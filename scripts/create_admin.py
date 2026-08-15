"""
Create or update the initial admin user.

Usage:
    ADMIN_EMAIL=admin@n-designs.local ADMIN_PASSWORD=changeme python scripts/create_admin.py
"""
import os
import sys

# Ensure project root is on the path when run directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@n-designs.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

if not ADMIN_PASSWORD:
    print("ERROR: ADMIN_PASSWORD env var is required.", file=sys.stderr)
    sys.exit(1)

db = SessionLocal()
try:
    user = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if user:
        user.hashed_password = hash_password(ADMIN_PASSWORD)
        user.is_active = True
        db.commit()
        print(f"Updated existing user: {ADMIN_EMAIL}")
    else:
        user = User(
            email=ADMIN_EMAIL,
            hashed_password=hash_password(ADMIN_PASSWORD),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Created admin user (id={user.id}): {ADMIN_EMAIL}")
finally:
    db.close()
