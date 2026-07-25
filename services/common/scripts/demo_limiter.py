import time
from common.rate_limiter import RateLimiter

limiter = RateLimiter([(3, 2)])  # tiny fake limit: 3 requests per 2 seconds
start = time.monotonic()
for i in range(7):
    limiter.acquire()
    print(f"request {i} fired at {time.monotonic() - start:5.2f}s") 