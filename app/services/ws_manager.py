from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, table_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[table_id].add(websocket)

    def disconnect(self, table_id: str, websocket: WebSocket) -> None:
        if table_id in self._connections:
            self._connections[table_id].discard(websocket)
            if not self._connections[table_id]:
                del self._connections[table_id]

    async def broadcast(self, table_id: str, payload: dict) -> None:
        connections = list(self._connections.get(table_id, set()))
        for connection in connections:
            await connection.send_json(payload)


manager = ConnectionManager()
