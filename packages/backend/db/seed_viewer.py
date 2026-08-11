# packages/backend/scripts/seed_rbac.py
# Idempotent RBAC seed: wire role_permissions + create a real demo viewer user.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import db as orm
from sqlalchemy import select

VIEWER_PASSWORD = "viewer123"

ROLE_PERMS = {
    "admin": ["AQUAVISION_READ", "AQUAVISION_MANAGE_DATA", "AQUAVISION_ACKNOWLEDGE_ALERT",
              "AQUAVISION_CONFIGURE", "CROP_READ", "CROP_TRAIN_MODEL", "GEOVISION_READ",
              "SYSTEM_ADMIN"],
    "viewer": ["AQUAVISION_READ"],
    "aquavision_analyst": ["AQUAVISION_READ", "AQUAVISION_ANALYZE", "AQUAVISION_EXPORT"],
    "field_officer": ["AQUAVISION_READ", "AQUAVISION_ACKNOWLEDGE_ALERT", "AQUAVISION_ADD_NOTE"],
}


def seed():
    with SessionLocal() as db:
        perms = {p.name: p.id for p in db.execute(select(orm.Permission)).scalars().all()}
        roles = {r.name: r.id for r in db.execute(select(orm.Role)).scalars().all()}

        for role_name, pnames in ROLE_PERMS.items():
            rid = roles.get(role_name)
            if rid is None:
                continue
            for pn in pnames:
                pid = perms.get(pn)
                if pid is None:
                    continue
                exists = db.execute(select(orm.RolePermission).where(
                    orm.RolePermission.role_id == rid,
                    orm.RolePermission.permission_id == pid)).scalar_one_or_none()
                if exists is None:
                    db.add(orm.RolePermission(role_id=rid, permission_id=pid))

        viewer = db.execute(select(orm.User).where(orm.User.email == "viewer@ibcp.gov.pk")).scalar_one_or_none()
        if viewer is None:
            viewer = orm.User(name="Water Viewer", email="viewer@ibcp.gov.pk",
                              password_hash=get_password_hash(VIEWER_PASSWORD), is_active=True)
            db.add(viewer)
            db.flush()
            vid = roles.get("viewer")
            if vid:
                db.add(orm.UserRole(user_id=viewer.id, role_id=vid))

        db.commit()
        print("Seeded viewer. Login: viewer@ibcp.gov.pk /", VIEWER_PASSWORD)


if __name__ == "__main__":
    seed()