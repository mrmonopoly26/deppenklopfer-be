from app.api.auth import router as auth_router
from app.api.tables import router as tables_router
from app.api.users import router as users_router
from app.api.ws import router as ws_router

__all__ = ["auth_router", "tables_router", "users_router", "ws_router"]
