# packages/backend/db/seed_supervisor.py
# Creates the water_supervisor demo account (national scope) for the #12
# SCADA alarm lifecycle: verifies operator responses and clears resolved
# alerts. The role + VERIFY_RESPONSE / RESOLVE_ALERT permissions are seeded
# by migration 12_alert_alarm_lifecycle.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import db as orm
from sqlalchemy import select

EMAIL = "supervisor@ibcp.gov.pk"
PASSWORD = "supervisor123"

with SessionLocal() as db:
    u = db.execute(select(orm.User).where(orm.User.email == EMAIL)).scalar_one_or_none()
    if u is None:
        u = orm.User(name="Water Supervisor", email=EMAIL,
                     password_hash=get_password_hash(PASSWORD), is_active=True)
        db.add(u)
        db.flush()
        print("created supervisor user id", u.id)
    else:
        u.password_hash = get_password_hash(PASSWORD)
        print("updated supervisor user id", u.id)

    role = db.execute(select(orm.Role).where(orm.Role.name == "water_supervisor")).scalar_one_or_none()
    if role is None:
        print("SKIP: water_supervisor role missing - run alembic upgrade to head first")
    else:
        ex = db.execute(select(orm.UserRole).where(orm.UserRole.user_id == u.id)).scalar_one_or_none()
        if ex is None:
            db.add(orm.UserRole(user_id=u.id, role_id=role.id))

    # National scope so the supervisor can work any region's alerts.
    existing = db.execute(select(orm.UserRegionScope).where(orm.UserRegionScope.user_id == u.id)).scalars().all()
    for e in existing:
        db.delete(e)
    db.add(orm.UserRegionScope(user_id=u.id, scope_type="NATIONAL", is_active=True))

    db.commit()
print(f"Done. {EMAIL} / {PASSWORD}")