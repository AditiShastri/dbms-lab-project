import cv2
import easyocr
import numpy as np
import requests
import difflib
from flask import Blueprint, request, jsonify, render_template
from datetime import datetime
from extensions import db, mail
from flask_mail import Message
from models import Vehicle, User, ParkingLot, ParkingSpot, ParkingTransaction
from blueprints.utils import get_user_sorted_lots

gate_bp = Blueprint('gate', __name__)

# --- CONFIGURATION ---
MY_PHONE_IP = "http://192.168.29.88:8080" 

ENTRY_PLATE_IP = MY_PHONE_IP 
ENTRY_ID_IP    = MY_PHONE_IP 
EXIT_ID_IP     = MY_PHONE_IP 

reader = easyocr.Reader(['en'], gpu=False)

# --- HELPER 1: FETCH IMAGE ---
def fetch_image(base_url):
    try:
        url = f"{base_url}/shot.jpg"
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            arr = np.asarray(bytearray(resp.content), dtype=np.uint8)
            frame = cv2.imdecode(arr, -1)
            return frame, None
        return None, "Camera Unreachable"
    except Exception as e:
        return None, str(e)

# --- HELPER 2: ROBUST OCR SOUP ---
def read_ocr_soup(image, debug_filename="debug_ocr.jpg"):
    cv2.imwrite(debug_filename, image)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY)
    res_bin = reader.readtext(binary, detail=0)
    res_gray = reader.readtext(gray, detail=0)
    raw_soup = "".join(res_bin + res_gray).upper().replace(" ", "").replace("-", "").replace(".", "")
    soup_fixed = raw_soup.replace('_', '').replace(';', '').replace(':', '')
    print(f"🥣 SOUP ({debug_filename}): {soup_fixed}")
    return soup_fixed

# --- HELPER 3: SMART MATCHING (Sliding Window) ---
def find_best_match(soup, all_vehicles):
    def normalize(text):
        return text.replace('S', '5').replace('Z', '2').replace('I', '1') \
                   .replace('O', '0').replace('B', '8').replace('D', '0') \
                   .replace('G', '6').replace('Q', '0').replace('U', '0')

    norm_soup = normalize(soup)
    best_vehicle = None; best_score = 0.0

    for v in all_vehicles:
        plate = v.license_plate.upper()
        norm_plate = normalize(plate)
        n = len(norm_plate)

        if plate in soup: return v, 1.0

        max_plate_score = 0.0
        for i in range(len(norm_soup)):
            chunk = norm_soup[i : i + n]
            chunk_short = norm_soup[i : i + n - 1] if (i + n - 1) <= len(norm_soup) else ""
            
            if len(chunk) > n * 0.6:
                score = difflib.SequenceMatcher(None, norm_plate, chunk).ratio()
                if score > max_plate_score: max_plate_score = score
            if len(chunk_short) > n * 0.6:
                score = difflib.SequenceMatcher(None, norm_plate, chunk_short).ratio()
                if score > max_plate_score: max_plate_score = score

        if max_plate_score > best_score:
            best_score = max_plate_score; best_vehicle = v

    return best_vehicle, best_score

# --- HELPER 4: EMAIL NOTIFICATIONS 📧 ---
def send_entry_email(user, lot, spot_number):
    try:
        msg = Message(f"Entry Approved: {lot.location}", recipients=[user.email])
        msg.body = f"Hello {user.name},\n\nEntry Approved.\n📍 LOT: {lot.location}\n🔢 SPOT: #{spot_number}\n\nDrive carefully!"
        mail.send(msg)
        print(f"📧 ENTRY EMAIL SENT to {user.email}")
    except Exception as e:
        print(f"⚠️ EMAIL FAILED: {str(e)}")

def send_exit_email(user, txn, lot):
    try:
        # Calculate Duration
        duration = txn.exit_time - txn.entry_time
        hours, remainder = divmod(duration.seconds, 3600)
        minutes = remainder // 60
        time_str = f"{hours}h {minutes}m"

        msg = Message(f"Exit Summary: {txn.license_plate}", recipients=[user.email])
        msg.body = f"""
        Hello {user.name},
        
        Your parking session has ended.
        
        🚗 VEHICLE:   {txn.license_plate}
        📍 LOCATION:  {lot.location}
        
        🕒 START TIME: {txn.entry_time.strftime('%I:%M %p')}
        🕒 END TIME:   {txn.exit_time.strftime('%I:%M %p')}
        ⏳ DURATION:   {time_str}
        
        Thank you for using Smart Parking!
        """
        mail.send(msg)
        print(f"📧 EXIT EMAIL SENT to {user.email}")
    except Exception as e:
        print(f"⚠️ EXIT EMAIL FAILED: {str(e)}")


@gate_bp.route('/console')
def console():
    return render_template('gate/console.html')

