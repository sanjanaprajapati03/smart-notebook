from datetime import datetime, timedelta

import bcrypt
from fastapi.security import OAuth2PasswordBearer
from jose import jwt

from .config import JWT_SECRET_KEY, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")
MAX_BCRYPT_PASSWORD_BYTES = 72


def is_password_too_long(password: str) -> bool:
    return len(password.encode("utf-8")) > MAX_BCRYPT_PASSWORD_BYTES


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    if is_password_too_long(plain_password):
        return False
    try:
        return bcrypt.checkpw(
            _password_bytes(plain_password),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def get_password_hash(password: str) -> str:
    if is_password_too_long(password):
        raise ValueError("Password must be 72 bytes or fewer.")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(_password_bytes(password), salt).decode("utf-8")


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
