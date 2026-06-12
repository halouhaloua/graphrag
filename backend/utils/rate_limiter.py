"""异步请求限速器（漏斗桶算法）"""

import asyncio
import time


class AsyncRateLimiter:
    """异步请求限速器，漏斗桶算法"""

    def __init__(self, max_requests_per_minute: int):
        self.rate = max_requests_per_minute / 60.0
        self.capacity = max_requests_per_minute
        self.water = 0
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.time()
            leaked = (now - self.last_update) * self.rate
            self.water = max(0, self.water - leaked)
            self.last_update = now
            if self.water >= self.capacity:
                wait = (self.water - self.capacity + 1) / self.rate
                await asyncio.sleep(wait)
                self.water = max(0, self.water - self.rate * wait)
            self.water += 1
