# infrastructure/auth/security.py
# Password hashing (bcrypt via passlib). Tokens use infrastructure.auth.jwt.
from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    # bcrypt limit is 72 bytes
    if len(password) > 72:
        password = password[:72]
    return pwd_context.hash(password)
