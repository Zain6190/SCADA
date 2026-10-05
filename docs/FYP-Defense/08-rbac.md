# 08 — Role-Based Access Control (RBAC)

## 1. Identity stack

* Passwords: **bcrypt** hashing; JWT (PyJWT) bearer tokens —
  `services/aquavision-service/infrastructure/auth/security.py`, `.../auth/jwt.py`
  (stated in `routers/auth.py:4`).
* Login: `POST /auth/login` (`routers/auth.py:131`) validates against PostgreSQL and
  returns `LoginResponse { access_token, user }` (`auth.py:53-54`, `:187`) including the
  caller's `roles` and `permissions` (serialised at `auth.py:102-123`).
* Protected reads decode the token with `get_current_user`
  (`infrastructure/auth/jwt.py`), e.g. every workflow endpoint:
  `user: dict = Depends(get_current_user)` (`routers/alert_workflow.py:225, :323, :379, ...`).
  Without a token: HTTP 401 (verified live: `GET /water/alerts/queue` → 401).
* Explicit guards: `require_permissions(...)` (`infrastructure/auth/rbac.py:136`) —
  used for model-governance actions `approve/promote/reject`
  (`APPROVE_GUARD = require_permissions("AQUAVISION_APPROVE_REPORT")`, `registry.py:19`)
  and operator management (`auth.py:531`).
* Privilege-escalation blacklist: `system_admin`, `superuser`, `root` can never be
  assigned (`auth.py:74`).

## 2. Roles and permissions (live data)

Seven roles exist in `shared.roles` (members in brackets):

| Role | Members | Permissions held |
|------|---------|------------------|
| `admin` | 3 | full AQUAVISION set (read/analyze/export/ack/add-note/approve/manage-data/configure), escalate, resolve, send-instruction, verify-response, manage-operators, CROP_*, GEOVISION_READ, SYSTEM_ADMIN |
| `water_supervisor` | 5 | read, analyze, export, ack, add-note, approve-report, escalate, resolve, send-instruction, verify-response, manage-operators |
| `field_officer` | 8 | read, ack, add-note |
| `aquavision_analyst` | 1 | read, analyze, export |
| `viewer` | 18 | read only |
| `crop_analyst` | 0 | (reserved for the crop module) |
| `geo_analyst` | 0 | (reserved for the geo module) |

Canonical permission identifiers are declared in the database (`shared.permissions`,
18 rows) and mirrored on the frontend in
`packages/dashboard/src/lib/permissions.ts:3-17` (`PERMISSIONS` constant).

Permission checks are role→permission joins at request time
(`shared.role_permissions` → `get_permissions`, `rbac.py:33`), so an administrator can
re-role a user without restarting anything.

## 3. Access levels for analysis data

`permissions.ts:26-39` maps permissions to a coarse access level used by the UI:

```ts
waterAccessLevel(): 'manager'  if AQUAVISION_MANAGE_DATA
                    'operator' if ACKNOWLEDGE_ALERT or ADD_NOTE
                    'analyst'  if ANALYZE
                    'viewer'   otherwise
canSeeAnalysis()  = level !== 'viewer'      // analysis panels hidden from pure viewers
```

Row-level scoping: `shared.user_region_scopes` (24 rows) restricts users to particular
regions; `get_region_scope` / descendant resolution lives in `rbac.py:56-136`.

## 4. Where enforcement happens

| Layer | Mechanism | Evidence |
|-------|-----------|----------|
| Backend – workflow | `Depends(get_current_user)` on every endpoint | `alert_workflow.py:225+`; 401 without token (live-tested) |
| Backend – governance mutations | `require_permissions(...)` dependency | `registry.py:19, :147, :157, :167`; `auth.py:531` |
| Backend – public read endpoints | intentionally open for demo UX (overview, models list, sensors) | `GET /water/overview` → 200 without token (live-tested) |
| Frontend – route access | unauthenticated users redirected to `/login` | `context/AuthContext.tsx:27, :75-122` |
| Frontend – page/nav visibility | permissions from login response drive navigation groups and analysis panels | `lib/navigation.ts`, `lib/permissions.ts:28-39` |

> Honest note for the defence: authentication is enforced end-to-end on state-changing
> and workflow endpoints; several read-only dashboard endpoints are open by design for
> the demonstration, and role checks on the UI are advisory. This is documented as the
> known trade-off in `12-viva-qa.md`.

## 5. Account lifecycle

`shared.users` carries `is_active`, `access_status`, `access_requested_at`,
`last_login_at` — supporting a request → approve → login flow surfaced at
`/system/access-requests` (nav entry `navigation.ts:107`). Live: 35 accounts, 35 active,
13 with a recorded login.

## 6. Verify live

```powershell
# role/permission matrix
.\scripts\Query-DB.ps1 -Query "SELECT r.name, count(ur.user_id) FROM shared.roles r LEFT JOIN shared.user_roles ur ON ur.role_id=r.id GROUP BY r.name ORDER BY 1;"

# unauthenticated request to a workflow endpoint must be 401
curl.exe -s -o $env:TEMP\q.json -w "%{http_code}" http://localhost:8100/water/alerts/queue

# authenticated request succeeds
.\scripts\Test-API.ps1        # includes GET /water/alerts/queue (200 with JWT)
```

Demo: log in as `admin` (all menus visible) — then, in Swagger, call
`POST /water/alerts/{id}/assign` with and without the bearer token to show 200 vs 401.
