from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models import User
from app.schemas import BalanceResponse


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/balance", response_model=BalanceResponse)
def get_my_balance(current_user: User = Depends(get_current_user)) -> BalanceResponse:
    return BalanceResponse(
        user_id=current_user.id, balance_eur=current_user.balance_cents / 100
    )
