"""PIN-based authentication, JWT, and dependency."""
import logging
import os
import secrets
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Request, Depends

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7


# A literal default here is the same as no signing key at all: this repo is
# public, so anyone could read it and mint a token for any user in any tenant.
# When JWT_SECRET is unset we generate a random one per process instead. That
# fails safe — nobody can forge a token — at the cost of sessions not surviving
# a restart, which is the visible nudge to set the variable properly.
_EPHEMERAL_SECRET = secrets.token_urlsafe(48)
_warned = False


def _secret() -> str:
    global _warned
    env = os.environ.get("JWT_SECRET", "").strip()
    if env:
        return env
    if not _warned:
        _warned = True
        logging.getLogger("madio").warning(
            "JWT_SECRET is not set — using a random per-process key. Tokens will "
            "be invalidated on every restart. Set JWT_SECRET in the environment."
        )
    return _EPHEMERAL_SECRET



def hash_pin(pin: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pin.encode("utf-8"), salt).decode("utf-8")


def verify_pin(pin: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: str, username: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth_header[7:]
    payload = decode_token(token)

    db = request.app.state.db
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "pin_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
