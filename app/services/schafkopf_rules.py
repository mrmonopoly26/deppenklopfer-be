from __future__ import annotations

from typing import Iterable

# ── Card components ────────────────────────────────────────────────────────────

SUITS: tuple[str, ...] = ("eichel", "gras", "herz", "schellen")
RANKS: tuple[str, ...] = ("A", "10", "K", "O", "U", "9")

SUIT_EICHEL = "eichel"
SUIT_GRAS = "gras"
SUIT_HERZ = "herz"
SUIT_SCHELLEN = "schellen"

RANK_ACE = "A"
RANK_OBER = "O"
RANK_UNTER = "U"

RUFER_OR_RAMSCH_TRUMP_SUIT = SUIT_HERZ

# ── Contract types ─────────────────────────────────────────────────────────────

CONTRACT_RUFER = "rufer"
CONTRACT_SOLO = "solo"
CONTRACT_WENZ = "wenz"
CONTRACT_GEIER = "geier"
CONTRACT_RAMSCH = "ramsch"

# ── Bid decisions ──────────────────────────────────────────────────────────────

DECISION_PLAY = "play"
DECISION_PASS = "pass"

# ── Table game modes (as stored in config.game_modes) ─────────────────────────

MODE_RUFSPIEL = "rufspiel"

# ── Hand phases ────────────────────────────────────────────────────────────────

PHASE_BIDDING = "bidding"
PHASE_PLAYING = "playing"
PHASE_SCORING = "scoring"
PHASE_CLOSED = "closed"

# ── Table statuses ─────────────────────────────────────────────────────────────

TABLE_STATUS_PLAYING = "playing"
TABLE_STATUS_WAITING = "waiting"

# ── Game rule constants (Kurzes Blatt: 6 cards per player, 6 tricks per hand) ─

CARDS_PER_PLAYER = 6
TRICKS_PER_HAND = CARDS_PER_PLAYER
TOTAL_CARD_POINTS = 120
WINNING_POINTS = 61
SCHNEIDER_POINTS = 91

# ── Card point values ──────────────────────────────────────────────────────────

CARD_POINTS: dict[str, int] = {
    RANK_ACE: 11,
    "10": 10,
    "K": 4,
    RANK_OBER: 3,
    RANK_UNTER: 2,
    "9": 0,
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
        CONTRACT_RUFER: 1,
        CONTRACT_GEIER: 2,
        CONTRACT_WENZ: 3,
        CONTRACT_SOLO: 4,
    }.get(contract_type, 0)


def trump_order(contract_type: str, contract_suit: str | None) -> list[tuple[str, str]]:
    obers = [
        (SUIT_EICHEL, RANK_OBER), (SUIT_GRAS, RANK_OBER),
        (SUIT_HERZ, RANK_OBER), (SUIT_SCHELLEN, RANK_OBER),
    ]
    unters = [
        (SUIT_EICHEL, RANK_UNTER), (SUIT_GRAS, RANK_UNTER),
        (SUIT_HERZ, RANK_UNTER), (SUIT_SCHELLEN, RANK_UNTER),
    ]

    if contract_type in {CONTRACT_RUFER, CONTRACT_RAMSCH}:
        suit_cards = [
            (RUFER_OR_RAMSCH_TRUMP_SUIT, rank) for rank in (RANK_ACE, "10", "K", "9")
        ]
        return [*obers, *unters, *suit_cards]

    if contract_type == CONTRACT_SOLO:
        if not contract_suit:
            raise ValueError("Solo contract requires trump suit")
        suit_cards = [(contract_suit, rank) for rank in (RANK_ACE, "10", "K", "9")]
        return [*obers, *unters, *suit_cards]

    if contract_type == CONTRACT_WENZ:
        return unters

    if contract_type == CONTRACT_GEIER:
        return obers

    return []


def is_trump(
    contract_type: str, contract_suit: str | None, suit: str, rank: str
) -> bool:
    suit = normalize_suit(suit)
    rank = normalize_rank(rank)

    if contract_type in {CONTRACT_RUFER, CONTRACT_RAMSCH}:
        return rank in {RANK_OBER, RANK_UNTER} or suit == RUFER_OR_RAMSCH_TRUMP_SUIT

    if contract_type == CONTRACT_SOLO:
        if not contract_suit:
            return False
        return rank in {RANK_OBER, RANK_UNTER} or suit == contract_suit

    if contract_type == CONTRACT_WENZ:
        return rank == RANK_UNTER

    if contract_type == CONTRACT_GEIER:
        return rank == RANK_OBER

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
    called_ace_suit: str | None = None,
) -> list[tuple[str, str]]:
    cards = [(normalize_suit(s), normalize_rank(r)) for s, r in hand_cards]

    # Rufspiel: the partner (holder of the called ace) has restricted card choices.
    if contract_type == CONTRACT_RUFER and called_ace_suit:
        called_ace_s = normalize_suit(called_ace_suit)
        called_ace = (called_ace_s, RANK_ACE)
        if called_ace in cards:
            if lead_card:
                lead_s, lead_r = normalize_suit(lead_card[0]), normalize_rank(lead_card[1])
                led_cat = card_category(contract_type, contract_suit, lead_s, lead_r)
                if led_cat == called_ace_s:
                    # Called suit led: must play the called ace.
                    return [called_ace]
                # Called suit not led: exclude the called ace from valid options.
                matching = [
                    c for c in cards
                    if card_category(contract_type, contract_suit, c[0], c[1]) == led_cat
                ]
                following = matching if matching else cards
                without_ace = [c for c in following if c != called_ace]
                return without_ace if without_ace else following
            else:
                # Leading: may not lead any non-trump card of the called suit (including the ace).
                forbidden = {
                    c for c in cards
                    if c[0] == called_ace_s and not is_trump(contract_type, contract_suit, c[0], c[1])
                }
                if forbidden:
                    allowed = [c for c in cards if c not in forbidden]
                    return allowed if allowed else cards

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
    if contract_type == CONTRACT_WENZ:
        # U is trump; O ranks above 9 as a side-suit card
        order = {RANK_ACE: 5, "10": 4, "K": 3, RANK_OBER: 2, "9": 1, RANK_UNTER: 0}
        return order[rank]
    if contract_type == CONTRACT_GEIER:
        # O is trump; U ranks above 9 as a side-suit card
        order = {RANK_ACE: 5, "10": 4, "K": 3, RANK_UNTER: 2, "9": 1, RANK_OBER: 0}
        return order[rank]
    # O and U are always trump; only A, 10, K, 9 can appear as side-suit
    order = {RANK_ACE: 4, "10": 3, "K": 2, "9": 1, RANK_OBER: 0, RANK_UNTER: 0}
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

    lead_suit = cards[0][1]
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
    if contract_type in {CONTRACT_WENZ, CONTRACT_GEIER}:
        return 2
    if contract_type in {CONTRACT_RUFER, CONTRACT_SOLO}:
        return 3
    return 99
