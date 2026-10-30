"""Keep SDK cleanup when explicitly supplying redirect-disabled model clients."""
import asyncio

from openai import (
    DefaultHttpxClient as _DefaultHttpxClient,
    DefaultAsyncHttpxClient as _DefaultAsyncHttpxClient,
)


class DefaultHttpxClient(_DefaultHttpxClient):
    # Explicit http_client bypasses the SDK wrapper; retain its GC cleanup.
    def __del__(self) -> None:
        if self.is_closed:
            return
        try:
            self.close()
        except Exception:
            pass


class DefaultAsyncHttpxClient(_DefaultAsyncHttpxClient):
    def __del__(self) -> None:
        if self.is_closed:
            return
        try:
            asyncio.get_running_loop().create_task(self.aclose())
        except Exception:
            pass
