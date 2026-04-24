from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from app.services.schafkopf_rules import (
    CONTRACT_RAMSCH,
    CONTRACT_RUFER,
    SCHNEIDER_POINTS,
    TOTAL_CARD_POINTS,
    TRICKS_PER_HAND,
    WINNING_POINTS,
    card_points,
    count_laufende,
    is_trump,
    minimum_laufende,
    trump_order,
)


@dataclass
class SettlementResult:
    payouts_cents: dict[str, int]
    summary: str
    details: dict


def _ensure_zero_sum(payouts: dict[str, int]) -> None:
    total = sum(payouts.values())
    if total != 0:
        raise ValueError(f"Settlement is not zero-sum: {total}")


def _resolve_ramsch_loser(
    seat_points: dict[int, int],
    seat_tricks: dict[int, int],
    seat_trumps_in_tricks: dict[int, int],
    seat_highest_trump_idx: dict[int, int],
) -> int:
    max_points = max(seat_points.values())
    candidates = [seat for seat, points in seat_points.items() if points == max_points]
    if len(candidates) == 1:
        return candidates[0]

    max_tricks = max(seat_tricks[seat] for seat in candidates)
    candidates = [seat for seat in candidates if seat_tricks[seat] == max_tricks]
    if len(candidates) == 1:
        return candidates[0]

    max_trumps = max(seat_trumps_in_tricks[seat] for seat in candidates)
    candidates = [
        seat for seat in candidates if seat_trumps_in_tricks[seat] == max_trumps
    ]
    if len(candidates) == 1:
        return candidates[0]

    min_trump_idx = min(seat_highest_trump_idx.get(seat, 999) for seat in candidates)
    tied = [
        seat
        for seat in candidates
        if seat_highest_trump_idx.get(seat, 999) == min_trump_idx
    ]
    return min(tied)


