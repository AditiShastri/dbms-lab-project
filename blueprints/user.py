import os
import re
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from models import Vehicle, User, ParkingLot, ParkingSpot, ParkingTransaction
from extensions import db
from sqlalchemy import func
from flask_jwt_extended import jwt_required, get_jwt_identity

user_bp = Blueprint('user', __name__)
PENDING_FILE = 'pending_vehicles.json'

# --- HELPER: SORT LOTS ---
def get_user_sorted_lots(user):
    all_lots = ParkingLot.query.all()
    if not user.preferences: return all_lots
    try:
        pref_ids = [int(x) for x in user.preferences.split(',') if x.strip().isdigit()]
        all_lots.sort(key=lambda x: pref_ids.index(x.lot_id) if x.lot_id in pref_ids else 999)
    except: pass
    return all_lots

# =========================================================
# 📊 DASHBOARD
# =========================================================
@user_bp.route('/dashboard')
@jwt_required()
def dashboard():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if not user:
        return redirect(url_for('auth.login'))

    # 1. Pull Approved Vehicles (Those already in the DB)
    # Uses user.user_id to match your specific model schema
    my_vehicles = Vehicle.query.filter_by(user_id=user.user_id).all()
    
    # Define vehicle_plates list for use in Active Session and History queries
    vehicle_plates = [v.license_plate for v in my_vehicles]
    
    # 2. Pull Pending/Rejected from JSON (Filter out those already in the DB)
    pending_list = []
    if os.path.exists(PENDING_FILE):
        try:
            with open(PENDING_FILE, 'r') as f:
                all_pending = json.load(f)
                # Only show JSON entries if the plate isn't already approved in DB
                pending_list = [v for v in all_pending 
                               if str(v['user_id']) == str(user.user_id) 
                               and v['license_plate'] not in vehicle_plates]
        except: 
            pending_list = []

    # 3. Active Session
    active_txn = None
    current_lot_name = ""
    if vehicle_plates:
        active_txn = ParkingTransaction.query.filter(
            ParkingTransaction.license_plate.in_(vehicle_plates),
            ParkingTransaction.exit_time == None
        ).first()
        
        if active_txn:
            lot = ParkingLot.query.get(active_txn.lot_id)
            current_lot_name = lot.location if lot else "Unknown"

    # 4. History
    history = []
    if vehicle_plates:
        history = ParkingTransaction.query.filter(
            ParkingTransaction.license_plate.in_(vehicle_plates),
            ParkingTransaction.exit_time != None
        ).order_by(ParkingTransaction.entry_time.desc()).limit(5).all()

    # 5. Get Sorted Lots based on User Preferences
    sorted_lots = get_user_sorted_lots(user)

    # Note: Ensure dashboard.html is inside templates/user/
    return render_template('user/dashboard.html', 
                         user=user, 
                         vehicles=my_vehicles, 
                         pending=pending_list,
                         active_txn=active_txn,
                         current_lot_name=current_lot_name,
                         history=history,
                         lots=sorted_lots)
# 
# =========================================================
# 📝 REGISTER VEHICLE
# =========================================================
@user_bp.route('/register_vehicle', methods=['GET', 'POST'])
@jwt_required()
def register_vehicle():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    if request.method == 'GET':
        return render_template('auth/register_vehicle.html', current_user=user)

    # A. Clean Inputs
    plate = request.form.get('license_plate', '').strip().upper().replace(" ", "").replace("-", "")
    model = request.form.get('model', 'Unknown')
    dl_raw = request.form.get('dl_number', '').strip().upper()
    
    # B. Validation
    if not re.match(r"^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$", plate):
        flash('Invalid License Plate format! (e.g., KA01AB1234)', 'error')
        return redirect(url_for('user.register_vehicle'))

    dl_clean = dl_raw.replace(" ", "").replace("-", "")
    if not re.match(r"^[A-Z]{2}\d{13}$", dl_clean):
        flash('Invalid DL Number! Must be 15 chars (e.g., KA0120220001234)', 'error')
        return redirect(url_for('user.register_vehicle'))

    if Vehicle.query.filter_by(license_plate=plate).first():
        flash('Vehicle already registered!', 'error')
        return redirect(url_for('user.register_vehicle'))

    # C. Save to Pending
    new_request = {
        "user_id": current_user_id,
        "license_plate": plate,
        "model": model,
        "dl_number": dl_clean,
        "status": "pending",
        "dl_file": "simulated_doc.pdf", 
        "rc_file": "simulated_doc.pdf"
    }
    
    data = []
    if os.path.exists(PENDING_FILE):
        try:
            with open(PENDING_FILE, 'r') as f:
                data = json.load(f)
        except: data = []
    
    data.append(new_request)
    with open(PENDING_FILE, 'w') as f:
        json.dump(data, f, indent=4)
        
    flash('Vehicle submitted for approval!', 'success')
    return redirect(url_for('user.dashboard'))

