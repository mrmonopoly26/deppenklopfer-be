from __future__ import annotations

from typing import Iterable

SUITS: tuple[str, ...] = ("eichel", "gras", "herz", "schellen")
RANKS: tuple[str, ...] = ("A", "10", "K", "O", "U", "9", "8", "7")

RUFER_OR_RAMSCH_TRUMP_SUIT = "herz"

CARD_POINTS: dict[str, int] = {
    "A": 11,
    "10": 10,
    "K": 4,
    "O": 3,
    "U": 2,
    "9": 0,
    "8": 0,
    "7": 0,
}


def normalize_suit(value: str) -> str:
    suit = value.strip().lower()
    if suit not in SUITS:
        raise ValueError(f"Unknown suit: {value}")
    return suit


def normalize_rank(value: str) -> str:
    rank = value.strip().upper()
    if rank not in RANKS:
        raise ValueError(f"Unknown rank: {value}")
    return rank


def build_deck() -> list[tuple[str, str]]:
    return [(suit, rank) for suit in SUITS for rank in RANKS]


def next_seat(seat: int) -> int:
    return 1 if seat == 4 else seat + 1


def contract_rank(contract_type: str) -> int:
    return {
        "rufer": 1,
        "wenz": 2,
        "solo": 3,
    }.get(contract_type, 0)


def trump_order(contract_type: str, contract_suit: str | None) -> list[tuple[str, str]]:
    obers = [("eichel", "O"), ("gras", "O"), ("herz", "O"), ("schellen", "O")]
    unters = [("eichel", "U"), ("gras", "U"), ("herz", "U"), ("schellen", "U")]

    if contract_type in {"rufer", "ramsch"}:
        suit_cards = [
            (RUFER_OR_RAMSCH_TRUMP_SUIT, rank)
            for rank in ("A", "10", "K", "9", "8", "7")
        ]
        return [*obers, *unters, *suit_cards]

    if contract_type == "solo":
        if not contract_suit:
            raise ValueError("Solo contract requires trump suit")
        suit_cards = [(contract_suit, rank) for rank in ("A", "10", "K", "9", "8", "7")]
        return [*obers, *unters, *suit_cards]

    if contract_type == "wenz":
        return unters

    return []


def is_trump(
    contract_type: str, contract_suit: str | None, suit: str, rank: str
) -> bool:
    suit = normalize_suit(suit)
    rank = normalize_rank(rank)

    if contract_type in {"rufer", "ramsch"}:
        return rank in {"O", "U"} or suit == RUFER_OR_RAMSCH_TRUMP_SUIT

    if contract_type == "solo":
        if not contract_suit:
            return False
        return rank in {"O", "U"} or suit == contract_suit

    if contract_type == "wenz":
        return rank == "U"

    return False


def card_category(
    contract_type: str, contract_suit: str | None, suit: str, rank: str
) -> str:
    if is_trump(contract_type, contract_suit, suit, rank):
        return "trump"
    return normalize_suit(suit)


def legal_cards(
    hand_cards: Iterable[tuple[str, str]],
    lead_card: tuple[str, str] | None,
    contract_type: str,
    contract_suit: str | None,
) -> list[tuple[str, str]]:
    cards = [(normalize_suit(s), normalize_rank(r)) for s, r in hand_cards]
    if not lead_card:
        return cards

    lead_suit, lead_rank = normalize_suit(lead_card[0]), normalize_rank(lead_card[1])
    led_category = card_category(contract_type, contract_suit, lead_suit, lead_rank)

    matching = [
        card
        for card in cards
        if card_category(contract_type, contract_suit, card[0], card[1]) == led_category
    ]
    return matching if matching else cards


def _side_suit_strength(contract_type: str, rank: str) -> int:
    if contract_type == "wenz":
        order = {"A": 7, "10": 6, "K": 5, "O": 4, "9": 3, "8": 2, "7": 1, "U": 0}
        return order[rank]

    order = {"A": 7, "10": 6, "K": 5, "9": 4, "8": 3, "7": 2, "O": 1, "U": 0}
    return order[rank]


def trick_winner(
    trick_cards: Iterable[tuple[int, str, str]],
    contract_type: str,
    contract_suit: str | None,
) -> int:
    cards = [
        (seat, normalize_suit(suit), normalize_rank(rank))
        for seat, suit, rank in trick_cards
    ]
    if not cards:
        raise ValueError("Cannot resolve winner for empty trick")

    lead_suit, lead_rank = cards[0][1], cards[0][2]
    trumps = trump_order(contract_type, contract_suit)
    trump_index = {card: idx for idx, card in enumerate(trumps)}

    trump_cards = [card for card in cards if (card[1], card[2]) in trump_index]
    if trump_cards:
        winner = min(trump_cards, key=lambda c: trump_index[(c[1], c[2])])
        return winner[0]

    led_cards = [card for card in cards if card[1] == lead_suit]
    winner = max(led_cards, key=lambda c: _side_suit_strength(contract_type, c[2]))
    return winner[0]


def card_points(rank: str) -> int:
    return CARD_POINTS[normalize_rank(rank)]


def count_laufende(
    team_cards: Iterable[tuple[str, str]],
    contract_type: str,
    contract_suit: str | None,
) -> int:
    order = trump_order(contract_type, contract_suit)
    if not order:
        return 0

    cards = {(normalize_suit(s), normalize_rank(r)) for s, r in team_cards}
    laufende = 0
    for card in order:
        if card in cards:
            laufende += 1
        else:
            break
    return laufende


def minimum_laufende(contract_type: str) -> int:
    if contract_type == "wenz":
        return 2
    if contract_type in {"rufer", "solo"}:
        return 3
    return 99
