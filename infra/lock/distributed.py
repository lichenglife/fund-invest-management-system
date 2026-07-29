"""分布式锁实现(详设§3.14.6 分布式锁与调度防重)。

§3.14.6：多副本时任务触发前获取 Redis ``SET NX`` 锁；获锁才执行，执行完删锁；
未获锁跳过，避免重复采集/重算。锁 token 用 uuid4，删锁前校验归属(防脑裂)。

> ADR-004：Redis 多副本必需；MVP 单机可省。无 Redis 时降级为内存锁(进程内互斥)，
> 不阻断单实例调度(§8.5 降级可观测)。
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: 锁默认过期时间(秒，§3.14.6 ex=3600)。
LOCK_TTL_DEFAULT = 3600

#: 锁 key 前缀(§3.14.6 fund:scheduler:lock:{job})。
_LOCK_PREFIX = "fund:scheduler:lock:"


class DistributedLock:
    """分布式锁抽象(§3.14.6)。

    实现：
    - ``RedisDistributedLock``：基于 Redis SET NX(多副本，生产必需)。
    - ``InMemoryLock``：进程内互斥(MVP 单机无 Redis 时降级)。
    """

    def acquire(self, job: str, ttl: int = LOCK_TTL_DEFAULT) -> bool:
        """尝试获取锁；成功返回 True，已被占返回 False。"""
        raise NotImplementedError

    def release(self, job: str) -> bool:
        """释放锁(校验 token 归属)；成功返回 True。"""
        raise NotImplementedError

    def with_lock(
        self, job: str, fn: Callable[[], T], ttl: int = LOCK_TTL_DEFAULT
    ) -> tuple[bool, T | None]:
        """带锁执行(§3.14.6 with_lock 伪代码)。

        Args:
            job: 任务标识。
            fn: 获锁后执行的函数。
            ttl: 锁过期秒数。
        Returns:
            (是否获锁, fn 返回值)；未获锁返回 (False, None)。
        """
        if not self.acquire(job, ttl=ttl):
            logger.info(
                "lock.skip", extra={"action": "lock", "job": job, "reason": "already_locked"}
            )
            return False, None
        try:
            result = fn()
            return True, result
        finally:
            self.release(job)


class RedisDistributedLock(DistributedLock):
    """Redis SET NX 分布式锁(§3.14.6)。

    token 用 uuid4，删锁前 Lua/校验归属防脑裂(避免误删他人锁)。
    """

    def __init__(self, redis_client: Any) -> None:
        """Args:
        redis_client: redis.Redis 实例(从 infra.redis.get_redis 获取)。
        """
        self._redis = redis_client

    def acquire(self, job: str, ttl: int = LOCK_TTL_DEFAULT) -> bool:
        token = uuid.uuid4().hex
        key = f"{_LOCK_PREFIX}{job}"
        # SET NX EX(§3.14.6 r.set(..., nx=True, ex=3600))
        ok = self._redis.set(key, token, nx=True, ex=ttl)
        if ok:
            # token 存线程本地供 release 校验
            _token_store[key] = token
            return True
        return False

    def release(self, job: str) -> bool:
        key = f"{_LOCK_PREFIX}{job}"
        token = _token_store.pop(key, None)
        if token is None:
            return False
        # 校验归属后删(防脑裂：仅当值仍是本 token 才删)
        current = self._redis.get(key)
        if current == token:
            self._redis.delete(key)
            return True
        # 锁已过期被他人获取，不删
        return False


class InMemoryLock(DistributedLock):
    """进程内锁(MVP 单机无 Redis 时降级，§8.5)。

    线程安全(threading.Lock)；无 TTL(进程内短期互斥足够)。
    """

    def __init__(self) -> None:
        self._held: set[str] = set()
        self._guard = threading.Lock()

    def acquire(self, job: str, ttl: int = LOCK_TTL_DEFAULT) -> bool:
        with self._guard:
            if job in self._held:
                return False
            self._held.add(job)
            return True

    def release(self, job: str) -> bool:
        with self._guard:
            if job in self._held:
                self._held.discard(job)
                return True
            return False


#: 线程本地 token 存储(RedisDistributedLock 用，供 release 校验归属)。
_token_store: dict[str, str] = {}


def get_lock(redis_client: Any | None = None) -> DistributedLock:
    """获取锁实现：有 Redis 用分布式锁，否则降级内存锁(§8.5)。

    Args:
        redis_client: 显式传入的 Redis 客户端；None 自动获取(可能返回内存锁)。
    """
    if redis_client is None:
        from infra.redis.client import get_redis

        redis_client = get_redis()
    if redis_client is not None:
        return RedisDistributedLock(redis_client)
    # 无 Redis 降级(§8.5 可观测)
    logger.warning("lock.redis_unavailable", extra={"action": "lock", "degraded": True})
    return InMemoryLock()


__all__: list[str] = [
    "DistributedLock",
    "RedisDistributedLock",
    "InMemoryLock",
    "get_lock",
    "LOCK_TTL_DEFAULT",
]
