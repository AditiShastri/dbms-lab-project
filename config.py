import os

class Config:
    # --- 1. BASIC CONFIG ---
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'rvce_parking_super_secret_key_999'
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'parking.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- 2. JWT CONFIGURATION (CRITICAL) ---
    JWT_SECRET_KEY = 'super_secret_jwt_key_change_this'
    
    # TELL JWT TO READ FROM COOKIES
    JWT_TOKEN_LOCATION = ['cookies']
    
    # RELAX SECURITY FOR LOCALHOST (HTTP)
    JWT_COOKIE_SECURE = False  # Set to True only if using HTTPS
    JWT_COOKIE_CSRF_PROTECT = False # Disable CSRF for now to stop 401 errors
    
    # AUTO-REFRESH (Optional)
    JWT_ACCESS_TOKEN_EXPIRES = 3600 # 1 hour

    # --- 3. UPLOADS ---
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'backend', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 

    # --- 4. EMAIL ---
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'your-mail@gmail.com'
    MAIL_PASSWORD = 'your-mail@gmail.com'
    MAIL_DEFAULT_SENDER = ('RVCE Parking', 'your-mail@gmail.com')