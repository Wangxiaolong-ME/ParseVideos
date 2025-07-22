"""控制“同一用户同一时间只跑一个下载任务”的管理器。"""
import asyncio
from typing import Dict

class TaskManager:
    def __init__(self):
        self._locks: Dict[int, asyncio.Lock] = {}

    async def acquire(self, user_id: int) -> bool:
        """尝试为 user_id 获取锁；成功返回 True，否则 False。"""
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        if lock.locked():
            return False
        await lock.acquire()
        return True

    def release(self, user_id: int) -> None:
        lock = self._locks.get(user_id)
        if lock and lock.locked():
            lock.release()

    def active_count(self) -> int:
        """当前正在执行的任务数（= 已加锁的用户数）。"""
        return sum(1 for lock in self._locks.values() if lock.locked())