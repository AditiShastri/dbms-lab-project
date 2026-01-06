from extensions import db
from datetime import datetime  # <--- THIS WAS MISSING

class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    usn = db.Column(db.String(20), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='student')
    department = db.Column(db.String(50))
    preferences = db.Column(db.String(50), default="1,2,3,4")
    
    # Relationships
    vehicles = db.relationship('Vehicle', backref='owner', lazy=True)

class Vehicle(db.Model):
    __tablename__ = 'vehicles' # Good practice to name tables explicitly
    id = db.Column(db.Integer, primary_key=True)
    license_plate = db.Column(db.String(20), unique=True, nullable=False)
    type = db.Column(db.String(20), nullable=False) 
    
    # --- NEW COLUMNS ---
    dl_number = db.Column(db.String(50), nullable=True)
    dl_file = db.Column(db.String(150), nullable=True)
    rc_file = db.Column(db.String(150), nullable=True)
    # -------------------

    # FIX: changed 'user.user_id' to 'users.user_id' to match the User table name
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ParkingLot(db.Model):
    __tablename__ = 'parking_lots'
    lot_id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(100), nullable=False)
    number_of_spots = db.Column(db.Integer, nullable=False)
    spots = db.relationship('ParkingSpot', backref='lot', lazy=True, cascade="all, delete-orphan")

class ParkingSpot(db.Model):
    __tablename__ = 'parking_spots'
    spot_id = db.Column(db.Integer, primary_key=True)
    lot_id = db.Column(db.Integer, db.ForeignKey('parking_lots.lot_id'), nullable=False)
    spot_number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='available')
    reserved_for_faculty = db.Column(db.Boolean, default=False)

class ParkingTransaction(db.Model):
    __tablename__ = 'parking_transactions'
    transaction_id = db.Column(db.Integer, primary_key=True)
    license_plate = db.Column(db.String(20), nullable=False)
    lot_id = db.Column(db.Integer, nullable=False)
    spot_number = db.Column(db.Integer, nullable=False)
    entry_time = db.Column(db.DateTime, nullable=False)
    exit_time = db.Column(db.DateTime, nullable=True)
    fee = db.Column(db.Float, default=0.0)

class SupportMessage(db.Model):
    __tablename__ = 'support_messages'
    msg_id = db.Column(db.Integer, primary_key=True)
    sender_email = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='unread')
    created_at = db.Column(db.DateTime, server_default=db.func.now())