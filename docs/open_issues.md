# Open Issues

## Bugs

### 1. Cards not pushed after `start_hand`
After `start_hand` the server broadcasts `game_state` (phase: "bidding") but never pushes individual `my_hand` to each player. Players connect, see bidding has started, but their hand is blank until they explicitly send a `my_hand` event. The reconnect flow already does this correctly — `start_hand` should too.

**Fix:** After broadcasting `public_state` in the `start_hand` branch of `ws.py`, unicast `my_hand` to every seated participant via `manager.send_to_user`.

---

### 2. Cards not re-pushed after bidding resolves
When bidding resolves to a playing contract, `my_hand_state` sort order changes significantly — all Obers and Unters move to the trump section. The server never re-pushes the re-sorted hand to players. They must explicitly request `my_hand` again to see the correct order.

**Fix:** After `db.commit()` and `manager.broadcast(public_state(...))` in the bidding-resolution path of `handle_declare_bid`, unicast the updated `my_hand` to every participant.

---

## Should Fix

### 3. No per-seat point totals in `public_state`
During play there is no server-computed running score. Clients must iterate `completed_tricks`, look up each card's point value, and attribute it to the correct seat — duplicating Schafkopf domain logic that already lives in the backend.

**Fix:** Add `seat_points: dict[int, int]` to `public_state`, computed by summing `card_points(rank)` for all cards in each seat's won tricks.

---

### 4. Any participant can start a hand
`start_hand` has no authorization check — all 4 players can trigger it. This can cause accidental starts or races when multiple players tap the button simultaneously.

**Fix:** In the `start_hand` branch of `ws.py`, reject the event if `user.id != table.host_user_id`.
