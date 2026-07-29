"""分布式锁单测(P1-01d，详设§3.14.6 分布式锁与调度防重)。

覆盖：Redis SET NX 获锁/未获锁跳过、token 归属校验防脑裂、无 Redis 内存兜底。
"""

from __future__ import annotations

import threading

import pytest

from infra.lock.distributed import LOCK_TTL_DEFAULT, InMemoryLock, RedisDistributedLock, get_lock


class _FakeRedis:
    """最小 fake Redis(模拟 set nx/get/delete)。"""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self._data:
            return False
        self._data[key] = value
        return True

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def delete(self, key: str) -> int:
        if key in self._data:
            del self._data[key]
            return 1
        return 0


class TestRedisDistributedLock:
    """§3.14.6 Redis SET NX 锁。"""

    def test_acquire_success(self) -> None:
        """首次获锁成功(SET NX)。"""
        r = _FakeRedis()
        lock = RedisDistributedLock(r)
        assert lock.acquire("collect") is True
        assert lock.acquire("collect") is False  # 已被占

    def test_with_lock_skip_if_held(self) -> None:
        """未获锁 -> 跳过，fn 不执行(§3.14.6)。"""
        r = _FakeRedis()
        lock1 = RedisDistributedLock(r)
        lock2 = RedisDistributedLock(r)  # 另一实例(同 Redis)
        called: list[int] = []

        def _job() -> str:
            called.append(1)
            return "done"

        # lock1 持锁(模拟长任务)
        assert lock1.acquire("collect") is True
        # lock2 尝试同 job -> 未获锁 -> 跳过
        ok, result = lock2.with_lock("collect", _job)
        assert ok is False
        assert result is None
        assert called == []  # fn 未执行

    def test_with_lock_executes_when_acquired(self) -> None:
        """获锁 -> 执行 fn，结束释放锁。"""
        r = _FakeRedis()
        lock = RedisDistributedLock(r)
        ok, result = lock.with_lock("collect", lambda: "ok")
        assert ok is True
        assert result == "ok"
        # 释放后可再获
        assert lock.acquire("collect") is True

    def test_release_token_guard_brain_split(self) -> None:
        """删锁前校验 token 归属(防脑裂，§3.14.6)。

        模拟：lock 获锁后，Redis 中 token 被外部替换(过期后他人获锁)；
        此时 release 不应误删他人锁。
        """
        r = _FakeRedis()
        lock = RedisDistributedLock(r)
        assert lock.acquire("collect") is True
        # 模拟锁过期后被他人获取(Redis 中 token 变了)
        r._data["fund:scheduler:lock:collect"] = "someone-else-token"
        # release 校验归属：store 里是本实例 token，但 Redis 已是他人 token -> 不删
        assert lock.release("collect") is False
        assert r.get("fund:scheduler:lock:collect") == "someone-else-token"  # 未删他人锁

    def test_ttl_default(self) -> None:
        assert LOCK_TTL_DEFAULT == 3600  # §3.14.6 ex=3600


class TestInMemoryLock:
    """§8.5 无 Redis 降级内存锁。"""

    def test_acquire_release(self) -> None:
        lock = InMemoryLock()
        assert lock.acquire("job") is True
        assert lock.acquire("job") is False  # 占用
        assert lock.release("job") is True
        assert lock.acquire("job") is True  # 释放后可再获

    def test_thread_safety(self) -> None:
        """多线程互斥(进程内)。"""
        lock = InMemoryLock()
        winners: list[int] = []

        def _try() -> None:
            if lock.acquire("shared"):
                winners.append(1)

        threads = [threading.Thread(target=_try) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(winners) == 1  # 仅一个获锁


class TestGetLock:
    """降级工厂：有 Redis 用分布式锁，否则内存锁。"""

    def test_with_redis(self) -> None:
        lock = get_lock(redis_client=_FakeRedis())
        assert isinstance(lock, RedisDistributedLock)

    def test_without_redis_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 Redis -> 降级内存锁(§8.5)。"""
        from infra.redis import client as redis_client_mod

        monkeypatch.setattr(redis_client_mod, "get_redis", lambda: None)
        lock = get_lock()
        assert isinstance(lock, InMemoryLock)
