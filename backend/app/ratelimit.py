"""Small in-memory sliding-window rate limiter (per client IP, per bucket).

Good enough for a single instance. For multiple instances, back it with Redis or a gateway limit.
"""
 

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, limit: int, window_s: int = 60, bucket: str = "general"):
        self.limit, self.window_s, self.bucket = limit, window_s, bucket
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def __call__(self, request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self._lock:
            q = self._hits[ip]
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                retry = int(self.window_s - (now - q[0])) + 1
                raise HTTPException(status_code=429, detail=f"Rate limit exceeded ({self.limit}/{self.window_s}s). Retry in {retry}s.", headers={"Retry-After": str(retry)})
            q.append(now)
            if len(self._hits) > 10_000:  # bound memory
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