def settle_hand(
    *,
    contract_type: str,
    contract_suit: str | None,
    declarer_user_id: str | None,
    partner_user_id: str | None,
    seat_to_user: dict[int, str],
    tricks: Iterable[tuple[int, list[tuple[int, str, str, str]]]],
    initial_hand_cards: dict[str, list[tuple[str, str]]],
    rufer_rate_cents: int = 10,
    solo_wenz_rate_cents: int = 50,
    schneider_bonus_cents: int = 10,
    schwarz_bonus_cents: int = 20,
    laufende_rate_cents: int = 10,
    enable_laufende: bool = True,
) -> SettlementResult:
    seat_points = defaultdict(int)
    seat_tricks = defaultdict(int)
    seat_trumps_in_tricks = defaultdict(int)
    seat_highest_trump_idx: dict[int, int] = {}

    trumps = trump_order(contract_type, contract_suit)
    trump_idx = {card: idx for idx, card in enumerate(trumps)}

    trick_count = 0
    for winner_seat, trick_cards in tricks:
        trick_count += 1
        seat_tricks[winner_seat] += 1
        for _, suit, rank, _ in trick_cards:
            seat_points[winner_seat] += card_points(rank)
            card_key = (suit, rank)
            if card_key in trump_idx:
                seat_trumps_in_tricks[winner_seat] += 1
                current = seat_highest_trump_idx.get(winner_seat, 999)
                seat_highest_trump_idx[winner_seat] = min(current, trump_idx[card_key])

    payouts = {user_id: 0 for user_id in seat_to_user.values()}

    if contract_type == CONTRACT_RAMSCH:
        loser_seat = _resolve_ramsch_loser(
            seat_points=dict(seat_points),
            seat_tricks=dict(seat_tricks),
            seat_trumps_in_tricks=dict(seat_trumps_in_tricks),
            seat_highest_trump_idx=seat_highest_trump_idx,
        )
        loser_user = seat_to_user[loser_seat]
        jungfrau_count = sum(1 for seat in seat_to_user if seat_tricks[seat] == 0)
        multiplier = 2**jungfrau_count if jungfrau_count > 0 else 1
        amount = rufer_rate_cents * multiplier

        for seat, user_id in seat_to_user.items():
            if seat == loser_seat:
                payouts[user_id] -= amount * 3
            else:
                payouts[user_id] += amount

        _ensure_zero_sum(payouts)
        return SettlementResult(
            payouts_cents=payouts,
            summary=f"Ramsch: loser seat {loser_seat} paid {amount} cents to each opponent",
            details={
                "contract_type": contract_type,
                "seat_points": dict(seat_points),
                "seat_tricks": dict(seat_tricks),
                "loser_seat": loser_seat,
                "jungfrau_count": jungfrau_count,
                "amount_per_opponent_cents": amount,
            },
        )

    if not declarer_user_id:
        raise ValueError("Declarer required for non-Ramsch settlement")

    declarer_seat = next(
        seat for seat, user in seat_to_user.items() if user == declarer_user_id
    )
    partner_seat = None
    if partner_user_id:
        partner_seat = next(
            seat for seat, user in seat_to_user.items() if user == partner_user_id
        )

    if contract_type == CONTRACT_RUFER:
        if partner_seat is None:
            raise ValueError("Rufer requires partner")
        declarer_team = {declarer_seat, partner_seat}
    else:
        declarer_team = {declarer_seat}

    declarer_points = sum(seat_points[seat] for seat in declarer_team)
    declarer_tricks = sum(seat_tricks[seat] for seat in declarer_team)
    declarer_wins = declarer_points >= WINNING_POINTS

    winner_points = declarer_points if declarer_wins else TOTAL_CARD_POINTS - declarer_points
    winner_tricks = declarer_tricks if declarer_wins else TRICKS_PER_HAND - declarer_tricks

    base = rufer_rate_cents if contract_type == CONTRACT_RUFER else solo_wenz_rate_cents
    amount = base

    if winner_points >= SCHNEIDER_POINTS:
        amount += schneider_bonus_cents
    if winner_tricks == TRICKS_PER_HAND:
        amount += schwarz_bonus_cents

    laufende = 0
    if enable_laufende:
        winner_team_user_ids = {
            seat_to_user[seat]
            for seat in seat_to_user
            if ((seat in declarer_team) == declarer_wins)
        }
        winner_cards = [
            card
            for user_id in winner_team_user_ids
            for card in initial_hand_cards.get(user_id, [])
        ]
        laufende = count_laufende(winner_cards, contract_type, contract_suit)
        if laufende >= minimum_laufende(contract_type):
            amount += laufende_rate_cents * laufende
        else:
            laufende = 0

    if contract_type == CONTRACT_RUFER:
        winner_seats = {
            seat for seat in seat_to_user if ((seat in declarer_team) == declarer_wins)
        }
        loser_seats = set(seat_to_user.keys()) - winner_seats
        for seat in winner_seats:
            payouts[seat_to_user[seat]] += amount
        for seat in loser_seats:
            payouts[seat_to_user[seat]] -= amount
    else:
        if declarer_wins:
            payouts[declarer_user_id] += amount * 3
            for seat, user_id in seat_to_user.items():
                if user_id != declarer_user_id:
                    payouts[user_id] -= amount
        else:
            payouts[declarer_user_id] -= amount * 3
            for seat, user_id in seat_to_user.items():
                if user_id != declarer_user_id:
                    payouts[user_id] += amount

    _ensure_zero_sum(payouts)

    result = "won" if declarer_wins else "lost"
    return SettlementResult(
        payouts_cents=payouts,
        summary=f"{contract_type} {result} ({declarer_points}: {TOTAL_CARD_POINTS - declarer_points}), amount {amount} cents",
        details={
            "contract_type": contract_type,
            "contract_suit": contract_suit,
            "declarer_points": declarer_points,
            "declarer_tricks": declarer_tricks,
            "declarer_wins": declarer_wins,
            "laufende": laufende,
            "amount_per_opponent_cents": amount,
            "seat_points": dict(seat_points),
            "seat_tricks": dict(seat_tricks),
        },
    )
