from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.api.ws_game import handle_declare_bid, handle_legal_cards, handle_play_card
from app.api.ws_state import active_hand, my_hand_state, participants_by_seat, public_state
from app.db.session import SessionLocal
from app.models import ChatMessage, Table, TableParticipant, User
from app.services.hand_service import start_hand
from app.services.security import decode_access_token
from app.services.ws_manager import manager


router = APIRouter(tags=["ws"])


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
        await manager.connect(table.id, user.id, websocket)
        await manager.broadcast(table.id, {
            "type": "participant_joined",
            "user_id": user.id,
            "nickname": participant.nickname,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        hand = active_hand(db, table.id)
        if hand:
            seats = participants_by_seat(db, table.id)
            await websocket.send_json(public_state(db, hand, seats))
            await websocket.send_json({
                "type": "my_hand",
                "hand_id": hand.id,
                "cards": my_hand_state(db, hand, user.id),
            })

        while True:
            payload = await websocket.receive_json()
            event_type = payload.get("type")

            if event_type == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.now(UTC).isoformat()})

            elif event_type == "chat_message":
                text = str(payload.get("message", "")).strip()
                if text:
                    db.add(ChatMessage(
                        table_id=table.id,
                        user_id=user.id,
                        nickname=participant.nickname,
                        message=text,
                    ))
                    db.commit()
                    await manager.broadcast(table.id, {
                        "type": "chat_message",
                        "user_id": user.id,
                        "nickname": participant.nickname,
                        "message": text,
                        "timestamp": datetime.now(UTC).isoformat(),
                    })

            elif event_type == "start_hand":
                seats = participants_by_seat(db, table.id)
                active = active_hand(db, table.id)
                if active:
                    await websocket.send_json({
                        "type": "game_error",
                        "message": "A hand is already active",
                        "state": public_state(db, active, seats),
                    })
                    continue
                try:
                    hand = start_hand(db, table, seats)
                    db.commit()
                    await manager.broadcast(table.id, public_state(db, hand, seats))
                except ValueError as exc:
                    db.rollback()
                    await websocket.send_json({"type": "game_error", "message": str(exc)})

            elif event_type == "my_hand":
                hand = active_hand(db, table.id)
                if not hand:
                    await websocket.send_json({"type": "my_hand", "cards": [], "message": "No active hand"})
                    continue
                await websocket.send_json({
                    "type": "my_hand",
                    "hand_id": hand.id,
                    "cards": my_hand_state(db, hand, user.id),
                })

            elif event_type == "declare_bid":
                hand = active_hand(db, table.id)
                if not hand:
                    await websocket.send_json({"type": "game_error", "message": "No active hand"})
                    continue
                seats = participants_by_seat(db, table.id)
                await handle_declare_bid(db, table, hand, user, participant, seats, payload, websocket)

            elif event_type == "legal_cards":
                hand = active_hand(db, table.id)
                if not hand:
                    await websocket.send_json({"type": "legal_cards", "cards": [], "message": "No active play"})
                    continue
                await handle_legal_cards(db, hand, user, websocket)

            elif event_type == "play_card":
                hand = active_hand(db, table.id)
                if not hand:
                    await websocket.send_json({"type": "game_error", "message": "No active hand to play"})
                    continue
                seats = participants_by_seat(db, table.id)
                await handle_play_card(db, table, hand, user, participant, seats, payload, websocket)

    except WebSocketDisconnect:
        if table_id:
            manager.disconnect(table_id, websocket)
            await manager.broadcast(table_id, {
                "type": "participant_left",
                "user_id": user_id,
                "timestamp": datetime.now(UTC).isoformat(),
            })
    finally:
        db.close()
