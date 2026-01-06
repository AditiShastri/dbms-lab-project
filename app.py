import os
from flask import Flask, render_template
from config import Config
from extensions import db, bcrypt, cors, mail # Note: We don't import 'jwt' here to avoid conflict
from flask_migrate import Migrate
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, JWTManager

# Import Models
from models import User, Vehicle, ParkingLot, ParkingSpot, ParkingTransaction, SupportMessage

# Import Blueprints
from blueprints.auth import auth_bp
from blueprints.admin import admin_bp
from blueprints.gate import gate_bp
from blueprints.user import user_bp

def create_app():
    # 1. SETUP FOLDERS (Crucial for finding HTML/CSS)
    base_dir = os.path.abspath(os.path.dirname(__file__))
    template_dir = os.path.join(base_dir, 'templates')
    static_dir = os.path.join(base_dir, 'static')

    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.config.from_object(Config)

    # 2. INITIALIZE EXTENSIONS
    db.init_app(app)
    bcrypt.init_app(app)
    cors.init_app(app)
    mail.init_app(app)
    
    # Initialize JWT Manager (This fixes the Attribute Error)
    jwt = JWTManager(app)
    
    migrate = Migrate(app, db)

    # 3. REGISTER BLUEPRINTS
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(gate_bp, url_prefix='/api/gate')
    
    # Note: We use '/user' instead of '/api/user' for the dashboard URL to look cleaner
    app.register_blueprint(user_bp, url_prefix='/user') 

    # 4. CONTEXT PROCESSORS (Inject Data into HTML)
    
    # Inject JWT User ID into all templates automatically
    @app.context_processor
    def inject_jwt():
        def safe_get_jwt_identity():
            try:
                verify_jwt_in_request(optional=True)
                return get_jwt_identity()
            except Exception:
                return None
        return dict(get_jwt_identity=safe_get_jwt_identity)

    # Helper to sort parking spots numerically
    @app.context_processor
    def utility_processor():
        def spot_sorter(spots):
            return sorted(spots, key=lambda x: x.spot_number)
        return dict(spot_sorter=spot_sorter)

    # 5. ROOT ROUTE
    @app.route('/')
    def index():
        return render_template('auth/login.html')

    return app

app = create_app()

# --- 🌱 DATABASE SEEDER ---
def seed_database():
    with app.app_context():
        db.create_all()
        
        # 1. Seed 5 Specific Parking Lots
        lots_data = [
            ("CSE Ground", 150),       # ID 1
            ("Near Kotak", 20),        # ID 2
            ("Near RVU", 30),          # ID 3
            ("Near B Quadrangle", 25), # ID 4
            ("Mech Parking Lot", 35)   # ID 5
        ]
        
        # Check if DB is empty before seeding
        if not ParkingLot.query.first():
            print("🌱 Seeding 5 Parking Lots...")
            for loc, caps in lots_data:
                lot = ParkingLot(location=loc, number_of_spots=caps)
                db.session.add(lot)
                db.session.commit() # Commit individually to guarantee ID order 1-5
                
                # Generate Spots
                for i in range(1, caps + 1):
                    # Faculty Reservation Logic (First 20%)
                    is_reserved = (i <= (caps * 0.2))
                    spot = ParkingSpot(
                        lot_id=lot.lot_id, 
                        spot_number=i,
                        reserved_for_faculty=is_reserved
                    )
                    db.session.add(spot)
            db.session.commit()
            print("✅ 5 Lots Created (Inc. Mech Lot).")

        # 2. Seed Admin
        if not User.query.filter_by(email="admin@rvce.edu.in").first():
            print("🌱 Seeding Admin...")
            hashed_pw = bcrypt.generate_password_hash('admin').decode('utf-8')
            admin = User(
                name="System Administrator",
                email="admin@rvce.edu.in",
                phone="9999999999",
                usn=None,
                password_hash=hashed_pw,
                role="admin",
                department="ADMIN",
                preferences="1,2,3,4,5"
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin Seeded.")

if __name__ == '__main__':
    seed_database()
    app.run(debug=True, port=5000)