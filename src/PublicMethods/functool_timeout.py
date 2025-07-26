import functools
import concurrent.futures
import threading
import logging
log = logging.getLogger(__name__)

class TimeoutException(Exception):
    """函数执行超时"""


def timeout(seconds: float):
    """
    装饰器：在独立线程中运行函数，等待 seconds 秒。
    超时则抛出 TimeoutException。
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 用单线程池跑一次调用
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, *args, **kwargs)
                try:
                    return future.result(timeout=seconds)
                except concurrent.futures.TimeoutError:
                    # （可选）记录一下哪个线程还没结束
                    th = threading.current_thread().name
                    raise TimeoutException(
                        f"调用 `{func.__name__}` 超时（>{seconds}s）"
                    )

        return wrapper

    return decorator


def retry_on_timeout(timeout_sec: int, retries: int):
    """
          超时后重试装饰器：
       - timeout_sec: 每次调用的超时时间
       - retries: 最多重试次数（包含第一次调用）
    """

    def decorator(func):
        # 先给 func 绑定一个简单的 timeout
        timed = timeout(timeout_sec)(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, retries + 1):
                try:
                    return timed(*args, **kwargs)
                except TimeoutException as e:
                    last_exc = e
                    log.warning(f"[{func.__name__}] 第{attempt}次调用超时，准备重试…")
            # 如果所有 attempt 都超时，则抛最后一次异常
            raise last_exc

        return wrapper

    return decorator


import asyncio
import functools
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


class AsyncTimeoutException(Exception):
    """异步函数超时"""


def retry_on_timeout_async(timeout_sec: float, retries: int):
    """
    异步超时重试装饰器：
      - timeout_sec: 每次调用的超时时间（秒）
      - retries: 最多尝试次数（包含第一次）
    只对 asyncio 环境有效，必须在 async 函数上使用。
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc: Exception | None = None
            for attempt in range(1, retries + 1):
                try:
                    # asyncio.wait_for 会在协程超过 timeout_sec 秒后抛 asyncio.TimeoutError
                    return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_sec)
                except asyncio.TimeoutError as e:
                    last_exc = AsyncTimeoutException(
                        f"[{func.__name__}] 第 {attempt} 次调用超时（>{timeout_sec}s），准备重试…"
                    )
                    # 你也可以改为 logger.warning(...)
                    log.warning(last_exc)
                except Exception as e:
                    # 如果是其他异常，直接抛，不再重试
                    raise
            # 如果所有重试都超时，则抛出最后一次 AsyncTimeoutException
            raise last_exc  # type: ignore

        return wrapper  # type: ignore

    return decorator
