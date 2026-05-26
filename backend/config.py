import os
from dotenv import load_dotenv

load_dotenv()

# JWT Config
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key-change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Security Config
# Default is 'admin123' hashed using bcrypt
DEFAULT_ADMIN_HASH = "$2b$12$JnRosKAnW.Q7eeeaDUfcN.IlKTfPvpHrtOKmR9q9XaHyfEUQloGZe"
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", DEFAULT_ADMIN_HASH)

# CAPTCHA Config
CAPTCHA_SECRET = os.getenv("CAPTCHA_SECRET", "")
DISABLE_CAPTCHA = os.getenv("DISABLE_CAPTCHA", "True").lower() in ("true", "1", "yes")

# WordPress Config (Loaded directly in the scripts as well, but good to have here)
WP_URL = os.getenv("WP_URL", "")
WP_USER = os.getenv("WP_USER", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")
