from datetime import UTC, datetime
import random

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    BalanceTransaction,
    ChatMessage,
    GameHand,
    GameRound,
    HandBid,
    HandCard,
    HandTrick,
    Table,
    TableParticipant,
    TrickCard,
    User,
)
from app.services.schafkopf_rules import (
    build_deck,
    contract_rank,
    legal_cards,
    next_seat,
    normalize_rank,
    normalize_suit,
    trick_winner,
)
from app.services.schafkopf_scoring import settle_hand
from app.services.security import decode_access_token
from app.services.ws_manager import manager


router = APIRouter(tags=["ws"])


ACTIVE_HAND_PHASES = {"bidding", "playing", "scoring"}


def _current_hand(db, table_id: str) -> GameHand | None:
    return db.scalar(
        select(GameHand)
        .where(GameHand.table_id == table_id)
        .order_by(GameHand.hand_number.desc())
    )


def _active_hand(db, table_id: str) -> GameHand | None:
    return db.scalar(
        select(GameHand)
        .where(GameHand.table_id == table_id, GameHand.phase.in_(ACTIVE_HAND_PHASES))
        .order_by(GameHand.hand_number.desc())
    )


def _participants_by_seat(db, table_id: str) -> list[TableParticipant]:
    return db.scalars(
        select(TableParticipant)
        .where(TableParticipant.table_id == table_id)
        .order_by(TableParticipant.seat_number.asc())
    ).all()


def _seat_to_user(participants: list[TableParticipant]) -> dict[int, str]:
    return {
        participant.seat_number: participant.user_id for participant in participants
    }


def _start_hand(db, table: Table, participants: list[TableParticipant]) -> GameHand:
    if len(participants) != 4:
        raise ValueError("Exactly 4 participants are required to start a hand")

    previous_hand = _current_hand(db, table.id)
    hand_number = 1 if not previous_hand else previous_hand.hand_number + 1
    dealer_seat = 1 if not previous_hand else next_seat(previous_hand.dealer_seat)
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
    db.flush()

    deck = build_deck()
    random.shuffle(deck)

    seat_cycle = [forehand_seat]
    for _ in range(3):
        seat_cycle.append(next_seat(seat_cycle[-1]))

    seat_to_user = _seat_to_user(participants)
    for index, (suit, rank) in enumerate(deck):
        seat = seat_cycle[index % 4]
        db.add(
            HandCard(
                hand_id=hand.id,
                table_id=table.id,
                user_id=seat_to_user[seat],
                seat_number=seat,
                suit=suit,
                rank=rank,
            )
        )

    db.flush()
    return hand


