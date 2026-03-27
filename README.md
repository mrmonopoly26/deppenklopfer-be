# deppenklopfer-be

FastAPI backend for deppenklopfer (Schafkopf).

## MVP Features Implemented

- Email/password registration and login with JWT bearer tokens
- Email/password change request flow via expiring confirmation token
- Table creation with unique 6-digit game code
- Host-only table configuration updates (game modes and payout values)
- Table join with per-table nickname (nickname is not globally unique)
- Fixed 4-seat tables for Schafkopf
- Realtime table streaming over WebSocket for chat and game events
- Persistent chat history per table
- Persistent game round payout recording and user virtual bank balance updates
- Server-authoritative Schafkopf hand lifecycle over WebSocket
	- hand start and card dealing (8 cards each)
	- bidding/pass flow with rufer/wenz/solo resolution
	- all-pass handling: optional auto-Ramsch if enabled in game modes
	- strict legal-card validation per contract while playing tricks
	- automatic hand settlement and balance posting (tariff 10/50 + bonuses)

## Tech Stack

- FastAPI
- SQLAlchemy (SQLite for MVP)
- JWT (python-jose)
- Password hashing (passlib/bcrypt)

## Run Locally

1. Install dependencies:

```bash
uv sync
```

2. Start server:

```bash
uv run uvicorn main:app --reload
```

3. Open docs:

```text
http://127.0.0.1:8000/docs
```

The SQLite database file is created automatically on first startup as `deppenklopfer.db`.

## API Overview

### Auth

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/change-request`
- `POST /auth/change-request/confirm`

### Tables

- `POST /tables`
- `POST /tables/join`
- `GET /tables/{game_code}`
- `PATCH /tables/{game_code}/config`
- `GET /tables/{game_code}/chat`
- `POST /tables/{game_code}/rounds/complete`

### User

- `GET /users/me/balance`

### Realtime Streaming

- `WS /ws/tables/{game_code}?token=<jwt>`

WebSocket event types currently supported:

- `chat_message`
- `game_action`
- `start_hand`
- `my_hand`
- `declare_bid`
- `legal_cards`
- `play_card`
- `ping` / `pong`
- broadcasted lifecycle events (`participant_joined`, `participant_left`)

Additional game stream payloads:

- `game_state` (broadcast): public hand state, bids, current trick, turn seat, result
- `game_error` (direct): invalid action details for the sending player

Notes:

- Existing `game_action` passthrough is still available for backward compatibility.
- `start_hand` currently requires 4 participants at the table.
- Ramsch is enabled when `"ramsch"` is included in `table.config.game_modes`.
