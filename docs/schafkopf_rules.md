# Schafkopf Rules

## Basics

- 4 players, 32-card deck (4 suits × 8 ranks)
- **Suits:** Eichel (acorns), Gras (leaves), Herz (hearts), Schellen (bells)
- **Ranks:** A, 10, K, O (Ober), U (Unter), 9, 8, 7
- Dealer rotates clockwise each hand. Cards are dealt 8 per player starting from **forehand** (player left of dealer).

## Card Points

| Rank | Points |
|------|--------|
| A    | 11     |
| 10   | 10     |
| K    | 4      |
| O    | 3      |
| U    | 2      |
| 9/8/7 | 0    |

Total: **120 points** per hand. Declarer team needs **≥ 61** to win.

## Bidding

Each player in turn (starting from forehand) declares **play** or **pass**. If multiple players bid, the highest contract type wins; equal types go to the earlier bidder. If everyone passes → Ramsch (if enabled) or the hand is skipped.

## Contract Types

### Rufer (Rufspiel)
- Declarer names a suit ace (not Herz) → whoever holds that ace is the secret partner.
- Trump suit: **Herz** + all Obers + all Unters.
- Declarer must hold at least one non-trump, non-ace card of the called suit.
- Declarer cannot call an ace they hold themselves.

### Solo
- One player against three. Declarer picks any suit as trump.
- Trump: chosen suit + all Obers + all Unters.

### Wenz
- One player against three. **Only Unters are trump** (no Obers).
- Trump order (high → low): Eichel-U, Gras-U, Herz-U, Schellen-U.
- Obers rank as normal side-suit cards (A > 10 > K > O > 9 > 8 > 7).

### Ramsch
- No declarer. Everyone plays for themselves. Player with the **most points loses** and pays the others.
- Tiebreak: most tricks → most trumps collected → highest trump held.
- **Jungfrau** (zero tricks taken): doubles the loser's penalty per jungfrau player.

## Trump Order (Rufer / Solo)

Eichel-O · Gras-O · Herz-O · Schellen-O · Eichel-U · Gras-U · Herz-U · Schellen-U · (suit A · 10 · K · 9 · 8 · 7)

## Legal Cards

A player must **follow suit** if possible. "Suit" is determined by the **category** of the lead card:
- If the lead card is trump → must play trump.
- Otherwise → must play the led suit (A, 10, K, 9, 8, 7 of that suit; Obers and Unters are always trump, not the suit).

If a player has no cards of the required category, they may play any card.

## Trick Resolution

The highest trump wins. If no trump was played, the highest card of the **led suit** wins. The winner leads the next trick.

## Scoring

Base rate comes from table config (`euro_per_point_cents`).

| Contract | Base rate |
|----------|-----------|
| Rufer    | 1× base   |
| Solo / Wenz | 5× base |

**Bonuses** (stacked on top of base):
- **Schneider** (winner ≥ 91 points): +1× base
- **Schwarz** (all 8 tricks): +2× base
- **Laufende** (consecutive trumps from the top held by the winning team): +1× base per trump, minimum 3 for Rufer/Solo, 2 for Wenz

**Payout:**
- Rufer: each winner receives base+bonuses from each loser (zero-sum, 2v2).
- Solo/Wenz: declarer wins → receives 3× amount (one from each opponent); declarer loses → pays 3× amount.
- Ramsch: loser pays 1× amount to each of the 3 opponents.
