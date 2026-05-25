import time
import uuid
from fastapi import HTTPException

from .. import state


def require_pg_pool():
    if not state.pg_pool:
        raise HTTPException(status_code=500, detail="Auth database offline.")
    return state.pg_pool


def _row_to_dict(row) -> dict | None:
    return dict(row) if row else None


async def get_user_by_email(email: str) -> dict | None:
    query = """
        SELECT id, email, password_hash, created_at, updated_at
        FROM users
        WHERE email = $1
        LIMIT 1
    """
    row = await require_pg_pool().fetchrow(query, email)
    return _row_to_dict(row)


async def get_user_by_id(user_id: str) -> dict | None:
    query = """
        SELECT id, email, password_hash, created_at, updated_at
        FROM users
        WHERE id = $1
        LIMIT 1
    """
    row = await require_pg_pool().fetchrow(query, user_id)
    return _row_to_dict(row)


async def create_user(email: str, password_hash: str) -> dict:
    now = int(time.time())
    user_id = str(uuid.uuid4())
    query = """
        INSERT INTO users (id, email, password_hash, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id, email, password_hash, created_at, updated_at
    """
    row = await require_pg_pool().fetchrow(
        query,
        user_id,
        email,
        password_hash,
        now,
        now,
    )
    user = _row_to_dict(row)
    if not user:
        raise HTTPException(status_code=500, detail="Failed to create user.")
    return user
