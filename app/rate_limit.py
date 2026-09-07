"""Request rate limiting for the credential endpoints.

Login and registration are the two places an attacker can iterate — guessing
passwords, enumerating emails, or burning CPU on bcrypt hashes — so each is
throttled per client. Everything else is protected by authentication.

Configuration (all optional):

* LOGIN_RATE_LIMIT / REGISTER_RATE_LIMIT — limit strings such as "10/minute";
  validated at import so a typo fails at boot, not on the first login.
* TRUST_PROXY_HEADERS — set to true when the API runs behind a reverse proxy
  or load balancer that sets X-Forwarded-For. Without it, every user behind
  the proxy shares the proxy's address and one bucket; with it set wrongly
  (no proxy in front), a client could spoof the header to dodge the limit.
* RATE_LIMIT_STORAGE_URI — e.g. redis://host:6379; without it counts live
  in process memory, which is fine for one instance and per-replica otherwise.
* RATE_LIMIT_ENABLED=false — disables limiting; the test suite sets this so
  fixtures can log in repeatedly.
"""

import os

from limits import parse as parse_limit
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

TRUST_PROXY_HEADERS = os.environ.get("TRUST_PROXY_HEADERS", "false").lower() == "true"


def client_key(request: Request) -> str:
    """The identity a request is throttled under.

    With TRUST_PROXY_HEADERS, the first address in X-Forwarded-For is the
    original client (proxies append their own address after it). Otherwise,
    and whenever the header is absent, the direct peer address is used.
    """
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return get_remote_address(request)


def _limit_from_env(name: str, default: str) -> str:
    """Read a limit string and prove it parses, so bad config fails at boot."""
    value = os.environ.get(name, default)
    try:
        parse_limit(value)
    except ValueError as exc:
        raise RuntimeError(f"{name}={value!r} is not a valid rate limit (e.g. '10/minute')") from exc
    return value


# 10 login attempts a minute per client is plenty for a person mistyping a
# password and far too few for guessing one.
LOGIN_RATE_LIMIT = _limit_from_env("LOGIN_RATE_LIMIT", "10/minute")

# Registration is throttled harder: each attempt costs a bcrypt hash, and an
# open endpoint that mints accounts is the easiest thing to script against.
REGISTER_RATE_LIMIT = _limit_from_env("REGISTER_RATE_LIMIT", "5/minute")

limiter = Limiter(
    key_func=client_key,
    storage_uri=os.environ.get("RATE_LIMIT_STORAGE_URI", "memory://"),
    enabled=os.environ.get("RATE_LIMIT_ENABLED", "true").lower() != "false",
)
