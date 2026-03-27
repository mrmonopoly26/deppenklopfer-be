import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.db.session import get_db
from app.models import ChangeRequest, User
from app.schemas import (
    AuthResponse,
    ChangeRequestConfirm,
    ChangeRequestCreate,
    LoginRequest,
    RegisterRequest,
)
from app.services.security import create_access_token, hash_password, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    existing_user = db.scalar(select(User).where(User.email == payload.email))
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already in use"
        )

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    return AuthResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    return AuthResponse(access_token=create_access_token(user.id))


@router.get("/me")
def me(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "id": current_user.id,
        "email": current_user.email,
        "balance_eur": current_user.balance_cents / 100,
    }


@router.post("/change-request")
def create_change_request(
    payload: ChangeRequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(
        hours=settings.change_request_expire_hours
    )

    request = ChangeRequest(
        user_id=current_user.id,
        request_type=payload.request_type,
        token=token,
        expires_at=expires_at,
    )

    if payload.request_type == "email":
        try:
            validated_email = EmailStr(payload.new_value)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email"
            ) from exc

        if db.scalar(select(User).where(User.email == validated_email)):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email already in use"
            )
        request.new_email = str(validated_email)
    else:
        request.new_password_hash = hash_password(payload.new_value)

    db.add(request)
    db.commit()

    return {
        "message": "Change request created",
        "token": token,
        "note": "Simulated mail delivery for MVP: token returned in response",
    }


@router.post("/change-request/confirm")
def confirm_change_request(
    payload: ChangeRequestConfirm, db: Session = Depends(get_db)
) -> dict:
    request = db.scalar(
        select(ChangeRequest).where(ChangeRequest.token == payload.token)
    )
    if not request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Token not found"
        )
    if request.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Token already used"
        )
    if request.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token expired")

    user = db.scalar(select(User).where(User.id == request.user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    if request.request_type == "email":
        if not request.new_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Missing new email"
            )
        user.email = request.new_email
    else:
        if not request.new_password_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Missing new password"
            )
        user.password_hash = request.new_password_hash

    request.used_at = datetime.utcnow()
    db.commit()
    return {"message": "Change applied"}
