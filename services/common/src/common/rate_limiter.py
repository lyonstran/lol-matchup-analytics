import time
import threading
from collections import deque


class RateLimiter:
    """Enforces multiple sliding-window request limits at once.

    limits: list of (max_requests, window_seconds).
    Riot dev keys: [(20, 1), (100, 120)] — 20/sec AND 100 per 2 minutes.
    """

    def __init__(self, limits):
        self.limits = list(limits)
        self.windows = [deque() for _ in self.limits]
        self.lock = threading.Lock()

    def acquire(self):
        """Block until a request is allowed under every window, then record it."""
        while True:
            with self.lock:
                now = time.monotonic()
                wait = 0.0
                for (max_req, window), stamps in zip(self.limits, self.windows):
                    cutoff = now - window
                    while stamps and stamps[0] <= cutoff:
                        stamps.popleft()          # drop timestamps outside the window
                    if len(stamps) >= max_req:
                        wait = max(wait, stamps[0] + window - now)
                if wait <= 0:
                    for stamps in self.windows:
                        stamps.append(now)
                    return
            time.sleep(wait)