from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class GameHand(Base):
    __tablename__ = "game_hands"
    __table_args__ = (
        UniqueConstraint("table_id", "hand_number", name="uq_game_hands_table_number"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    table_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tables.id"), index=True
    )
    hand_number: Mapped[int] = mapped_column(Integer)
    dealer_seat: Mapped[int] = mapped_column(Integer)
    forehand_seat: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(32), default="bidding")
    contract_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    contract_suit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    called_ace_suit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    declarer_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    partner_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    current_turn_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trick_number: Mapped[int] = mapped_column(Integer, default=1)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class HandCard(Base):
    __tablename__ = "hand_cards"
    __table_args__ = (
        UniqueConstraint(
            "hand_id",
            "user_id",
            "suit",
            "rank",
            name="uq_hand_cards_hand_user_card",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hand_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("game_hands.id"), index=True
    )
    table_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tables.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    seat_number: Mapped[int] = mapped_column(Integer)
    suit: Mapped[str] = mapped_column(String(16))
    rank: Mapped[str] = mapped_column(String(4))
    is_played: Mapped[bool] = mapped_column(Boolean, default=False)


class HandBid(Base):
    __tablename__ = "hand_bids"
    __table_args__ = (
        UniqueConstraint("hand_id", "user_id", name="uq_hand_bids_hand_user"),
        UniqueConstraint("hand_id", "bid_order", name="uq_hand_bids_hand_order"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hand_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("game_hands.id"), index=True
    )
    table_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tables.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    seat_number: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(16))
    contract_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    contract_suit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    called_ace_suit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bid_order: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class HandTrick(Base):
    __tablename__ = "hand_tricks"
    __table_args__ = (
        UniqueConstraint("hand_id", "trick_index", name="uq_hand_tricks_hand_index"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    hand_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("game_hands.id"), index=True
    )
    table_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tables.id"), index=True
    )
    trick_index: Mapped[int] = mapped_column(Integer)
    lead_seat: Mapped[int] = mapped_column(Integer)
    winner_seat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TrickCard(Base):
    __tablename__ = "trick_cards"
    __table_args__ = (
        UniqueConstraint("trick_id", "seat_number", name="uq_trick_cards_trick_seat"),
        UniqueConstraint("trick_id", "play_order", name="uq_trick_cards_trick_order"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    trick_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("hand_tricks.id"), index=True
    )
    hand_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("game_hands.id"), index=True
    )
    table_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tables.id"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    seat_number: Mapped[int] = mapped_column(Integer)
    play_order: Mapped[int] = mapped_column(Integer)
    suit: Mapped[str] = mapped_column(String(16))
    rank: Mapped[str] = mapped_column(String(4))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
