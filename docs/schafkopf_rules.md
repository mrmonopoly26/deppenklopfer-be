# Schafkopf Rules

## Basics

- 4 players, 24-card deck (4 suits × 6 ranks)
- **Suits:** Eichel (acorns), Gras / Blatt (leaves), Herz (hearts), Schellen (bells)
- **Ranks:** A, 10, K, O (Ober), U (Unter), 9
- Dealer rotates clockwise each hand. Cards are dealt 6 per player starting from **forehand** (player left of dealer).

## Card Points

| Rank | Points |
|------|--------|
| A    | 11     |
| 10   | 10     |
| K    | 4      |
| O    | 3      |
| U    | 2      |
| 9    | 0      |

Total: **120 points** per hand. Declarer team needs **≥ 61** to win.

## Bidding

Each player in turn (starting from forehand) declares **play** or **pass**. If multiple players bid, the highest contract type wins; equal types go to the earlier bidder. If everyone passes → Ramsch (if enabled) or the hand is skipped.

## Contract Types

### Rufer (Rufspiel)
- Declarer (or caller) names a suit ace (not Herz) → whoever holds that ace is the secret partner (the called player).
- Trump suit: **Herz** + all Obers + all Unters.
- Declarer must hold at least one non-trump, non-ace card of the called suit.
- Declarer cannot call an ace they hold themselves.

### Solo
- One player against three. Declarer picks any suit as trump.
- Trump: chosen suit + all Obers + all Unters.

### Wenz
- One player against three. **Only Unters are trump** (no Obers).
- Trump order (high → low): Eichel-U, Gras-U, Herz-U, Schellen-U.
- Obers rank as normal side-suit cards (A > 10 > K > O > 9).

### Ramsch
- No declarer. Everyone plays for themselves. Player with the **most points loses** and pays the others.
- Tiebreak: most tricks → most trumps collected → highest trump held.
- **Jungfrau** (zero tricks taken): doubles the loser's penalty per jungfrau player.

## Trump Order (Rufer / Solo)

Eichel-O · Gras-O · Herz-O · Schellen-O · Eichel-U · Gras-U · Herz-U · Schellen-U · (suit A · 10 · K · 9)

## Legal Cards

A player must **follow suit** if possible. "Suit" is determined by the **category** of the lead card:
- If the lead card is trump → must play trump.
- Otherwise → must play the led suit (A, 10, K, 9 of that suit; Obers and Unters are always trump, not the suit).

If a player has no cards of the required category, they may play any card.

*IMPORTANT ADDITIONAL RULES FOR RUFSPIEL*:
1. If the suit of the called is led and the called player (the one with the ace) has any other cards of that suit, the player must play the ace and is not allowed to play other cards of that suit.
Example: First card is Gras-10, called player has Gras-A and Gras-K -> must play Gras-A, cannot play Gras-K.
2. If the called player (the one with the ace) is in the front (the one who leads the trick) and has the called suit, they must play the ace, if and only if he wants to play this suit. He is not allowed to play other cards of that suit. But he is of course allowed to play other suits or trumps. 
Example: Called player in front with 4 trumps and Gras-A and Gras-K -> He either plays a trump or Gras-A, but cannot play Gras-K. If he wants to play Gras, he must play Gras-A.
3. The caller of a Rufspiel is not allowed to hold the called ace (he cannot call himself). On top, he might only call an ace, if he has at least a suit card (NOT THE ACE, HERZ IS CONSIDERED AS TRUMP FOR RUFSPIEL) of the suit he wants to call. This also means that if the caller has the ace of the suit he wants to call, he is not allowed to call this suit.
Example 1: Caller has only Gras-A and no other Gras card -> cannot call Gras-A, because he holds this ace.
Example 2: Caller Gras-K -> he is allowed to call Gras-A.
Example 3: Caller has four Obers, single Unter and Herz-10 -> he cannot call Herz-A, because Herz is considered as trump for Rufspiel.

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
- **Schwarz** (all 6 tricks): +2× base
- **Laufende** (consecutive trumps from the top held by the winning team): +1× base per trump, minimum 3 for Rufer/Solo, 2 for Wenz

**Payout:**
- Rufer: each winner receives base+bonuses from each loser (zero-sum, 2v2).
- Solo/Wenz: declarer wins → receives 3× amount (one from each opponent); declarer loses → pays 3× amount.
- Ramsch: loser pays 1× amount to each of the 3 opponents.
