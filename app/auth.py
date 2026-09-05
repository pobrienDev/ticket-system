"""Password hashing and JWT issuance/verification.

Passwords are stored as bcrypt hashes: one-way, individually salted, and
deliberately slow to compute. Sessions are stateless JWTs signed with
JWT_SECRET (HS256); the server verifies a signature instead of looking up
a session row, which is what lets the API scale horizontally without shared
session storage.
"""

import datetime
import os

import bcrypt
import jwt
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.environ.get("JWT_SECRET")  # from .env, never hardcoded
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET is not set. Copy .env.example to .env and set a random secret "
        "(e.g. python -c \"import secrets; print(secrets.token_hex(32))\")."
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))


def hash_password(password: str) -> str:
    # gensalt() produces a fresh random salt per call, so identical passwords
    # never share a hash; the salt is embedded in the returned string.
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:  # malformed stored hash
        return False


def create_access_token(data: dict, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    # Callers pass the claims (the app uses {"sub": user id}); this adds the
    # expiry and signs. Claims are readable by anyone holding the token —
    # a JWT is signed, not encrypted — so nothing sensitive goes in here.
    to_encode = data.copy()
    expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        # Pinning algorithms here prevents algorithm-confusion attacks; PyJWT
        # also verifies the exp claim as part of decode.
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return None
