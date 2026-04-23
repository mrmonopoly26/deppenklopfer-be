from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._user_sockets: dict[str, dict[str, WebSocket]] = defaultdict(dict)

    async def connect(self, table_id: str, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        old = self._user_sockets[table_id].get(user_id)
        if old:
            self._connections[table_id].discard(old)
        self._connections[table_id].add(websocket)
        self._user_sockets[table_id][user_id] = websocket

    def disconnect(self, table_id: str, websocket: WebSocket) -> None:
        if table_id in self._connections:
            self._connections[table_id].discard(websocket)
            if not self._connections[table_id]:
                del self._connections[table_id]
        if table_id in self._user_sockets:
            self._user_sockets[table_id] = {
                uid: ws
                for uid, ws in self._user_sockets[table_id].items()
                if ws is not websocket
            }
            if not self._user_sockets[table_id]:
                del self._user_sockets[table_id]

    async def broadcast(self, table_id: str, payload: dict) -> None:
        connections = list(self._connections.get(table_id, set()))
        dead: list = []
        for connection in connections:
            try:
                await connection.send_json(payload)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self._connections[table_id].discard(connection)
            if table_id in self._user_sockets:
                self._user_sockets[table_id] = {
                    uid: ws
                    for uid, ws in self._user_sockets[table_id].items()
                    if ws is not connection
                }

    async def send_to_user(self, table_id: str, user_id: str, payload: dict) -> None:
        ws = self._user_sockets.get(table_id, {}).get(user_id)
        if ws:
            try:
                await ws.send_json(payload)
            except Exception:
                self._connections[table_id].discard(ws)
                self._user_sockets.get(table_id, {}).pop(user_id, None)


manager = ConnectionManager()
