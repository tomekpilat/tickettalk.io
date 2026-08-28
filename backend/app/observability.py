import hashlib
import json
import logging
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic, perf_counter
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
JOIN_PATH = re.compile(r"^/api/rooms/[^/]+/join$")
IMPORT_PATH = re.compile(r"^/api/rooms/[^/]+/tickets/import(?:/preview)?$")
VOTE_PATH = re.compile(r"^/api/rooms/[^/]+/tickets/[^/]+/vote$")

http_logger = logging.getLogger("tickettalks.http")
event_logger = logging.getLogger("tickettalks.events")


def log_event(logger: logging.Logger, event: str, **fields: object) -> None:
    """Emit one machine-readable line without request bodies or credentials."""
    logger.info(json.dumps({"event": event, **fields}, separators=(",", ":"), default=str))


@dataclass(frozen=True)
class RateLimit:
    name: str
    requests: int
    window_seconds: int = 60


class RateLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, limit: RateLimit, identity: str) -> tuple[bool, int]:
        now = monotonic()
        key = (limit.name, identity)
        with self._lock:
            events = self._events[key]
            cutoff = now - limit.window_seconds
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit.requests:
                retry_after = max(1, int(limit.window_seconds - (now - events[0])) + 1)
                return False, retry_after
            events.append(now)
            return True, 0


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        join_limit: int,
        import_limit: int,
        vote_limit: int,
    ) -> None:
        super().__init__(app)
        self.limiter = RateLimiter()
        self.limits = {
            "join": RateLimit("join", join_limit),
            "import": RateLimit("import", import_limit),
            "vote": RateLimit("vote", vote_limit),
        }

    @staticmethod
    def _request_id(request: Request) -> str:
        supplied = request.headers.get("X-Request-ID", "")
        return supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid4())

    @staticmethod
    def _identity(request: Request) -> str:
        authorization = request.headers.get("Authorization")
        if authorization:
            return hashlib.sha256(authorization.encode()).hexdigest()[:24]
        client_host = request.client.host if request.client else "unknown"
        return hashlib.sha256(client_host.encode()).hexdigest()[:24]

    def _limit_for(self, request: Request) -> RateLimit | None:
        path = request.url.path
        if request.method == "POST" and JOIN_PATH.fullmatch(path):
            return self.limits["join"]
        if request.method == "POST" and IMPORT_PATH.fullmatch(path):
            return self.limits["import"]
        if request.method == "PUT" and VOTE_PATH.fullmatch(path):
            return self.limits["vote"]
        return None

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = self._request_id(request)
        request.state.request_id = request_id
        started_at = perf_counter()
        response: Response
        status_code = 500

        limit = self._limit_for(request)
        if limit and request.method != "OPTIONS":
            allowed, retry_after = self.limiter.check(limit, self._identity(request))
            if not allowed:
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Try again shortly."},
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit.requests),
                    },
                )
                status_code = response.status_code
                response.headers["X-Request-ID"] = request_id
                self._log_request(request, request_id, status_code, started_at)
                return response

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            self._log_request(request, request_id, status_code, started_at)
            raise

        response.headers["X-Request-ID"] = request_id
        self._log_request(request, request_id, status_code, started_at)
        return response

    @staticmethod
    def _log_request(
        request: Request, request_id: str, status_code: int, started_at: float
    ) -> None:
        log_event(
            http_logger,
            "http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status=status_code,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
