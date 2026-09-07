"""Password hashing and JWT issuance/verification.

Passwords are stored as bcrypt hashes: one-way, individually salted, and
deliberately slow to compute. Sessions are stateless JWTs signed with
JWT_SECRET (HS256); the server verifies a signature instead of looking up
a session row, which is what lets the API scale horizontally without shared
session storage.

This module has no knowledge of users or the database. It turns a password
into a hash (and back into a yes/no), and a set of claims into a token (and
back into claims). Everything else — which user, which permissions — is
decided by the caller.
"""

import datetime
import os

import bcrypt
import jwt
from dotenv import load_dotenv

load_dotenv()

# bcrypt hashes only the first 72 bytes of input. The API caps passwords so
# they can never exceed this (see schemas.UserCreate); the constant lives
# here because it is a property of the hashing algorithm, not of the API.
BCRYPT_MAX_PASSWORD_BYTES = 72

# HMAC-SHA256 keys shorter than the hash output (32 bytes) weaken the
# signature; RFC 7518 §3.2 requires at least that much.
MIN_SECRET_BYTES = 32

SECRET_KEY = os.environ.get("JWT_SECRET")  # from .env, never hardcoded
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET is not set. Copy .env.example to .env and set a random secret "
        "(e.g. python -c \"import secrets; print(secrets.token_hex(32))\")."
    )
if len(SECRET_KEY.encode()) < MIN_SECRET_BYTES:
    # Fail at boot rather than run with a weak key and a library warning
    # nobody reads. secrets.token_hex(32) yields 64 characters, well past this.
    raise RuntimeError(f"JWT_SECRET must be at least {MIN_SECRET_BYTES} bytes long.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))


def hash_password(password: str) -> str:
    """Return a bcrypt hash of `password`, safe to store.

    gensalt() produces a fresh random salt per call, so identical passwords
    never share a hash; the salt (and the cost factor) are embedded in the
    returned string, which is why verify_password needs nothing else.
    Callers must have enforced BCRYPT_MAX_PASSWORD_BYTES: bcrypt raises on
    longer input rather than silently truncating.
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Check `plain` against a stored bcrypt hash.

    Constant-time comparison inside bcrypt. Any malformed input — a corrupt
    stored hash, or a candidate over the byte limit — is simply a failed
    check, never an exception that could turn a login attempt into a 500.
    """
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(data: dict, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    """Sign `data` (the app passes {"sub": user id}) into a JWT.

    Adds the standard `iat` (issued at) and `exp` (expiry) claims and signs
    with HS256. A JWT is signed, not encrypted: anyone holding the token can
    read the claims, so nothing sensitive belongs in `data`. `expires_minutes`
    is a parameter so tests can mint an already-expired token.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    to_encode = data.copy()
    to_encode.update({"iat": now, "exp": now + datetime.timedelta(minutes=expires_minutes)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Verify a JWT and return its claims, or None if it is not acceptable.

    None covers every failure — bad signature, expired, malformed, missing
    required claims — so the caller (get_current_user) has one branch: 401.
    Pinning `algorithms` prevents algorithm-confusion attacks where a token
    names its own (weaker or absent) algorithm; requiring `exp` and `sub`
    means a token can never be accepted without an expiry or an identity.
    """
    try:
        return jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None
