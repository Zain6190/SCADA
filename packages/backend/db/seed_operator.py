# packages/backend/db/seed_operator.py
# Creates a demo operator user with a restricted geographic scope
# (Sukkur, Larkana, Hyderabad districts in Sindh) to demonstrate #2.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import db as orm
from sqlalchemy import select

EMAIL = "operator@ibcp.gov.pk"
PASSWORD = "operator123"
REGION_IDS = [11, 12, 10]  # Sukkur, Larkana, Hyderabad

with SessionLocal() as db:
    u = db.execute(select(orm.User).where(orm.User.email == EMAIL)).scalar_one_or_none()
    if u is None:
        u = orm.User(name="Sindh Operator", email=EMAIL,
                     password_hash=get_password_hash(PASSWORD), is_active=True)
        db.add(u)
        db.flush()
        print("created operator user id", u.id)
    else:
        u.password_hash = get_password_hash(PASSWORD)
        print("updated operator user id", u.id)

    field = db.execute(select(orm.Role).where(orm.Role.name == "field_officer")).scalar_one_or_none()
    if field:
        ex = db.execute(select(orm.UserRole).where(orm.UserRole.user_id == u.id)).scalar_one_or_none()
        if ex is None:
            db.add(orm.UserRole(user_id=u.id, role_id=field.id))

    # reset scopes then grant the Sindh districts as DISTRICT-type scopes
    existing = db.execute(select(orm.UserRegionScope).where(orm.UserRegionScope.user_id == u.id)).scalars().all()
    for e in existing:
        db.delete(e)
    for rid in REGION_IDS:
        db.add(orm.UserRegionScope(user_id=u.id, scope_type="DISTRICT", region_id=rid, is_active=True))

    db.commit()
print(f"Done. operator@ibcp.gov.pk / {PASSWORD} scope={REGION_IDS}")