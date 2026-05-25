from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel

from ..core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    is_password_too_long,
)
from ..services.users import get_user_by_email, create_user
from ..dependencies import get_current_user

router = APIRouter()


class UserRegisterRequest(BaseModel):
    email: str
    password: str


class UserLoginRequest(BaseModel):
    email: str
    password: str


class UserPublic(BaseModel):
    id: str
    email: str
    created_at: int | None = None
    updated_at: int | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


def user_public_from_record(record: dict) -> dict:
    return {
        "id": record.get("id"),
        "email": record.get("email"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register_user(payload: UserRegisterRequest):
    existing = await get_user_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered.")
    if is_password_too_long(payload.password):
        raise HTTPException(
            status_code=400,
            detail="Password must be 72 bytes or fewer.",
        )

    user = await create_user(
        email=payload.email,
        password_hash=get_password_hash(payload.password),
    )
    access_token = create_access_token(user_id=user["id"], email=user["email"])
    return TokenResponse(
        access_token=access_token,
        user=UserPublic(**user_public_from_record(user)),
    )


@router.post("/login", response_model=TokenResponse)
async def login_user(payload: UserLoginRequest):
    user = await get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(user_id=user["id"], email=user["email"])
    return TokenResponse(
        access_token=access_token,
        user=UserPublic(**user_public_from_record(user)),
    )


@router.get("/me", response_model=UserPublic)
async def read_current_user(current_user: dict = Depends(get_current_user)):
    return UserPublic(**user_public_from_record(current_user))
