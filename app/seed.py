"""Idempotent seed data: real helpdesk categories, plus an optional admin user.

Run after migrations:  python -m app.seed
Set ADMIN_EMAIL and ADMIN_PASSWORD in .env to create/promote an admin account.
"""

import os

from .auth import hash_password
from .database import SessionLocal
from .models import Category, User

# Categories drawn from real helpdesk work, per the project guide.
DEFAULT_CATEGORIES = [
    "Printer",
    "Network",
    "M365/Exchange",
    "Yardi/Property Software",
    "Account Access",
    "Hardware",
]


def seed():
    db = SessionLocal()
    try:
        for name in DEFAULT_CATEGORIES:
            if not db.query(Category).filter(Category.name == name).first():
                db.add(Category(name=name))
                print(f"Added category: {name}")

        admin_email = os.environ.get("ADMIN_EMAIL")
        admin_password = os.environ.get("ADMIN_PASSWORD")
        if admin_email and admin_password:
            user = db.query(User).filter(User.email == admin_email).first()
            if user:
                if not user.is_admin:
                    user.is_admin = True
                    print(f"Promoted existing user to admin: {admin_email}")
            else:
                db.add(
                    User(
                        email=admin_email,
                        hashed_password=hash_password(admin_password),
                        is_admin=True,
                    )
                )
                print(f"Created admin user: {admin_email}")

        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
