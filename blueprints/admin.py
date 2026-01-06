import json
import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_jwt_extended import jwt_required, get_jwt
from flask_mail import Message
from extensions import db, mail
from models import ParkingLot, ParkingSpot, ParkingTransaction, Vehicle, User, SupportMessage
from flask import jsonify
admin_bp = Blueprint('admin', __name__)

PENDING_FILE = 'pending_vehicles.json'

# --- HELPER FUNCTIONS FOR JSON ---
def load_pending():
    if not os.path.exists(PENDING_FILE):
        return []
    try:
        with open(PENDING_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_pending(data):
    with open(PENDING_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# --- 🔒 SECURITY MIDDLEWARE ---
@admin_bp.before_request
@jwt_required()
def check_admin():
    claims = get_jwt()
    if claims.get("role") != "admin":
        flash("⛔ ACCESS DENIED: Administrator privileges required.", "error")
        return redirect(url_for('user.dashboard'))

# --- 📊 DASHBOARD ROUTES ---
@admin_bp.route('/spot_details/<int:lot_id>/<int:spot_number>')
def spot_details(lot_id, spot_number):
    """
    Fetches the Active Transaction for a specific spot to show the Admin who is parked there.
    """
    # Find the active transaction (where exit_time is None)
    txn = ParkingTransaction.query.filter_by(
        lot_id=lot_id, 
        spot_number=spot_number, 
        exit_time=None
    ).first()

    if not txn:
        return jsonify({"status": "error", "msg": "Spot appears empty or system error."}), 404

    # Fetch Vehicle and Owner
    vehicle = Vehicle.query.filter_by(license_plate=txn.license_plate).first()
    owner = User.query.get(vehicle.user_id)

    return jsonify({
        "status": "success",
        "spot": spot_number,
        "plate": txn.license_plate,
        "owner": owner.name,
        "role": owner.role.upper(),
        "phone": owner.phone,
        "entry_time": txn.entry_time.strftime("%H:%M:%S")
    })

@admin_bp.route('/dashboard')
def dashboard():
    lots = ParkingLot.query.all()
    pending_count = len(load_pending())
    
    # Sort spots numerically
    for lot in lots:
        lot.spots.sort(key=lambda x: x.spot_number)
        
    return render_template('admin/dashboard.html', lots=lots, pending_count=pending_count)

@admin_bp.route('/create_lot', methods=['POST'])
def create_lot():
    location = request.form.get('location')
    capacity = int(request.form.get('capacity'))
    
    new_lot = ParkingLot(location=location, number_of_spots=capacity)
    db.session.add(new_lot)
    db.session.commit()
    
    # Auto-generate spots (20% reserved for faculty)
    for i in range(1, capacity + 1):
        is_reserved = True if i <= (capacity * 0.2) else False
        spot = ParkingSpot(
            lot_id=new_lot.lot_id, 
            spot_number=i, 
            status='available', 
            reserved_for_faculty=is_reserved
        )
        db.session.add(spot)
    
    db.session.commit()
    flash('✅ Parking Lot Created Successfully!', 'success')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/delete_lot/<int:lot_id>', methods=['POST'])
def delete_lot(lot_id):
    lot = ParkingLot.query.get_or_404(lot_id)
    active_spots = ParkingSpot.query.filter_by(lot_id=lot_id, status='occupied').count()
    if active_spots > 0:
        flash(f'❌ Cannot delete lot! {active_spots} cars are still parked here.', 'error')
        return redirect(url_for('admin.dashboard'))

    db.session.delete(lot)
    db.session.commit()
    flash('🗑️ Parking Lot Deleted!', 'success')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/edit_lot/<int:lot_id>', methods=['POST'])
def edit_lot(lot_id):
    lot = ParkingLot.query.get_or_404(lot_id)
    new_capacity = int(request.form.get('capacity'))
    current_capacity = lot.number_of_spots
    
    if new_capacity > current_capacity:
        for i in range(current_capacity + 1, new_capacity + 1):
            spot = ParkingSpot(lot_id=lot.lot_id, spot_number=i, status='available')
            db.session.add(spot)
        lot.number_of_spots = new_capacity
        db.session.commit()
        flash(f'✅ Capacity increased to {new_capacity}.', 'success')

    elif new_capacity < current_capacity:
        spots_to_remove = ParkingSpot.query.filter(
            ParkingSpot.lot_id == lot_id,
            ParkingSpot.spot_number > new_capacity
        ).all()
        
        for spot in spots_to_remove:
            if spot.status == 'occupied':
                flash(f'❌ Cannot reduce capacity! Spot #{spot.spot_number} is occupied.', 'error')
                return redirect(url_for('admin.dashboard'))
        
        for spot in spots_to_remove:
            db.session.delete(spot)
        
        lot.number_of_spots = new_capacity
        db.session.commit()
        flash(f'⚠️ Capacity reduced to {new_capacity}.', 'success')

    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/toggle_faculty/<int:lot_id>/<int:spot_number>', methods=['POST'])
def toggle_faculty(lot_id, spot_number):
    spot = ParkingSpot.query.filter_by(lot_id=lot_id, spot_number=spot_number).first_or_404()
    if spot.status == 'occupied':
        active_txn = ParkingTransaction.query.join(Vehicle).join(User).filter(
                ParkingTransaction.lot_id == lot_id,
                ParkingTransaction.spot_number == spot_number,
                ParkingTransaction.exit_time == None,
                User.role == 'student'
            ).first()
        if active_txn:
            flash(f'⛔ Action Denied: Spot #{spot_number} is occupied by a Student.', 'error')
            return redirect(url_for('admin.dashboard'))

    spot.reserved_for_faculty = not spot.reserved_for_faculty
    db.session.commit()
    status = "Faculty Only" if spot.reserved_for_faculty else "Open to All"
    flash(f'Spot #{spot_number} is now {status}.', 'success')
    return redirect(url_for('admin.dashboard'))

# --- 📋 APPROVAL ROUTES ---
# ... inside blueprints/admin.py ...

@admin_bp.route('/approvals')
def approvals():
    pending_list = load_pending()
    
    # --- ENRICH DATA WITH USER INFO ---
    # The JSON only has 'user_id'. We need Name, Dept, USN from the DB.
    final_list = []
    
    for item in pending_list:
        user = User.query.get(item['user_id'])
        if user:
            # Add user details to the dictionary temporarily for display
            item['user_name'] = user.name
            item['user_dept'] = user.department
            item['user_usn'] = user.usn
            item['user_email'] = user.email
            final_list.append(item)
    
    return render_template('admin/approvals.html', pending=final_list)

@admin_bp.route('/approve/<plate>')
def approve_vehicle(plate):
    pending = load_pending()
    vehicle_data = next((item for item in pending if item["license_plate"] == plate), None)
    
    if vehicle_data:
        new_vehicle = Vehicle(
            license_plate=vehicle_data['license_plate'],
            type=vehicle_data['type'],
            user_id=vehicle_data['user_id']
        )
        db.session.add(new_vehicle)
        db.session.commit()
        
        pending = [v for v in pending if v['license_plate'] != plate]
        save_pending(pending)
        flash(f'✅ Vehicle {plate} Approved & Registered!', 'success')
    else:
        flash('Vehicle not found in queue.', 'error')
    return redirect(url_for('admin.approvals'))

@admin_bp.route('/reject/<plate>')
def reject_vehicle(plate):
    pending = load_pending()
    pending = [v for v in pending if v['license_plate'] != plate]
    save_pending(pending)
    flash(f'🚫 Vehicle {plate} Rejected.', 'error')
    return redirect(url_for('admin.approvals'))

# --- 💬 SUPPORT INBOX ROUTES (The Missing Part) ---

@admin_bp.route('/messages')
def view_messages():
    # This was missing in your file!
    messages = SupportMessage.query.order_by(SupportMessage.created_at.desc()).all()
    return render_template('admin/messages.html', messages=messages)

@admin_bp.route('/mark_read/<int:msg_id>')
def mark_read(msg_id):
    msg = SupportMessage.query.get_or_404(msg_id)
    msg.status = 'read'
    db.session.commit()
    flash('Message marked as read.', 'success')
    return redirect(url_for('admin.view_messages'))

@admin_bp.route('/reply_message', methods=['POST'])
def reply_message():
    msg_id = request.form.get('msg_id')
    reply_body = request.form.get('reply_text')
    
    support_msg = SupportMessage.query.get_or_404(msg_id)
    
    try:
        email = Message(
            subject=f"Re: Support Request (Ticket #{msg_id})",
            sender=current_app.config['MAIL_USERNAME'],
            recipients=[support_msg.sender_email],
            body=f"Hello,\n\nRegarding your issue:\n> {support_msg.message}\n\n{reply_body}\n\nBest Regards,\nRVCE Parking Admin Team"
        )
        mail.send(email)
        
        support_msg.status = 'replied'
        db.session.commit()
        flash(f'✅ Reply sent to {support_msg.sender_email}!', 'success')
    except Exception as e:
        flash(f"❌ Failed to send email: {str(e)}", 'error')
        
    return redirect(url_for('admin.view_messages'))