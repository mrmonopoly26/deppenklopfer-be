from __future__ import annotations

from datetime import UTC, datetime

from fastapi import WebSocket
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.ws_state import public_state
from app.models import (
    GameHand,
    HandBid,
    HandCard,
    HandTrick,
    Table,
    TableParticipant,
    TrickCard,
    User,
)
from app.services.hand_service import close_and_settle_hand
from app.services.schafkopf_rules import (
    contract_rank,
    legal_cards,
    next_seat,
    normalize_rank,
    normalize_suit,
    trick_winner,
)
from app.services.ws_manager import manager


async def handle_declare_bid(
    db: Session,
    table: Table,
    hand: GameHand,
    user: User,
    participant: TableParticipant,
    participants: list[TableParticipant],
    payload: dict,
    websocket: WebSocket,
) -> None:
    if hand.phase != "bidding":
        await websocket.send_json({"type": "game_error", "message": "No bidding in progress"})
        return
    if participant.seat_number != hand.current_turn_seat:
        await websocket.send_json({"type": "game_error", "message": "Not your bidding turn"})
        return

    already_bid = db.scalar(
        select(HandBid).where(HandBid.hand_id == hand.id, HandBid.user_id == user.id)
    )
    if already_bid:
        await websocket.send_json({"type": "game_error", "message": "You already submitted a bid"})
        return

    decision = str(payload.get("decision", "pass")).strip().lower()
    contract_type = payload.get("contract_type")
    contract_suit = payload.get("contract_suit")
    called_ace_suit = payload.get("called_ace_suit")

    try:
        if decision == "play":
            if contract_type not in {"rufer", "solo", "wenz"}:
                raise ValueError("Invalid contract_type")
            contract_to_mode = {"rufer": "rufspiel", "solo": "solo", "wenz": "wenz"}
            if contract_to_mode[contract_type] not in (table.config.game_modes or []):
                raise ValueError(f"{contract_type} is not enabled at this table")
            if contract_type == "solo":
                if not contract_suit:
                    raise ValueError("Solo requires contract_suit")
                contract_suit = normalize_suit(str(contract_suit))
            else:
                contract_suit = None

            if contract_type == "rufer":
                if not called_ace_suit:
                    raise ValueError("Rufer requires called_ace_suit")
                called_ace_suit = normalize_suit(str(called_ace_suit))
                if called_ace_suit == "herz":
                    raise ValueError("Called ace suit cannot be herz")
                my_cards = db.scalars(
                    select(HandCard).where(HandCard.hand_id == hand.id, HandCard.user_id == user.id)
                ).all()
                if any(c.suit == called_ace_suit and c.rank == "A" for c in my_cards):
                    raise ValueError("You cannot call an ace that you hold")
                if not any(c.suit == called_ace_suit and c.rank not in {"O", "U", "A"} for c in my_cards):
                    raise ValueError("Rufer requires at least one non-lord card in called suit")
            else:
                called_ace_suit = None
        else:
            decision, contract_type, contract_suit, called_ace_suit = "pass", None, None, None

        bid_order = (
            db.scalar(
                select(func.count()).select_from(HandBid).where(HandBid.hand_id == hand.id)
            ) or 0
        ) + 1
        db.add(HandBid(
            hand_id=hand.id,
            table_id=table.id,
            user_id=user.id,
            seat_number=participant.seat_number,
            decision=decision,
            contract_type=contract_type,
            contract_suit=contract_suit,
            called_ace_suit=called_ace_suit,
            bid_order=bid_order,
        ))
        db.flush()

        all_bids = db.scalars(
            select(HandBid).where(HandBid.hand_id == hand.id).order_by(HandBid.bid_order.asc())
        ).all()

        if len(all_bids) < 4:
            hand.current_turn_seat = next_seat(hand.current_turn_seat or participant.seat_number)
            db.commit()
            await manager.broadcast(table.id, public_state(db, hand, participants))
            return

        play_bids = [b for b in all_bids if b.decision == "play" and b.contract_type]
        if not play_bids:
            if "ramsch" in (table.config.game_modes or []):
                hand.phase = "playing"
                hand.contract_type = "ramsch"
                hand.contract_suit = None
                hand.called_ace_suit = None
                hand.declarer_user_id = None
                hand.partner_user_id = None
                hand.current_turn_seat = hand.forehand_seat
            else:
                hand.phase = "closed"
                hand.current_turn_seat = None
                hand.result_json = {"type": "skipped_all_pass"}
                hand.closed_at = datetime.now(UTC)
                table.status = "waiting"
        else:
            winning_bid = sorted(
                play_bids,
                key=lambda b: (-contract_rank(b.contract_type or ""), b.bid_order),
            )[0]
            hand.phase = "playing"
            hand.contract_type = winning_bid.contract_type
            hand.contract_suit = winning_bid.contract_suit
            hand.called_ace_suit = winning_bid.called_ace_suit
            hand.declarer_user_id = winning_bid.user_id
            hand.current_turn_seat = hand.forehand_seat

            if winning_bid.contract_type == "rufer" and winning_bid.called_ace_suit:
                partner_card = db.scalar(
                    select(HandCard).where(
                        HandCard.hand_id == hand.id,
                        HandCard.suit == winning_bid.called_ace_suit,
                        HandCard.rank == "A",
                    )
                )
                hand.partner_user_id = partner_card.user_id if partner_card else None
            else:
                hand.partner_user_id = None

        db.commit()
        await manager.broadcast(table.id, public_state(db, hand, participants))

        if hand.contract_type == "rufer" and hand.partner_user_id:
            await manager.send_to_user(table.id, hand.partner_user_id, {
                "type": "you_are_partner",
                "hand_id": hand.id,
                "called_ace_suit": hand.called_ace_suit,
            })
    except ValueError as exc:
        db.rollback()
        await websocket.send_json({"type": "game_error", "message": str(exc)})


