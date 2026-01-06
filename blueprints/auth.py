import csv
import os
import re
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response
from extensions import db, bcrypt
from flask_jwt_extended import create_access_token, unset_jwt_cookies
from models import User, SupportMessage
from blueprints.utils import get_default_preferences
from flask_jwt_extended import create_access_token, set_access_cookies, unset_jwt_cookies

auth_bp = Blueprint('auth', __name__)

DEPT_MAPPING = {
    "ISE": "IS", "CSE": "CS", "ECE": "EC", "EEE": "EE",
    "MECH": "ME", "CIVIL": "CV", "AERO": "AS", "CHEM": "CH",
    "IEM": "IM", "EIE": "EI", "ETE": "ET"
}


# --- 1. SMART CSV LOADER (Fixes the Column Name Issue) ---
def get_csv_value(row, possible_keys):
    """
    Tries to find a value in the CSV row using a list of possible column names.
    Returns the first match found, or empty string.
    """
    for key in possible_keys:
        if key in row and row[key]:
            return row[key].strip()
    return ""

def load_csv_data(filename):
    data = {}
    if not os.path.exists(filename):
        print(f"⚠️ WARNING: '{filename}' not found.")
        return {}
    
    try:
        with open(filename, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            
            # 1. Normalize CSV headers to UPPERCASE to handle 'mail' vs 'MAIL'
            if reader.fieldnames:
                reader.fieldnames = [name.strip().upper() for name in reader.fieldnames]
            
            print(f"📂 Loading {filename}... Found Columns: {reader.fieldnames}")

            for row in reader:
                # 2. Try multiple keys for Email ("EMAIL", "MAIL", "EMAIL ID")
                email = get_csv_value(row, ['EMAIL', 'MAIL', 'EMAIL ID', 'EMAIL_ID']).lower()
                
                if email:
                    data[email] = {
                        # Try "NAME", "FULL NAME", "FACULTY NAME"
                        "name": get_csv_value(row, ['NAME', 'FULL NAME', 'STUDENT NAME', 'FACULTY NAME']),
                        
                        # Try "PHONE", "MOBILE", "CONTACT"
                        "phone": get_csv_value(row, ['PHONE', 'MOBILE', 'CONTACT NO', 'PHONE NUMBER']),
                        
                        # Try "BRANCH", "DEPARTMENT", "DEPT"
                        "branch": get_csv_value(row, ['BRANCH', 'DEPARTMENT', 'DEPT']) or "UNKNOWN",
                        
                        "role": "faculty" if "FACULTY" in filename.upper() else "student"
                    }
            
            print(f"✅ Loaded {len(data)} records from {filename}")
            
    except Exception as e:
        print(f"❌ Error reading {filename}: {e}")
    return data

# Load lists
MASTER_STUDENT_LIST = load_csv_data('STUDENT LIST.CSV')
MASTER_FACULTY_LIST = load_csv_data('FACULTY LIST.CSV') 

# --- 2. VALIDATION HELPERS ---
def validate_registration(data):
    if not all([data['name'], data['email'], data['phone'], data['password'], data['dept']]):
        return "All fields are required."
    
    if not data['email'].endswith('@rvce.edu.in'):
        return "Email must be an official RVCE address (@rvce.edu.in)"

    if not re.match(r'^[6-9]\d{9}$', data['phone']):
        return "Invalid Phone Number."

    if data['role'] == 'student':
        if not data['usn']:
            return "ID Card No. (USN) is required for Students."
        if not re.match(r"^RVCE\d{2}[A-Z]{2,3}\d{3}$", data['usn']):
            return "Invalid ID Card Format."

    if not re.match(r"^(?=.*[0-9])(?=.*[!@#$%^&*])[a-zA-Z0-9!@#$%^&*]{8,}$", data['password']):
        return "Password must be 8+ chars with 1 number & 1 special char."

    return None

def verify_identity(data):
    email = data['email']
    role = data['role']
    
    master_list = MASTER_FACULTY_LIST if role == 'faculty' else MASTER_STUDENT_LIST
    
    # A. Check Email Existence
    if email not in master_list:
        # Debugging Print (Check your terminal if this fails)
        print(f"❌ Verification Failed: {email} not found in loaded list.")
        return f"Email not found in official {role} records."

    record = master_list[email]
    
    # B. Name Match (Fuzzy)
    is_name_match = (data['name'].lower() in record['name'].lower()) or \
                    (record['name'].lower() in data['name'].lower())
    
    # C. Dept Match
    form_dept = data['dept']       # e.g., "ISE"
    official_dept = record['branch'] # e.g., "ISE" or "IS"
    
    # Normalize Official Dept using Mapping if it matches a Key (e.g. "ISE" -> "IS")
    # But if the CSV already has "ISE", we keep it.
    
    # Check 1: Direct Match (ISE == ISE)
    match_1 = (form_dept == official_dept)
    
    # Check 2: Mapped Match (ISE -> IS == IS)
    expected_code = DEPT_MAPPING.get(form_dept, form_dept)
    match_2 = (expected_code == official_dept)
    
    # Check 3: Reverse Map (IS -> ISE == ISE) - In case CSV has "IS" but form has "ISE"
    match_3 = False
    for key, val in DEPT_MAPPING.items():
        if val == official_dept and key == form_dept:
            match_3 = True
            break
            
    is_dept_match = match_1 or match_2 or match_3

    if not (is_name_match and is_dept_match):
        print(f"❌ Mismatch for {email}: Form[{data['name']}, {form_dept}] vs CSV[{record['name']}, {official_dept}]")
        return "Verification Failed: Identity details do not match official records."

    return None

# --- REGISTER ROUTE ---
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('auth/register.html', form_data={})

    data = {
        'name': request.form.get('name', '').strip(),
        'email': request.form.get('email', '').strip().lower(),
        'phone': request.form.get('phone', '').strip(),
        'usn': request.form.get('usn', '').strip().upper(),
        'password': request.form.get('password', ''),
        'role': request.form.get('role', 'student'),
        'dept': request.form.get('department', '')
    }

    error = validate_registration(data)
    if error:
        flash(error, 'error')
        return render_template('auth/register.html', form_data=data)

    # Reload lists if empty
    global MASTER_STUDENT_LIST, MASTER_FACULTY_LIST
    if not MASTER_STUDENT_LIST: MASTER_STUDENT_LIST = load_csv_data('STUDENT LIST.CSV')
    if not MASTER_FACULTY_LIST: MASTER_FACULTY_LIST = load_csv_data('FACULTY LIST.CSV')

    if data['role'] in ['student', 'faculty']:
        identity_error = verify_identity(data)
        if identity_error:
            flash(identity_error, 'error')
            return render_template('auth/register.html', form_data=data)

    if User.query.filter_by(email=data['email']).first():
        flash('Email already registered! Please Login.', 'error')
        return render_template('auth/register.html', form_data=data)
    
    if data['role'] == 'student' and User.query.filter_by(usn=data['usn']).first():
        flash('ID Card already registered! Please Login.', 'error')
        return render_template('auth/register.html', form_data=data)

    try:
        hashed_pw = bcrypt.generate_password_hash(data['password']).decode('utf-8')
        default_prefs = get_default_preferences(data['dept'])
        
        new_user = User(
            name=data['name'], 
            email=data['email'],
            password_hash=hashed_pw,
            phone=data['phone'],
            usn=data['usn'] if data['role'] == 'student' else None, 
            role=data['role'],
            department=data['dept'],
            preferences=default_prefs
        )
        db.session.add(new_user)
        db.session.commit()
        
        access_token = create_access_token(identity=str(new_user.user_id), additional_claims={"role": new_user.role})
        target_page = 'admin.dashboard' if new_user.role == 'admin' else 'user.dashboard'
        response = make_response(redirect(url_for(target_page)))
        set_access_cookies(response, access_token)
        flash(f'✅ Account Created! Welcome, {new_user.name}.', 'success')
        return response
        
    except Exception as e:
        db.session.rollback()
        flash(f"System Error: {str(e)}", 'error')
        return render_template('auth/register.html', form_data=data)

# ... Login/Logout/Contact routes remain same ...
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('auth/login.html')

    email = request.form.get('email')
    password = request.form.get('password')
    user = User.query.filter_by(email=email).first()

    if user and bcrypt.check_password_hash(user.password_hash, password):
        # 1. Create Token
        access_token = create_access_token(identity=str(user.user_id), additional_claims={"role": user.role})
        
        # 2. Determine Redirect
        target_page = 'admin.dashboard' if user.role == 'admin' else 'user.dashboard'
        
        # 3. Create Response & Attach Cookie
        response = make_response(redirect(url_for(target_page)))
        set_access_cookies(response, access_token) # <--- USES CONFIG SETTINGS AUTOMATICALLY
        
        flash(f'Welcome back, {user.name}!', 'success')
        return response
    else:
        flash('Invalid Email or Password', 'error')
        return redirect(url_for('auth.login'))
    
@auth_bp.route('/logout')
def logout():
    response = make_response(redirect(url_for('auth.login')))
    unset_jwt_cookies(response)
    flash('Logged out successfully.', 'info')
    return response

@auth_bp.route('/contact_admin', methods=['POST'])
def contact_admin():
    email = request.form.get('contact_email')
    msg_text = request.form.get('message')
    
    if email and msg_text:
        try:
            new_msg = SupportMessage(sender_email=email, message=msg_text)
            db.session.add(new_msg)
            db.session.commit()
            flash('Message sent to Admin!', 'success')
        except Exception:
            db.session.rollback()
            flash('Error sending message.', 'error')
    return render_template('auth/register.html', form_data={'email': email})