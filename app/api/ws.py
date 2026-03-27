from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ChatMessage, Table, TableParticipant, User
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
            elif event_type == "ping":
                await websocket.send_json(
                    {"type": "pong", "timestamp": datetime.now(UTC).isoformat()}
                )
    except WebSocketDisconnect:
        manager.disconnect(table.id, websocket)
        await manager.broadcast(
            table.id,
            {
                "type": "participant_left",
                "user_id": user_id,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
    finally:
        db.close()
