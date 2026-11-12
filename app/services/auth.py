"""Password hashing and session-cookie signing for normal (real-login) mode.

Stdlib only, per CLAUDE.md -- no new dependency for this. PBKDF2-HMAC-SHA256
with a per-user random salt is the standard "no extra library" choice
(it's literally what Django's PBKDF2 hasher does under the hood).
"""

import hashlib
import hmac
import secrets

from app.config import settings

PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"{PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        iterations_str, salt, expected_hex = stored.split("$")
        iterations = int(iterations_str)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return hmac.compare_digest(digest.hex(), expected_hex)


def sign_session(user_id: int) -> str:
    """Builds a tamper-evident cookie value: "<user_id>.<hmac>"."""
    payload = str(user_id)
    signature = hmac.new(settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify_session(cookie_value: str | None) -> int | None:
    """Returns the user id if the cookie is well-formed and the signature matches."""
    if not cookie_value or "." not in cookie_value:
        return None
    payload, _, signature = cookie_value.partition(".")
    expected = hmac.new(settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        return int(payload)
    except ValueError:
        return None
