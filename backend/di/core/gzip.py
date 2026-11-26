"""gzip for JSON answers, never for streams (plan 3 task 1).

Owns: `GzipExceptStreams`, Starlette's `GZipMiddleware(minimum_size=1000, compresslevel=5)` that steps aside for
server-sent events. It never compresses `/api/stream`, `/api/ask` or `/mcp`, nor any request that asks for
`text/event-stream`: a gzip layer buffers, and a buffered event stream arrives late or not at all.

Why a wrapper: Starlette skips `text/event-stream` by itself only from 0.46; fastapi 0.115.6 pins Starlette 0.41. The
bump to `fastapi==0.115.14` with `starlette>=0.46,<0.47` (plan 3 Global Constraints) needs a recompiled lock; until
then this wrapper gives the same behaviour. Once the bump lands the paths here are belt and braces.
"""

from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

NO_GZIP_PREFIXES = ("/api/stream", "/api/ask", "/mcp")


class GzipExceptStreams:
    def __init__(self, app: ASGIApp, minimum_size: int = 1000, compresslevel: int = 5) -> None:
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=minimum_size, compresslevel=compresslevel)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(NO_GZIP_PREFIXES):
            await self.app(scope, receive, send)
            return
        for k, v in scope["headers"]:
            if k == b"accept" and b"text/event-stream" in v:
                await self.app(scope, receive, send)
                return
        await self.gzip(scope, receive, send)