# ==========================================================
# 🚗 ENTRY LOGIC (Steps 1 & 2)
# ==========================================================
@gate_bp.route('/scan_plate_entry', methods=['POST'])
def scan_plate_entry():
    manual = request.json.get('manual_plate')
    soup_fixed = ""
    if manual: soup_fixed = manual.upper()
    else:
        frame, error = fetch_image(ENTRY_PLATE_IP)
        if error: return jsonify({"status": "error", "msg": error}), 500
        soup_fixed = read_ocr_soup(frame, "debug_plate_entry.jpg")

    all_vehicles = Vehicle.query.all()
    found_vehicle, score = find_best_match(soup_fixed, all_vehicles)

    if not found_vehicle or score < 0.65:
        return jsonify({"status": "denied", "msg": "No Plate Found", "debug_ocr": soup_fixed}), 404
    
    if ParkingTransaction.query.filter_by(license_plate=found_vehicle.license_plate, exit_time=None).first():
        return jsonify({"status": "denied", "msg": "Vehicle Already Inside!"}), 400

    user = User.query.get(found_vehicle.user_id)

    if user.role == 'faculty':
        print(f"🎓 FACULTY: {user.name} - Bypassing ID Check")
        preferred_lots = get_user_sorted_lots(user)
        allocated_spot = None; allocated_lot = None
        for lot in preferred_lots:
            spot = ParkingSpot.query.filter_by(lot_id=lot.lot_id, status='available').first()
            if spot: allocated_spot = spot; allocated_lot = lot; break
        
        if not allocated_spot: return jsonify({"status": "denied", "msg": "Campus Full"}), 400
        
        allocated_spot.status = 'occupied'
        new_txn = ParkingTransaction(license_plate=found_vehicle.license_plate, lot_id=allocated_lot.lot_id, spot_number=allocated_spot.spot_number, entry_time=datetime.now())
        db.session.add(new_txn); db.session.commit()
        send_entry_email(user, allocated_lot, allocated_spot.spot_number)
        
        return jsonify({"status": "allowed", "owner": user.name, "lot": allocated_lot.location, "spot": allocated_spot.spot_number, "msg": f"Welcome Faculty {user.name}!"})

    return jsonify({"status": "step1_success", "plate": found_vehicle.license_plate, "owner_name": user.name, "expected_usn": user.usn, "msg": f"Verified. Scan ID."})


@gate_bp.route('/verify_id_and_grant', methods=['POST'])
def verify_id_and_grant():
    plate = request.json.get('plate')
    expected_usn = request.json.get('expected_usn')
    manual_id = request.json.get('manual_id')
    soup_fixed = ""

    if manual_id: soup_fixed = manual_id.upper()
    else:
        frame, error = fetch_image(ENTRY_ID_IP)
        if error: return jsonify({"status": "error", "msg": error}), 500
        soup_fixed = read_ocr_soup(frame, "debug_id_entry.jpg")

    match = False
    if expected_usn and expected_usn in soup_fixed: match = True
    else:
        score = difflib.SequenceMatcher(None, expected_usn, soup_fixed).ratio()
        if score > 0.45: match = True

    if not match: return jsonify({"status": "denied", "msg": f"ID Mismatch (Expected {expected_usn})", "debug_data": soup_fixed}), 400

    vehicle = Vehicle.query.filter_by(license_plate=plate).first()
    user = User.query.get(vehicle.user_id)
    preferred_lots = get_user_sorted_lots(user)
    
    allocated_spot = None; allocated_lot = None
    for lot in preferred_lots:
        query = ParkingSpot.query.filter_by(lot_id=lot.lot_id, status='available')
        if user.role != 'faculty': query = query.filter_by(reserved_for_faculty=False)
        spot = query.first()
        if spot: allocated_spot = spot; allocated_lot = lot; break
            
    if not allocated_spot: return jsonify({"status": "denied", "msg": "Campus Full"}), 400

    allocated_spot.status = 'occupied'
    new_txn = ParkingTransaction(license_plate=plate, lot_id=allocated_lot.lot_id, spot_number=allocated_spot.spot_number, entry_time=datetime.now())
    db.session.add(new_txn); db.session.commit()
    send_entry_email(user, allocated_lot, allocated_spot.spot_number)

    return jsonify({"status": "allowed", "owner": user.name, "lot": allocated_lot.location, "spot": allocated_spot.spot_number})


# ==========================================================
# 📤 EXIT LOGIC (Plate Based + Email Receipt)
# ==========================================================
@gate_bp.route('/scan_exit_id', methods=['POST'])
def scan_exit_id():
    manual_plate = request.json.get('manual_id')
    soup_fixed = ""

    if manual_plate: soup_fixed = manual_plate.upper()
    else:
        frame, error = fetch_image(EXIT_ID_IP)
        if error: return jsonify({"status": "error", "msg": error}), 500
        soup_fixed = read_ocr_soup(frame, "debug_exit_plate.jpg")

    all_vehicles = Vehicle.query.all()
    found_vehicle, score = find_best_match(soup_fixed, all_vehicles)

    if not found_vehicle or score < 0.65:
        return jsonify({"status": "denied", "msg": "No Plate Found", "debug": soup_fixed}), 404

    active_txn = ParkingTransaction.query.filter_by(license_plate=found_vehicle.license_plate, exit_time=None).first()
    
    if not active_txn:
        return jsonify({"status": "denied", "msg": f"Vehicle {found_vehicle.license_plate} not inside."}), 404

    # CHECKOUT
    user = User.query.get(found_vehicle.user_id)
    spot = ParkingSpot.query.filter_by(lot_id=active_txn.lot_id, spot_number=active_txn.spot_number).first()
    current_lot = ParkingLot.query.get(active_txn.lot_id) # Need lot details for email

    if spot: spot.status = 'available'
    
    active_txn.exit_time = datetime.now()
    db.session.commit()

    # SEND EXIT EMAIL 📧
    send_exit_email(user, active_txn, current_lot)

    return jsonify({"status": "allowed", "msg": f"Goodbye {user.name}!", "plate": active_txn.license_plate})