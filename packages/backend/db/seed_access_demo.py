# packages/backend/db/seed_access_demo.py
# Idempotent: provision/refresh the Phase 2 access-lifecycle demo accounts.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import db as orm
from sqlalchemy import select

DEMO_USERS = [
    ("pending@ibcp.gov.pk", "Pending Access", "viewer", "PENDING", "pending123"),
    ("suspended@ibcp.gov.pk", "Suspended Access", "viewer", "SUSPENDED", "suspended123"),
]


def seed():
    with SessionLocal() as db:
        for email, name, role_name, status, pw in DEMO_USERS:
            role = db.execute(select(orm.Role).where(orm.Role.name == role_name)).scalar_one_or_none()
            if role is None:
                print(f"SKIP missing role {role_name} for {email}")
                continue
            user = db.execute(select(orm.User).where(orm.User.email == email)).scalar_one_or_none()
            if user is None:
                user = orm.User(
                    name=name, email=email,
                    password_hash=get_password_hash(pw), is_active=True,
                    access_status=status,
                )
                db.add(user)
                db.flush()
                db.add(orm.UserRole(user_id=user.id, role_id=role.id))
                print(f"created {email} @ {status}")
            else:
                user.access_status = status
                print(f"updated {email} -> {status}")
        db.commit()


if __name__ == "__main__":
    seed()