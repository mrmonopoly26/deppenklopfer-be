# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                                      # install dependencies
uv run uvicorn main:app --reload             # run dev server (port 8000)
./start_server.sh                            # alternative dev start (port 8001)
```

Interactive API docs at `/docs` when the server is running.

No test or lint commands are configured.

## Architecture

FastAPI backend for **Deppenklopfer**, a real-time Schafkopf (German card game) platform.

**Stack:** FastAPI · SQLAlchemy + SQLite · JWT auth (python-jose + bcrypt) · WebSockets · Python 3.13+ · uv

### File size limit

Keep every file under **400 lines**. Exceptions are allowed when a single cohesive concept genuinely requires more, but split first.

### Layers

- `app/api/ws.py` — WebSocket connection setup and event dispatch (thin router only).
- `app/api/ws_game.py` — Game event handlers: `handle_declare_bid`, `handle_legal_cards`, `handle_play_card`.
- `app/api/ws_state.py` — Read-only DB queries and state serialisation: `active_hand`, `participants_by_seat`, `public_state`, `my_hand_state`.
- `app/api/tables.py` — REST endpoints for table create/join/config/chat.
- `app/services/hand_service.py` — Hand lifecycle mutations: `start_hand`, `close_and_settle_hand`.
- `app/services/schafkopf_rules.py` — Card/trump logic and legal-move validation.
- `app/services/schafkopf_scoring.py` — Payout calculation and Ramsch settlement.
- `app/services/ws_manager.py` — WebSocket connection pool (`ConnectionManager`).
- `app/models/entities.py` — SQLAlchemy ORM (User, Table, TableParticipant, ChatMessage, GameRound, GameHand, HandBid, BalanceTransaction).
- `app/schemas/dto.py` — Pydantic DTOs for all request/response shapes.
- `app/config.py` — env-based settings (JWT secret, DB URL, CORS).

### Game flow

1. Client authenticates → JWT
2. Client creates/joins table via 6-digit code (`app/api/tables.py`)
3. Client connects WebSocket (`/ws/{table_id}`) — server is authoritative
4. Server deals 8 cards per player, runs bidding (Rufspiel/Solo/Wenz/Ramsch), validates legal cards, resolves tricks, settles hand, updates `BalanceTransaction`

### Key design points

- All game state lives server-side; WebSocket messages are the only interface for in-progress hands
- SQLite auto-creates on startup (`deppenklopfer.db`); swap to PostgreSQL by changing `DATABASE_URL` in config
- CORS is open (`*`) in the current MVP config

### Game rules
A full set of rules is located in `docs/schafkopf_rules.md`.

