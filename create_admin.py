from app import create_app
from extensions import db, bcrypt
from models import User

app = create_app()

with app.app_context():
    # 1. Check if user already exists
    if User.query.filter_by(email='admin@rvce.edu.in').first():
        print("User admin@rvce.edu.in already exists!")
    else:
        # 2. Hash the password
        hashed_pw = bcrypt.generate_password_hash('admin').decode('utf-8')
        
        # 3. Create the Admin User
        admin = User(
            name='System Admin', 
            email='admin@rvce.edu.in', 
            password_hash=hashed_pw, 
            role='admin',  # <--- Key part
            department='ADMIN'
        )
        
        db.session.add(admin)
        db.session.commit()
        print("SUCCESS: Admin user created!")
        print("Login with -> Email: admin@rvce.edu.in | Pass: admin")