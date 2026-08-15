import logging
import os
import time
from threading import Lock
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt


logger = logging.getLogger(__name__)

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false"
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-secret")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


class FixedWindowLimiter:
    def __init__(self):
        self._windows: dict[str, tuple[int, int]] = {}
        self._lock = Lock()

    def hit(self, key: str, *, limit: int, window_seconds: int, now: int) -> int:
        window_start = now - (now % window_seconds)
        with self._lock:
            self._windows = {
                item_key: value
                for item_key, value in self._windows.items()
                if value[0] + window_seconds > now
            }
            stored_start, count = self._windows.get(key, (window_start, 0))
            if stored_start != window_start:
                stored_start, count = window_start, 0
            count += 1
            self._windows[key] = (stored_start, count)
            if count <= limit:
                return 0
            return max(1, stored_start + window_seconds - now)


limiter = FixedWindowLimiter()


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"


async def get_identity(request: Request, token: str | None = None) -> str:
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            if username:
                return f"user:{username}"
        except JWTError:
            pass
    return f"ip:{get_client_ip(request)}"


def rate_limit(group: str, max_requests: int, window_seconds: int = 60) -> Callable:
    async def _rate_limit_dependency(
        request: Request,
        token: str | None = Depends(oauth2_scheme),
    ):
        if not RATE_LIMIT_ENABLED:
            return

        identity = await get_identity(request, token)
        key = f"{group}:{identity}"
        retry_after = limiter.hit(
            key,
            limit=max_requests,
            window_seconds=window_seconds,
            now=int(time.time()),
        )
        if retry_after:
            logger.warning(
                "Rate limit hit: group=%s, identity=%s, path=%s",
                group,
                identity,
                request.url.path,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests, please try again later",
                headers={"Retry-After": str(retry_after)},
            )

    return _rate_limit_dependency
