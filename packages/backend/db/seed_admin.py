# packages/backend/db/create_admin.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import db as orm
from sqlalchemy import select

with SessionLocal() as db:
    u = db.execute(select(orm.User).where(orm.User.email == "admin@ibcp.gov.pk")).scalar_one_or_none()
    if u is None:
        u = orm.User(name="System Admin", email="admin@ibcp.gov.pk",
                     password_hash=get_password_hash("admin123"), is_active=True)
        db.add(u)
        db.flush()
        print("created admin user id", u.id)
    else:
        u.password_hash = get_password_hash("admin123")
        db.flush()
        print("updated admin user id", u.id)
    role = db.execute(select(orm.Role).where(orm.Role.name == "admin")).scalar_one_or_none()
    if role:
        ex = db.execute(select(orm.UserRole).where(orm.UserRole.user_id == u.id)).scalar_one_or_none()
        if ex is None:
            db.add(orm.UserRole(user_id=u.id, role_id=role.id))
    db.commit()
print("Done. admin@ibcp.gov.pk / admin123")