def _public_state(db, hand: GameHand, participants: list[TableParticipant]) -> dict:
    bids = db.scalars(
        select(HandBid)
        .where(HandBid.hand_id == hand.id)
        .order_by(HandBid.bid_order.asc())
    ).all()

    trick = db.scalar(
        select(HandTrick).where(
            HandTrick.hand_id == hand.id,
            HandTrick.trick_index == hand.trick_number,
        )
    )
    trick_cards: list[dict] = []
    if trick:
        cards = db.scalars(
            select(TrickCard)
            .where(TrickCard.trick_id == trick.id)
            .order_by(TrickCard.play_order.asc())
        ).all()
        trick_cards = [
            {
                "seat_number": card.seat_number,
                "user_id": card.user_id,
                "suit": card.suit,
                "rank": card.rank,
                "play_order": card.play_order,
            }
            for card in cards
        ]

    return {
        "type": "game_state",
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
        "partner_user_id": hand.partner_user_id,
        "result": hand.result_json,
        "participants": [
            {
                "user_id": participant.user_id,
                "nickname": participant.nickname,
                "seat_number": participant.seat_number,
            }
            for participant in participants
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
    }


def _my_hand_state(db, hand_id: str, user_id: str) -> list[dict]:
    cards = db.scalars(
        select(HandCard)
        .where(HandCard.hand_id == hand_id, HandCard.user_id == user_id)
        .order_by(HandCard.suit.asc(), HandCard.rank.asc())
    ).all()
    return [
        {
            "suit": card.suit,
            "rank": card.rank,
            "is_played": card.is_played,
        }
        for card in cards
    ]


def _close_and_settle_hand(
    db,
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
        resolved_tricks.append(
            (
                trick.winner_seat or 0,
                [
                    (card.seat_number, card.suit, card.rank, card.user_id)
                    for card in cards
                ],
            )
        )

    initial_hand_cards: dict[str, list[tuple[str, str]]] = {}
    all_cards = db.scalars(select(HandCard).where(HandCard.hand_id == hand.id)).all()
    for card in all_cards:
        initial_hand_cards.setdefault(card.user_id, []).append((card.suit, card.rank))

    settlement = settle_hand(
        contract_type=hand.contract_type or "",
        contract_suit=hand.contract_suit,
        declarer_user_id=hand.declarer_user_id,
        partner_user_id=hand.partner_user_id,
        seat_to_user=_seat_to_user(participants),
        tricks=resolved_tricks,
        initial_hand_cards=initial_hand_cards,
        rufer_rate_cents=10,
        solo_wenz_rate_cents=50,
        schneider_bonus_cents=10,
        schwarz_bonus_cents=20,
        laufende_rate_cents=10,
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
        db.add(
            BalanceTransaction(
                user_id=user_id,
                table_id=table.id,
                round_id=round_entity.id,
                amount_cents=amount_cents,
                reason=f"auto_{hand.contract_type or 'unknown'}",
            )
        )

    hand.phase = "closed"
    hand.current_turn_seat = None
    hand.result_json = {
        **settlement.details,
        "summary": settlement.summary,
        "round_id": round_entity.id,
        "payouts_cents": settlement.payouts_cents,
    }
    hand.closed_at = datetime.now(UTC)

    return hand.result_json


@router.websocket("/ws/tables/{game_code}")
async def table_stream(websocket: WebSocket, game_code: str, token: str) -> None:
    user_id = decode_access_token(token)
    if not user_id:
        await websocket.close(code=1008)
        return

    db = SessionLocal()
    table_id: str | None = None
    try:
        user = db.scalar(select(User).where(User.id == user_id))
        table = db.scalar(select(Table).where(Table.game_code == game_code))
        if not user or not table:
            await websocket.close(code=1008)
            return

        participant = db.scalar(
            select(TableParticipant).where(
                TableParticipant.table_id == table.id,
                TableParticipant.user_id == user.id,
            )
        )
        if not participant:
            await websocket.close(code=1008)
            return

        table_id = table.id

        await manager.connect(table.id, websocket)
        await manager.broadcast(
            table.id,
            {
                "type": "participant_joined",
                "user_id": user.id,
                "nickname": participant.nickname,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        while True:
            payload = await websocket.receive_json()
            event_type = payload.get("type")
            if event_type == "chat_message":
                text = str(payload.get("message", "")).strip()
                if not text:
                    continue

                chat_message = ChatMessage(
                    table_id=table.id,
                    user_id=user.id,
                    nickname=participant.nickname,
                    message=text,
                )
                db.add(chat_message)
                db.commit()

                await manager.broadcast(
                    table.id,
                    {
                        "type": "chat_message",
                        "user_id": user.id,
                        "nickname": participant.nickname,
                        "message": text,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
            elif event_type == "game_action":
                await manager.broadcast(
                    table.id,
                    {
                        "type": "game_action",
                        "user_id": user.id,
                        "nickname": participant.nickname,
                        "action": payload.get("action"),
                        "payload": payload.get("payload", {}),
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
            elif event_type == "start_hand":
                participants = _participants_by_seat(db, table.id)
                active = _active_hand(db, table.id)
                if active:
                    await websocket.send_json(
                        {
                            "type": "game_error",
                            "message": "A hand is already active",
                            "state": _public_state(db, active, participants),
                        }
                    )
                    continue

                try:
                    hand = _start_hand(db, table, participants)
                    db.commit()
                    await manager.broadcast(
                        table.id, _public_state(db, hand, participants)
                    )
                except ValueError as exc:
                    db.rollback()
                    await websocket.send_json(
                        {"type": "game_error", "message": str(exc)}
                    )
            elif event_type == "my_hand":
                hand = _active_hand(db, table.id)
                if not hand:
                    await websocket.send_json(
                        {"type": "my_hand", "cards": [], "message": "No active hand"}
                    )
                    continue

                await websocket.send_json(
                    {
                        "type": "my_hand",
                        "hand_id": hand.id,
                        "cards": _my_hand_state(db, hand.id, user.id),
                    }
                )
            elif event_type == "declare_bid":
                hand = _active_hand(db, table.id)
                participants = _participants_by_seat(db, table.id)
                if not hand or hand.phase != "bidding":
                    await websocket.send_json(
                        {"type": "game_error", "message": "No bidding in progress"}
                    )
                    continue
                if participant.seat_number != hand.current_turn_seat:
                    await websocket.send_json(
                        {"type": "game_error", "message": "Not your bidding turn"}
                    )
                    continue

                already_bid = db.scalar(
                    select(HandBid).where(
                        HandBid.hand_id == hand.id, HandBid.user_id == user.id
                    )
                )
                if already_bid:
                    await websocket.send_json(
                        {"type": "game_error", "message": "You already submitted a bid"}
                    )
                    continue

                decision = str(payload.get("decision", "pass")).strip().lower()
                contract_type = payload.get("contract_type")
                contract_suit = payload.get("contract_suit")
                called_ace_suit = payload.get("called_ace_suit")

                try:
                    if decision == "play":
                        if contract_type not in {"rufer", "solo", "wenz"}:
                            raise ValueError("Invalid contract_type")
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
                                select(HandCard).where(
                                    HandCard.hand_id == hand.id,
                                    HandCard.user_id == user.id,
                                )
                            ).all()
                            if any(
                                card.suit == called_ace_suit and card.rank == "A"
                                for card in my_cards
                            ):
                                raise ValueError("You cannot call an ace that you hold")
                            if not any(
                                card.suit == called_ace_suit
                                and card.rank not in {"O", "U", "A"}
                                for card in my_cards
                            ):
                                raise ValueError(
                                    "Rufer requires at least one non-lord card in called suit"
                                )
                        else:
                            called_ace_suit = None
                    else:
                        decision = "pass"
                        contract_type = None
                        contract_suit = None
                        called_ace_suit = None

                    bid_order = (
                        db.query(HandBid).filter(HandBid.hand_id == hand.id).count() + 1
                    )

                    db.add(
                        HandBid(
                            hand_id=hand.id,
                            table_id=table.id,
                            user_id=user.id,
                            seat_number=participant.seat_number,
                            decision=decision,
                            contract_type=contract_type,
                            contract_suit=contract_suit,
                            called_ace_suit=called_ace_suit,
                            bid_order=bid_order,
                        )
                    )
                    db.flush()

                    all_bids = db.scalars(
                        select(HandBid)
                        .where(HandBid.hand_id == hand.id)
                        .order_by(HandBid.bid_order.asc())
                    ).all()

                    if len(all_bids) < 4:
                        hand.current_turn_seat = next_seat(
                            hand.current_turn_seat or participant.seat_number
                        )
                        db.commit()
                        await manager.broadcast(
                            table.id, _public_state(db, hand, participants)
                        )
                        continue

                    play_bids = [
                        bid
                        for bid in all_bids
                        if bid.decision == "play" and bid.contract_type
                    ]
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
                    else:
                        winning_bid = sorted(
                            play_bids,
                            key=lambda bid: (
                                -contract_rank(bid.contract_type or ""),
                                bid.bid_order,
                            ),
                        )[0]

                        hand.phase = "playing"
                        hand.contract_type = winning_bid.contract_type
                        hand.contract_suit = winning_bid.contract_suit
                        hand.called_ace_suit = winning_bid.called_ace_suit
                        hand.declarer_user_id = winning_bid.user_id
                        hand.current_turn_seat = hand.forehand_seat

                        if (
                            winning_bid.contract_type == "rufer"
                            and winning_bid.called_ace_suit
                        ):
                            partner_card = db.scalar(
                                select(HandCard).where(
                                    HandCard.hand_id == hand.id,
                                    HandCard.suit == winning_bid.called_ace_suit,
                                    HandCard.rank == "A",
                                )
                            )
                            hand.partner_user_id = (
                                partner_card.user_id if partner_card else None
                            )
                        else:
                            hand.partner_user_id = None

                    db.commit()
                    await manager.broadcast(
                        table.id, _public_state(db, hand, participants)
                    )
                except ValueError as exc:
                    db.rollback()
                    await websocket.send_json(
                        {"type": "game_error", "message": str(exc)}
                    )
            elif event_type == "legal_cards":
                hand = _active_hand(db, table.id)
                if not hand or hand.phase != "playing":
                    await websocket.send_json(
                        {
                            "type": "legal_cards",
                            "cards": [],
                            "message": "No active play",
                        }
                    )
                    continue

                my_cards = db.scalars(
                    select(HandCard).where(
                        HandCard.hand_id == hand.id,
                        HandCard.user_id == user.id,
                        HandCard.is_played.is_(False),
                    )
                ).all()
                card_tuples = [(card.suit, card.rank) for card in my_cards]

                trick = db.scalar(
                    select(HandTrick).where(
                        HandTrick.hand_id == hand.id,
                        HandTrick.trick_index == hand.trick_number,
                    )
                )
                lead_card = None
                if trick:
                    lead = db.scalar(
                        select(TrickCard)
                        .where(TrickCard.trick_id == trick.id)
                        .order_by(TrickCard.play_order.asc())
                    )
                    if lead:
                        lead_card = (lead.suit, lead.rank)

                legal = legal_cards(
                    card_tuples,
                    lead_card,
                    hand.contract_type or "",
                    hand.contract_suit,
                )
                await websocket.send_json(
                    {
                        "type": "legal_cards",
                        "hand_id": hand.id,
                        "cards": [{"suit": suit, "rank": rank} for suit, rank in legal],
                    }
                )
            elif event_type == "play_card":
                hand = _active_hand(db, table.id)
                participants = _participants_by_seat(db, table.id)
                if not hand or hand.phase != "playing":
                    await websocket.send_json(
                        {"type": "game_error", "message": "No active hand to play"}
                    )
                    continue
                if participant.seat_number != hand.current_turn_seat:
                    await websocket.send_json(
                        {"type": "game_error", "message": "Not your turn"}
                    )
                    continue

                try:
                    suit = normalize_suit(str(payload.get("suit", "")))
                    rank = normalize_rank(str(payload.get("rank", "")))
                except ValueError as exc:
                    await websocket.send_json(
                        {"type": "game_error", "message": str(exc)}
                    )
                    continue

                my_cards = db.scalars(
                    select(HandCard).where(
                        HandCard.hand_id == hand.id,
                        HandCard.user_id == user.id,
                        HandCard.is_played.is_(False),
                    )
                ).all()
                card_tuples = [(card.suit, card.rank) for card in my_cards]
                if (suit, rank) not in set(card_tuples):
                    await websocket.send_json(
                        {
                            "type": "game_error",
                            "message": "Card not in your hand or already played",
                        }
                    )
                    continue

                trick = db.scalar(
                    select(HandTrick).where(
                        HandTrick.hand_id == hand.id,
                        HandTrick.trick_index == hand.trick_number,
                    )
                )
                lead_card = None
                if trick:
                    first_card = db.scalar(
                        select(TrickCard)
                        .where(TrickCard.trick_id == trick.id)
                        .order_by(TrickCard.play_order.asc())
                    )
                    if first_card:
                        lead_card = (first_card.suit, first_card.rank)

                allowed = legal_cards(
                    card_tuples,
                    lead_card,
                    hand.contract_type or "",
                    hand.contract_suit,
                )
                if (suit, rank) not in set(allowed):
                    await websocket.send_json(
                        {
                            "type": "game_error",
                            "message": "Illegal card for current trick",
                            "legal_cards": [
                                {"suit": legal_suit, "rank": legal_rank}
                                for legal_suit, legal_rank in allowed
                            ],
                        }
                    )
                    continue

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
                    db.query(TrickCard).filter(TrickCard.trick_id == trick.id).count()
                    + 1
                )
                db.add(
                    TrickCard(
                        trick_id=trick.id,
                        hand_id=hand.id,
                        table_id=table.id,
                        user_id=user.id,
                        seat_number=participant.seat_number,
                        play_order=play_order,
                        suit=suit,
                        rank=rank,
                    )
                )

                played_card = next(
                    card for card in my_cards if card.suit == suit and card.rank == rank
                )
                played_card.is_played = True
                db.flush()

                if play_order < 4:
                    hand.current_turn_seat = next_seat(participant.seat_number)
                    db.commit()
                    await manager.broadcast(
                        table.id, _public_state(db, hand, participants)
                    )
                    continue

                trick_cards = db.scalars(
                    select(TrickCard)
                    .where(TrickCard.trick_id == trick.id)
                    .order_by(TrickCard.play_order.asc())
                ).all()
                winner_seat = trick_winner(
                    [(card.seat_number, card.suit, card.rank) for card in trick_cards],
                    hand.contract_type or "",
                    hand.contract_suit,
                )
                trick.winner_seat = winner_seat

                if hand.trick_number >= 8:
                    _close_and_settle_hand(db, table, hand, participants)
                    db.commit()
                    await manager.broadcast(
                        table.id, _public_state(db, hand, participants)
                    )
                    continue

                hand.trick_number += 1
                hand.current_turn_seat = winner_seat
                db.commit()
                await manager.broadcast(table.id, _public_state(db, hand, participants))
            elif event_type == "ping":
                await websocket.send_json(
                    {"type": "pong", "timestamp": datetime.now(UTC).isoformat()}
                )
    except WebSocketDisconnect:
        if table_id:
            manager.disconnect(table_id, websocket)
            await manager.broadcast(
                table_id,
                {
                    "type": "participant_left",
                    "user_id": user_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
    finally:
        db.close()
