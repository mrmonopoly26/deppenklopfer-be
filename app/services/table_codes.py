import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Table


def generate_unique_game_code(db: Session) -> str:
    for _ in range(100):
        game_code = f"{random.randint(0, 999999):06d}"
        exists = db.scalar(select(Table).where(Table.game_code == game_code))
        if not exists:
            return game_code
    raise RuntimeError("Could not generate unique game code")
