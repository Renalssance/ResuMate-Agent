"""API Schema 定义 — 按业务域分模块，统一导出。"""

from backend.schemas.auth import (
    AuthResponse,
    CurrentUserResponse,
    LoginRequest,
    RegisterRequest,
)
from backend.schemas.chat import (
    ChatRequest,
)

__all__ = [
    # auth
    "AuthResponse",
    "CurrentUserResponse",
    "LoginRequest",
    "RegisterRequest",
    # chat
    "ChatRequest",
]
