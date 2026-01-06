from app import create_app
from extensions import db

# Create the app instance
app = create_app()

# Use the app context to access the database
with app.app_context():
    print("Creating database tables...")
    db.create_all()
    print("SUCCESS: Database and tables created inside 'instance/parking.db'")