from fastapi.responses import JSONResponse

from .core.config import allowed_origins, normalize_origin

MAX_REQUEST_SIZE = 32 * 1024 * 1024


class ApiSecurityMiddleware:
    def __init__(self, app):
        self.app = app
        self.allowed_origins = allowed_origins()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        origin = headers.get(b"origin")
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"} and not origin:
            await self._reject(
                scope,
                receive,
                send,
                403,
                "An origin header is required for this request.",
            )
            return

        if origin:
            try:
                normalized_origin = normalize_origin(origin.decode("latin-1"))
                host = headers.get(b"host", b"").decode("latin-1")
                request_origin = normalize_origin(f"{scope['scheme']}://{host}")
            except (UnicodeDecodeError, ValueError):
                normalized_origin = ""
                request_origin = ""
            if (
                normalized_origin not in self.allowed_origins
                and normalized_origin != request_origin
            ):
                await self._reject(
                    scope,
                    receive,
                    send,
                    403,
                    "Cross-origin requests are not allowed.",
                )
                return

        async def add_no_store(message):
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                if not any(name.lower() == b"cache-control" for name, _ in response_headers):
                    response_headers.append((b"cache-control", b"no-store"))
                message["headers"] = response_headers
            await send(message)

        await self.app(scope, receive, add_no_store)

    @staticmethod
    async def _reject(scope, receive, send, status_code: int, message: str) -> None:
        response = JSONResponse(
            status_code=status_code,
            content={"error": message},
            headers={"Cache-Control": "no-store"},
        )
        await response(scope, receive, send)


class RequestSizeLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return

        content_length = dict(scope["headers"]).get(b"content-length")
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_SIZE:
                    await ApiSecurityMiddleware._reject(
                        scope, receive, send, 413, "The request is too large."
                    )
                    return
            except ValueError:
                await ApiSecurityMiddleware._reject(
                    scope, receive, send, 400, "The request body is invalid."
                )
                return

        received_size = 0

        async def limited_receive():
            nonlocal received_size
            message = await receive()
            if message["type"] == "http.request":
                received_size += len(message.get("body", b""))
                if received_size > MAX_REQUEST_SIZE:
                    raise RequestTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestTooLarge:
            await ApiSecurityMiddleware._reject(
                scope, receive, send, 413, "The request is too large."
            )


class RequestTooLarge(Exception):
    pass
