from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    GameHand,
    HandBid,
    HandCard,
    HandTrick,
    TableParticipant,
    TrickCard,
)
from app.services.schafkopf_rules import (
    CONTRACT_RUFER,
    PHASE_BIDDING,
    PHASE_CLOSED,
    PHASE_PLAYING,
    PHASE_SCORING,
    trump_order,
)

_SUIT_ORDER = {"eichel": 0, "gras": 1, "herz": 2, "schellen": 3}
_RANK_ORDER = {"A": 0, "10": 1, "K": 2, "O": 3, "U": 4, "9": 5}

# ── WebSocket message/event type constants ─────────────────────────────────────

WS_GAME_STATE = "game_state"
WS_GAME_ERROR = "game_error"
WS_LEGAL_BIDS = "legal_bids"
WS_LEGAL_CARDS = "legal_cards"
WS_YOU_ARE_PARTNER = "you_are_partner"
WS_MY_HAND = "my_hand"
WS_PARTICIPANT_JOINED = "participant_joined"
WS_PARTICIPANT_LEFT = "participant_left"
WS_PING = "ping"
WS_PONG = "pong"
WS_CHAT_MESSAGE = "chat_message"
WS_START_HAND = "start_hand"
WS_DECLARE_BID = "declare_bid"
WS_PLAY_CARD = "play_card"

ACTIVE_HAND_PHASES = {PHASE_BIDDING, PHASE_PLAYING, PHASE_SCORING}


def active_hand(db: Session, table_id: str) -> GameHand | None:
    # populate_existing forces SQLAlchemy to refresh from DB rather than returning
    # a stale identity-map entry — critical for long-lived WebSocket sessions where
    # another session may have advanced the hand state since the object was first loaded.
    return db.scalar(
        select(GameHand)
        .where(GameHand.table_id == table_id, GameHand.phase.in_(ACTIVE_HAND_PHASES))
        .order_by(GameHand.hand_number.desc())
        .execution_options(populate_existing=True)
    )


def participants_by_seat(db: Session, table_id: str) -> list[TableParticipant]:
    return db.scalars(
        select(TableParticipant)
        .where(TableParticipant.table_id == table_id)
        .order_by(TableParticipant.seat_number.asc())
    ).all()


def public_state(db: Session, hand: GameHand, participants: list[TableParticipant]) -> dict:
    bids = db.scalars(
        select(HandBid)
        .where(HandBid.hand_id == hand.id)
        .order_by(HandBid.bid_order.asc())
    ).all()

    trick_cards: list[dict] = []
    if hand.phase != PHASE_CLOSED:
        trick = db.scalar(
            select(HandTrick).where(
                HandTrick.hand_id == hand.id,
                HandTrick.trick_index == hand.trick_number,
            )
        )
        if trick:
            cards = db.scalars(
                select(TrickCard)
                .where(TrickCard.trick_id == trick.id)
                .order_by(TrickCard.play_order.asc())
            ).all()
            trick_cards = [
                {
                    "seat_number": c.seat_number,
                    "user_id": c.user_id,
                    "suit": c.suit,
                    "rank": c.rank,
                    "play_order": c.play_order,
                }
                for c in cards
            ]

    completed_trick_rows = db.scalars(
        select(HandTrick)
        .where(HandTrick.hand_id == hand.id, HandTrick.winner_seat.is_not(None))
        .order_by(HandTrick.trick_index.asc())
    ).all()
    completed_tricks: list[dict] = []
    for t in completed_trick_rows:
        t_cards = db.scalars(
            select(TrickCard)
            .where(TrickCard.trick_id == t.id)
            .order_by(TrickCard.play_order.asc())
        ).all()
        completed_tricks.append({
            "trick_index": t.trick_index,
            "winner_seat": t.winner_seat,
            "cards": [
                {"seat_number": c.seat_number, "user_id": c.user_id, "suit": c.suit, "rank": c.rank}
                for c in t_cards
            ],
        })

    # Partner identity is secret in Rufer until the called ace hits the table.
    partner_revealed = hand.contract_type != CONTRACT_RUFER or (
        hand.called_ace_suit is not None
        and db.scalar(
            select(TrickCard).where(
                TrickCard.hand_id == hand.id,
                TrickCard.suit == hand.called_ace_suit,
                TrickCard.rank == "A",
            )
        )
        is not None
    )

    return {
        "type": WS_GAME_STATE,
        "hand_id": hand.id,
        "hand_number": hand.hand_number,
        "phase": hand.phase,
        "dealer_seat": hand.dealer_seat,
        "forehand_seat": hand.forehand_seat,
        "current_turn_seat": hand.current_turn_seat,
        "trick_number": hand.trick_number,
        "contract_type": hand.contract_type,
        "contract_suit": hand.contract_suit,
        "called_ace_suit": hand.called_ace_suit,
        "declarer_user_id": hand.declarer_user_id,
        "partner_user_id": hand.partner_user_id if partner_revealed else None,
        "result": hand.result_json,
        "participants": [
            {
                "user_id": p.user_id,
                "nickname": p.nickname,
                "seat_number": p.seat_number,
            }
            for p in participants
        ],
        "bids": [
            {
                "user_id": bid.user_id,
                "seat_number": bid.seat_number,
                "decision": bid.decision,
                "contract_type": bid.contract_type,
                "contract_suit": bid.contract_suit,
                "called_ace_suit": bid.called_ace_suit,
                "bid_order": bid.bid_order,
            }
            for bid in bids
        ],
        "current_trick": trick_cards,
        "completed_tricks": completed_tricks,
    }


def my_hand_state(db: Session, hand: GameHand, user_id: str) -> list[dict]:
    cards = db.scalars(
        select(HandCard).where(HandCard.hand_id == hand.id, HandCard.user_id == user_id)
    ).all()

    try:
        trump_list = trump_order(hand.contract_type or "", hand.contract_suit)
    except ValueError:
        trump_list = []
    trump_idx = {card: i for i, card in enumerate(trump_list)}

    def sort_key(c: HandCard) -> tuple:
        if (c.suit, c.rank) in trump_idx:
            return (0, trump_idx[(c.suit, c.rank)], 0)
        return (1, _SUIT_ORDER.get(c.suit, 9), _RANK_ORDER.get(c.rank, 9))

    return [
        {"suit": c.suit, "rank": c.rank, "is_played": c.is_played}
        for c in sorted(cards, key=sort_key)
    ]
