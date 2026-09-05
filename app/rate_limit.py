"""Request rate limiting for the credential endpoints.

Limits are keyed by client IP. Behind a reverse proxy that means the proxy's
address unless trusted forwarded-for handling is configured — acceptable for
the current deployment shape, and noted here so it isn't forgotten.
"""

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

# Registration is throttled harder: each attempt costs a bcrypt hash, and an
# open endpoint that mints accounts is the easiest thing to script against.
REGISTER_RATE_LIMIT = os.environ.get("REGISTER_RATE_LIMIT", "5/minute")
