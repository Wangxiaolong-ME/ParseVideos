"""简单的基于内存的限频器。生产环境可替换为 Redis。"""
import time
from typing import Dict

class RateLimiter:
    def __init__(self, min_interval: float):
        self._min_interval = float(min_interval)
        self._last_sent: Dict[int, float] = {}

    def allow(self, user_id: int) -> bool:
        """返回 True 表示通过；False 表示限频。"""
        now = time.time()
        last = self._last_sent.get(user_id, 0.0)
        if now - last < self._min_interval:
            return False
        self._last_sent[user_id] = now
        return True