async def handle_legal_cards(
    db: Session,
    hand: GameHand,
    user: User,
    websocket: WebSocket,
) -> None:
    if hand.phase != "playing":
        await websocket.send_json({"type": "legal_cards", "cards": [], "message": "No active play"})
        return

    my_cards = db.scalars(
        select(HandCard).where(
            HandCard.hand_id == hand.id,
            HandCard.user_id == user.id,
            HandCard.is_played.is_(False),
        )
    ).all()
    card_tuples = [(c.suit, c.rank) for c in my_cards]

    trick = db.scalar(
        select(HandTrick).where(
            HandTrick.hand_id == hand.id,
            HandTrick.trick_index == hand.trick_number,
        )
    )
    lead_card = None
    if trick:
        lead = db.scalar(
            select(TrickCard).where(TrickCard.trick_id == trick.id).order_by(TrickCard.play_order.asc())
        )
        if lead:
            lead_card = (lead.suit, lead.rank)

    legal = legal_cards(card_tuples, lead_card, hand.contract_type or "", hand.contract_suit)
    await websocket.send_json({
        "type": "legal_cards",
        "hand_id": hand.id,
        "cards": [{"suit": s, "rank": r} for s, r in legal],
    })


async def handle_play_card(
    db: Session,
    table: Table,
    hand: GameHand,
    user: User,
    participant: TableParticipant,
    participants: list[TableParticipant],
    payload: dict,
    websocket: WebSocket,
) -> None:
    if hand.phase != "playing":
        await websocket.send_json({"type": "game_error", "message": "No active hand to play"})
        return
    if participant.seat_number != hand.current_turn_seat:
        await websocket.send_json({"type": "game_error", "message": "Not your turn"})
        return

    try:
        suit = normalize_suit(str(payload.get("suit", "")))
        rank = normalize_rank(str(payload.get("rank", "")))
    except ValueError as exc:
        await websocket.send_json({"type": "game_error", "message": str(exc)})
        return

    my_cards = db.scalars(
        select(HandCard).where(
            HandCard.hand_id == hand.id,
            HandCard.user_id == user.id,
            HandCard.is_played.is_(False),
        )
    ).all()
    card_tuples = [(c.suit, c.rank) for c in my_cards]

    if (suit, rank) not in set(card_tuples):
        await websocket.send_json({"type": "game_error", "message": "Card not in your hand or already played"})
        return

    trick = db.scalar(
        select(HandTrick).where(HandTrick.hand_id == hand.id, HandTrick.trick_index == hand.trick_number)
    )
    lead_card = None
    if trick:
        first = db.scalar(
            select(TrickCard).where(TrickCard.trick_id == trick.id).order_by(TrickCard.play_order.asc())
        )
        if first:
            lead_card = (first.suit, first.rank)

    allowed = legal_cards(card_tuples, lead_card, hand.contract_type or "", hand.contract_suit)
    if (suit, rank) not in set(allowed):
        await websocket.send_json({
            "type": "game_error",
            "message": "Illegal card for current trick",
            "legal_cards": [{"suit": s, "rank": r} for s, r in allowed],
        })
        return

    if not trick:
        trick = HandTrick(
            hand_id=hand.id,
            table_id=table.id,
            trick_index=hand.trick_number,
            lead_seat=participant.seat_number,
        )
        db.add(trick)
        db.flush()

    play_order = (
        db.scalar(
            select(func.count()).select_from(TrickCard).where(TrickCard.trick_id == trick.id)
        ) or 0
    ) + 1
    db.add(TrickCard(
        trick_id=trick.id,
        hand_id=hand.id,
        table_id=table.id,
        user_id=user.id,
        seat_number=participant.seat_number,
        play_order=play_order,
        suit=suit,
        rank=rank,
    ))
    next(c for c in my_cards if c.suit == suit and c.rank == rank).is_played = True
    db.flush()

    if play_order < 4:
        hand.current_turn_seat = next_seat(participant.seat_number)
        db.commit()
        await manager.broadcast(table.id, public_state(db, hand, participants))
        return

    all_trick_cards = db.scalars(
        select(TrickCard).where(TrickCard.trick_id == trick.id).order_by(TrickCard.play_order.asc())
    ).all()
    winner_seat = trick_winner(
        [(c.seat_number, c.suit, c.rank) for c in all_trick_cards],
        hand.contract_type or "",
        hand.contract_suit,
    )
    trick.winner_seat = winner_seat

    if hand.trick_number >= 8:
        close_and_settle_hand(db, table, hand, participants)
        db.commit()
        await manager.broadcast(table.id, public_state(db, hand, participants))
        return

    hand.trick_number += 1
    hand.current_turn_seat = winner_seat
    db.commit()
    await manager.broadcast(table.id, public_state(db, hand, participants))
