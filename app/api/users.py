from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import BalanceTransaction, User
from app.schemas import BalanceResponse, TransactionItem


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/balance", response_model=BalanceResponse)
def get_my_balance(current_user: User = Depends(get_current_user)) -> BalanceResponse:
    return BalanceResponse(
        user_id=current_user.id, balance_eur=current_user.balance_cents / 100
    )


@router.get("/me/transactions", response_model=list[TransactionItem])
def get_my_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TransactionItem]:
    rows = db.scalars(
        select(BalanceTransaction)
        .where(BalanceTransaction.user_id == current_user.id)
        .order_by(BalanceTransaction.created_at.desc())
        .limit(limit)
    ).all()
    return [
        TransactionItem(
            id=r.id,
            table_id=r.table_id,
            round_id=r.round_id,
            amount_eur=r.amount_cents / 100,
            reason=r.reason,
            created_at=r.created_at,
        )
        for r in rows
    ]
