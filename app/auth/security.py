"""Password hashing (bcrypt directly) and JWT encode/decode.

We use the `bcrypt` package directly rather than going through `passlib`
because `passlib 1.7.4` (the latest release as of this writing) has not
been updated for `bcrypt 4.x`. Its backend-probe sends a 73-byte test
password through bcrypt and `bcrypt 4.x` raises rather than truncating,
which breaks every passlib bcrypt call. Direct usage avoids the issue.

Note: bcrypt itself only uses the first 72 bytes of the password. We
slice explicitly so a long password doesn't raise — the alternative
(silent truncation inside the library) is what bit passlib.
"""
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import jwt, JWTError

from app.config import settings


_BCRYPT_MAX_BYTES = 72


def _truncate(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_truncate(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_truncate(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, role: str, school_id: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {"sub": user_id, "role": role, "school_id": school_id, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        return None
