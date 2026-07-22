import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# Basic brute-force protection for the login endpoint. Tests disable it via
# RATE_LIMIT_ENABLED=false so repeated logins in fixtures don't trip 429s.
limiter = Limiter(
    key_func=get_remote_address,
    enabled=os.environ.get("RATE_LIMIT_ENABLED", "true").lower() != "false",
)

LOGIN_RATE_LIMIT = os.environ.get("LOGIN_RATE_LIMIT", "10/minute")
