from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangeRequestCreate(BaseModel):
    request_type: Literal["email", "password"]
    new_value: str = Field(min_length=4, max_length=320)


class ChangeRequestConfirm(BaseModel):
    token: str


class TableConfigPayload(BaseModel):
    game_modes: list[str] = Field(default_factory=lambda: ["rufspiel", "solo", "wenz"])
    euro_per_point: float = Field(default=0.1, ge=0)
    base_reward: float = Field(default=1.0, ge=0)


class TableCreateRequest(BaseModel):
    host_nickname: str = Field(default="Host", min_length=1, max_length=64)
    config: TableConfigPayload


class TableJoinRequest(BaseModel):
    game_code: str = Field(min_length=6, max_length=6)
    nickname: str = Field(min_length=1, max_length=64)


class ParticipantItem(BaseModel):
    user_id: str
    nickname: str
    seat_number: int

    model_config = ConfigDict(from_attributes=True)


class TableResponse(BaseModel):
    id: str
    game_code: str
    host_user_id: str
    status: str
    created_at: datetime
    config: TableConfigPayload
    participants: list[ParticipantItem]


class ChatHistoryItem(BaseModel):
    user_id: str
    nickname: str
    message: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PayoutItem(BaseModel):
    user_id: str
    amount_eur: float | None = None
    points: int | None = None
    reason: str = Field(default="round_payout", min_length=1, max_length=128)


class RoundCompleteRequest(BaseModel):
    summary: str = Field(min_length=1, max_length=2000)
    payouts: list[PayoutItem]


class BalanceResponse(BaseModel):
    user_id: str
    balance_eur: float