#=========================================================
#🗑️ DELETE VEHICLE
# =========================================================

@user_bp.route('/delete_vehicle/<string:plate>', methods=['POST'])
@jwt_required()
def delete_vehicle(plate):
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    # 1. Try to delete from DB
    vehicle = Vehicle.query.filter_by(license_plate=plate, user_id=user.user_id).first()
    if vehicle:
        db.session.delete(vehicle)
        db.session.commit()
        return jsonify({'status': 'success', 'msg': 'Vehicle removed from database'})

    # 2. Try to clear from JSON (Removes Rejected/Pending badges)
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, 'r') as f:
            pending = json.load(f)
        new_pending = [v for v in pending if not (v['license_plate'] == plate and str(v['user_id']) == str(current_user_id))]
        if len(new_pending) != len(pending):
            with open(PENDING_FILE, 'w') as f:
                json.dump(new_pending, f, indent=4)
            return jsonify({'status': 'success', 'msg': 'Request cleared'})

    return jsonify({'status': 'error', 'msg': 'Record not found'}), 404

# =========================================================
# 📈 ANALYTICS
# =========================================================
# =========================================================
# 📈 ANALYTICS (FIXED ATTRIBUTE NAME)
# =========================================================
@user_bp.route('/analytics')
@jwt_required()
def analytics():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    # Use user.user_id to match your model naming convention
    plates = [v.license_plate for v in user.vehicles]
    
    if not plates:
        return render_template('user/analytics.html', user=user, stats=None)

    # 1. Total Sessions (Counting any column that exists, license_plate is safe)
    total_sessions = ParkingTransaction.query.filter(ParkingTransaction.license_plate.in_(plates)).count()

    # 2. Hours Parked
    completed = ParkingTransaction.query.filter(
        ParkingTransaction.license_plate.in_(plates),
        ParkingTransaction.exit_time != None
    ).all()
    total_hours = round(sum([(t.exit_time - t.entry_time).total_seconds() for t in completed]) / 3600, 1)

    # 3. Favorite Lot (FIX: Counting 'lot_id' or '*' instead of 'id')
    fav = db.session.query(
        ParkingTransaction.lot_id, 
        func.count(ParkingTransaction.lot_id) # Changed from .id to .lot_id
    ).filter(ParkingTransaction.license_plate.in_(plates))\
     .group_by(ParkingTransaction.lot_id)\
     .order_by(func.count(ParkingTransaction.lot_id).desc()).first()
     
    fav_name = ParkingLot.query.get(fav[0]).location if fav else "None"

    stats = {
        'sessions': total_sessions,
        'hours': total_hours,
        'favorite': fav_name,
        'avg_duration': round(total_hours / total_sessions, 1) if total_sessions > 0 else 0
    }
    
    # Ensure this matches your template path (Option 1 from previous fix)
    return render_template('user/analytics.html', user=user, stats=stats)

# =========================================================
# ⚙️ PREFERENCES
# =========================================================
@user_bp.route('/update_preferences', methods=['POST'])
@jwt_required()
def update_preferences():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id)
    
    data = request.json
    if data and 'order' in data:
        user.preferences = ",".join(map(str, data['order']))
        db.session.commit()
        return jsonify({'status': 'success'})
        
    return jsonify({'status': 'error', 'msg': 'No data'})