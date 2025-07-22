# src/telegram_bot/monitor.py
"""运行时监控工具。"""

from concurrent.futures import ThreadPoolExecutor
from typing import Iterable

def _executor_queue_size(ex: ThreadPoolExecutor) -> int:
    """
    线程池排队任务 = 尚未取出的 work_queue + 已取出但未完成的线程数
    (_threads 里只要 thread.is_alive() 就认为任务未结束)。
    """
    waiting = ex._work_queue.qsize()                # 私有属性，但业界常用
    running = sum(1 for t in ex._threads if t.is_alive())
    return waiting + running

def get_queue_length(executors: Iterable[ThreadPoolExecutor]) -> int:
    """纯粹统计“等待中任务”数量（未被任何线程取走）。"""
    return sum(ex._work_queue.qsize() for ex in executors)