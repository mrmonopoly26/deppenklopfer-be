from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import (
    BalanceTransaction,
    ChatMessage,
    GameRound,
    Table,
    TableConfig,
    TableParticipant,
    User,
)
from app.schemas import (
    ChatHistoryItem,
    RoundCompleteRequest,
    TableConfigPayload,
    TableCreateRequest,
    TableJoinRequest,
    TableResponse,
)
from app.services.table_codes import generate_unique_game_code


router = APIRouter(prefix="/tables", tags=["tables"])


def _table_response(db: Session, table: Table) -> TableResponse:
    participants = db.scalars(
        select(TableParticipant)
        .where(TableParticipant.table_id == table.id)
        .order_by(TableParticipant.seat_number.asc())
    ).all()

    config = TableConfigPayload(
        game_modes=table.config.game_modes,
        euro_per_point=table.config.euro_per_point_cents / 100,
        base_reward=table.config.base_reward_cents / 100,
    )
    return TableResponse(
        id=table.id,
        game_code=table.game_code,
        host_user_id=table.host_user_id,
        status=table.status,
        created_at=table.created_at,
        config=config,
        participants=participants,
    )


@router.post("", response_model=TableResponse)
def create_table(
    payload: TableCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TableResponse:
    config = TableConfig(
        game_modes=payload.config.game_modes,
        euro_per_point_cents=round(payload.config.euro_per_point * 100),
        base_reward_cents=round(payload.config.base_reward * 100),
    )
    db.add(config)
    db.flush()

    table = Table(
        game_code=generate_unique_game_code(db),
        host_user_id=current_user.id,
        config_id=config.id,
    )
    db.add(table)
    db.flush()

    participant = TableParticipant(
        table_id=table.id,
        user_id=current_user.id,
        nickname=payload.host_nickname,
        seat_number=1,
    )
    db.add(participant)

    db.commit()
    db.refresh(table)
    return _table_response(db, table)


@router.post("/join", response_model=TableResponse)
def join_table(
    payload: TableJoinRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TableResponse:
    table = db.scalar(select(Table).where(Table.game_code == payload.game_code))
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Table not found"
        )

    existing_participant = db.scalar(
        select(TableParticipant).where(
            TableParticipant.table_id == table.id,
            TableParticipant.user_id == current_user.id,
        )
    )
    if existing_participant:
        existing_participant.nickname = payload.nickname
        db.commit()
        return _table_response(db, table)

    participants = db.scalars(
        select(TableParticipant).where(TableParticipant.table_id == table.id)
    ).all()
    if len(participants) >= 4:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Table is full"
        )

    occupied = {participant.seat_number for participant in participants}
    seat_number = next((seat for seat in range(1, 5) if seat not in occupied), None)
    if seat_number is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No free seat")

    participant = TableParticipant(
        table_id=table.id,
        user_id=current_user.id,
        nickname=payload.nickname,
        seat_number=seat_number,
    )
    db.add(participant)
    db.commit()
    return _table_response(db, table)


@router.get("/{game_code}", response_model=TableResponse)
def get_table(
    game_code: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> TableResponse:
    table = db.scalar(select(Table).where(Table.game_code == game_code))
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Table not found"
        )
    return _table_response(db, table)


@router.patch("/{game_code}/config", response_model=TableResponse)
def update_table_config(
    game_code: str,
    payload: TableConfigPayload,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TableResponse:
    table = db.scalar(select(Table).where(Table.game_code == game_code))
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Table not found"
        )
    if table.host_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only host may update table config",
        )

    table.config.game_modes = payload.game_modes
    table.config.euro_per_point_cents = round(payload.euro_per_point * 100)
    table.config.base_reward_cents = round(payload.base_reward * 100)
    db.commit()
    return _table_response(db, table)


@router.get("/{game_code}/chat", response_model=list[ChatHistoryItem])
def get_chat_history(
    game_code: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ChatHistoryItem]:
    table = db.scalar(select(Table).where(Table.game_code == game_code))
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Table not found"
        )

    messages = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.table_id == table.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    ).all()
    messages.reverse()
    return [ChatHistoryItem.model_validate(message) for message in messages]


@router.post("/{game_code}/rounds/complete")
def complete_round(
    game_code: str,
    payload: RoundCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    table = db.scalar(select(Table).where(Table.game_code == game_code))
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Table not found"
        )

    participant = db.scalar(
        select(TableParticipant).where(
            TableParticipant.table_id == table.id,
            TableParticipant.user_id == current_user.id,
        )
    )
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only table participants may submit rounds",
        )

    payouts: dict[str, int] = {}
    euro_per_point_cents = table.config.euro_per_point_cents
    base_reward_cents = table.config.base_reward_cents

    for payout_item in payload.payouts:
        if payout_item.amount_eur is None and payout_item.points is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each payout needs amount_eur or points",
            )

        if payout_item.amount_eur is not None:
            amount_cents = round(payout_item.amount_eur * 100)
        else:
            points = payout_item.points or 0
            amount_cents = points * euro_per_point_cents
            if points > 0:
                amount_cents += base_reward_cents
            elif points < 0:
                amount_cents -= base_reward_cents

        payouts[payout_item.user_id] = amount_cents

    game_round = GameRound(
        table_id=table.id,
        submitted_by_user_id=current_user.id,
        summary=payload.summary,
        payouts_json=payouts,
    )
    db.add(game_round)
    db.flush()

    for payout_item in payload.payouts:
        user = db.scalar(select(User).where(User.id == payout_item.user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown user: {payout_item.user_id}",
            )

        amount_cents = payouts[payout_item.user_id]
        user.balance_cents += amount_cents
        transaction = BalanceTransaction(
            user_id=user.id,
            table_id=table.id,
            round_id=game_round.id,
            amount_cents=amount_cents,
            reason=payout_item.reason,
        )
        db.add(transaction)

    db.commit()
    return {"message": "Round recorded", "round_id": game_round.id}
