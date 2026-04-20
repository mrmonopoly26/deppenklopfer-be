from __future__ import annotations

import random
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BalanceTransaction,
    GameHand,
    GameRound,
    HandCard,
    HandTrick,
    Table,
    TableParticipant,
    TrickCard,
    User,
)
from app.services.schafkopf_rules import build_deck, next_seat
from app.services.schafkopf_scoring import settle_hand


def _seat_to_user(participants: list[TableParticipant]) -> dict[int, str]:
    return {p.seat_number: p.user_id for p in participants}


def _current_hand(db: Session, table_id: str) -> GameHand | None:
    return db.scalar(
        select(GameHand)
        .where(GameHand.table_id == table_id)
        .order_by(GameHand.hand_number.desc())
    )


def start_hand(db: Session, table: Table, participants: list[TableParticipant]) -> GameHand:
    if len(participants) != 4:
        raise ValueError("Exactly 4 participants are required to start a hand")

    previous = _current_hand(db, table.id)
    hand_number = 1 if not previous else previous.hand_number + 1
    dealer_seat = 1 if not previous else next_seat(previous.dealer_seat)
    forehand_seat = next_seat(dealer_seat)

    hand = GameHand(
        table_id=table.id,
        hand_number=hand_number,
        dealer_seat=dealer_seat,
        forehand_seat=forehand_seat,
        phase="bidding",
        current_turn_seat=forehand_seat,
    )
    db.add(hand)
    table.status = "playing"
    db.flush()

    deck = build_deck()
    random.shuffle(deck)

    seat_cycle = [forehand_seat]
    for _ in range(3):
        seat_cycle.append(next_seat(seat_cycle[-1]))

    s2u = _seat_to_user(participants)
    for index, (suit, rank) in enumerate(deck):
        seat = seat_cycle[index % 4]
        db.add(HandCard(
            hand_id=hand.id,
            table_id=table.id,
            user_id=s2u[seat],
            seat_number=seat,
            suit=suit,
            rank=rank,
        ))

    db.flush()
    return hand


def close_and_settle_hand(
    db: Session,
    table: Table,
    hand: GameHand,
    participants: list[TableParticipant],
) -> dict:
    tricks = db.scalars(
        select(HandTrick)
        .where(HandTrick.hand_id == hand.id)
        .order_by(HandTrick.trick_index.asc())
    ).all()

    resolved_tricks: list[tuple[int, list[tuple[int, str, str, str]]]] = []
    for trick in tricks:
        cards = db.scalars(
            select(TrickCard)
            .where(TrickCard.trick_id == trick.id)
            .order_by(TrickCard.play_order.asc())
        ).all()
        resolved_tricks.append((
            trick.winner_seat or 0,
            [(c.seat_number, c.suit, c.rank, c.user_id) for c in cards],
        ))

    initial_hand_cards: dict[str, list[tuple[str, str]]] = {}
    for card in db.scalars(select(HandCard).where(HandCard.hand_id == hand.id)).all():
        initial_hand_cards.setdefault(card.user_id, []).append((card.suit, card.rank))

    base_rate = table.config.euro_per_point_cents
    settlement = settle_hand(
        contract_type=hand.contract_type or "",
        contract_suit=hand.contract_suit,
        declarer_user_id=hand.declarer_user_id,
        partner_user_id=hand.partner_user_id,
        seat_to_user=_seat_to_user(participants),
        tricks=resolved_tricks,
        initial_hand_cards=initial_hand_cards,
        rufer_rate_cents=base_rate,
        solo_wenz_rate_cents=base_rate * 5,
        schneider_bonus_cents=base_rate,
        schwarz_bonus_cents=base_rate * 2,
        laufende_rate_cents=base_rate,
        enable_laufende=True,
    )

    round_entity = GameRound(
        table_id=table.id,
        submitted_by_user_id=hand.declarer_user_id or participants[0].user_id,
        summary=settlement.summary,
        payouts_json=settlement.payouts_cents,
    )
    db.add(round_entity)
    db.flush()

    for user_id, amount_cents in settlement.payouts_cents.items():
        user = db.scalar(select(User).where(User.id == user_id))
        if not user:
            continue
        user.balance_cents += amount_cents
        db.add(BalanceTransaction(
            user_id=user_id,
            table_id=table.id,
            round_id=round_entity.id,
            amount_cents=amount_cents,
            reason=f"auto_{hand.contract_type or 'unknown'}",
        ))

    hand.phase = "closed"
    hand.current_turn_seat = None
    table.status = "waiting"
    hand.result_json = {
        **settlement.details,
        "summary": settlement.summary,
        "round_id": round_entity.id,
        "payouts_cents": settlement.payouts_cents,
    }
    hand.closed_at = datetime.now(UTC)
    return hand.result_json
