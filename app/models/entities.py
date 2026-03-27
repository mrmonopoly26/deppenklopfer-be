from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    balance_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TableConfig(Base):
    __tablename__ = "table_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_modes: Mapped[list[str]] = mapped_column(JSON, default=list)
    euro_per_point_cents: Mapped[int] = mapped_column(Integer, default=10)
    base_reward_cents: Mapped[int] = mapped_column(Integer, default=100)


class Table(Base):
    __tablename__ = "tables"
    __table_args__ = (
        UniqueConstraint("game_code", name="uq_tables_game_code"),
        CheckConstraint("length(game_code) = 6", name="ck_tables_game_code_len"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    game_code: Mapped[str] = mapped_column(String(6), nullable=False)
    host_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    config_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("table_configs.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="waiting")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    config: Mapped[TableConfig] = relationship()


class TableParticipant(Base):
    __tablename__ = "table_participants"
    __table_args__ = (
        UniqueConstraint("table_id", "user_id", name="uq_table_user"),
        UniqueConstraint("table_id", "seat_number", name="uq_table_seat"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    table_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tables.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    nickname: Mapped[str] = mapped_column(String(64))
    seat_number: Mapped[int] = mapped_column(Integer)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    request_type: Mapped[str] = mapped_column(String(16))
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    new_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    new_password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    table_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tables.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    nickname: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GameRound(Base):
    __tablename__ = "game_rounds"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    table_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tables.id"), index=True
    )
    submitted_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), index=True
    )
    summary: Mapped[str] = mapped_column(Text)
    payouts_json: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BalanceTransaction(Base):
    __tablename__ = "balance_transactions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    table_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tables.id"), index=True
    )
    round_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("game_rounds.id"), index=True
    )
    amount_cents: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
