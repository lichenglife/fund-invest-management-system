"""Redis 缓存层单测(P1-11，详设§2.8 / ADR-004)。

覆盖：
- 键构造(§2.8 模式)、TTL 表口径。
- set/get 往返(Redis 不可用走进程内兜底)。
- TTL 过期(进程内)。
- invalidate_score 失效(§3.3.8 权重变更)。
- 降级：Redis 不可用不抛异常、不阻断。
"""

from __future__ import annotations

import time

import pytest

import infra.redis.cache as cache_mod
from infra.redis.cache import (
    TTL,
    cache_delete,
    cache_get,
    cache_key,
    cache_set,
    clear_memory_cache,
    invalidate_score,
)


@pytest.fixture(autouse=True)
def _isolated_cache():
    """每个测试清进程内缓存 + 重置 redis 单例。"""
    clear_memory_cache()
    # 强制 get_redis 返回 None(Redis 可能未连) -> 走进程内兜底
    cache_mod.get_redis = lambda: None  # type: ignore[assignment]
    yield
    clear_memory_cache()


class TestCacheKey:
    """§2.8 键模式。"""

    def test_score_key(self) -> None:
        assert cache_key("score", code="000001.OF") == "fund:score:000001.OF"

    def test_dashboard_key(self) -> None:
        assert cache_key("dashboard", account_id="default") == "fund:dashboard:default"

    def test_top10_key(self) -> None:
        assert cache_key("top10", type="stock") == "fund:top10:stock"

    def test_glossary_key(self) -> None:
        assert cache_key("glossary", field="nav") == "fund:glossary:nav"

    def test_macro_key(self) -> None:
        assert cache_key("macro") == "fund:macro:latest"


class TestTTL:
    """§2.8 TTL 口径。"""

    def test_score_ttl_30min(self) -> None:
        assert TTL["score"] == 30 * 60

    def test_dashboard_ttl_5min(self) -> None:
        assert TTL["dashboard"] == 5 * 60

    def test_top10_ttl_15min(self) -> None:
        assert TTL["top10"] == 15 * 60

    def test_glossary_ttl_1h(self) -> None:
        assert TTL["glossary"] == 60 * 60


class TestSetGet:
    """set/get 往返(进程内兜底)。"""

    def test_roundtrip_dict(self) -> None:
        cache_set("score", code="A", value={"composite": 82.5})
        assert cache_get("score", code="A") == {"composite": 82.5}

    def test_miss_returns_none(self) -> None:
        assert cache_get("score", code="unknown") is None

    def test_overwrite(self) -> None:
        cache_set("score", code="A", value={"v": 1})
        cache_set("score", code="A", value={"v": 2})
        assert cache_get("score", code="A") == {"v": 2}

    def test_delete(self) -> None:
        cache_set("score", code="A", value={"v": 1})
        cache_delete("score", code="A")
        assert cache_get("score", code="A") is None

    def test_json_serialization(self) -> None:
        """复杂对象经 JSON 序列化往返。"""
        data = {"code": "000001", "factors": {"ret": 80.0, "risk": 70.0}, "list": [1, 2, 3]}
        cache_set("score", code="A", value=data)
        assert cache_get("score", code="A") == data


class TestTTLExpiry:
    """TTL 过期(进程内)。"""

    def test_expired_entry_returns_none(self) -> None:
        """写入后篡改过期时间 -> 过期返回 None。"""
        import infra.redis.cache as cm

        cache_set("score", code="A", value={"v": 1})
        # 篡改进程内缓存过期时间为过去
        key = cache_key("score", code="A")
        cm._memory_cache[key] = (cm._memory_cache[key][0], time.time() - 1)
        assert cache_get("score", code="A") is None


class TestInvalidateScore:
    """§3.3.8 权重变更失效。"""

    def test_invalidate_clears_score(self) -> None:
        cache_set("score", code="A", value={"composite": 82.5})
        invalidate_score("A")
        assert cache_get("score", code="A") is None

    def test_invalidate_other_codes_unaffected(self) -> None:
        cache_set("score", code="A", value={"v": 1})
        cache_set("score", code="B", value={"v": 2})
        invalidate_score("A")
        assert cache_get("score", code="B") == {"v": 2}


class TestDegradation:
    """Redis 不可用降级(§8.5)。"""

    def test_redis_unavailable_uses_memory(self) -> None:
        """get_redis=None -> 进程内兜底，不抛异常。"""
        cache_set("score", code="A", value={"v": 1})
        assert cache_get("score", code="A") == {"v": 1}

    def test_redis_unavailable_does_not_block(self) -> None:
        """Redis 不可用时 set/get/delete 均不抛异常。"""
        cache_set("dashboard", account_id="x", value={"k": "v"})
        assert cache_get("dashboard", account_id="x") == {"k": "v"}
        cache_delete("dashboard", account_id="x")
        # 多次调用不崩溃
        cache_get("dashboard", account_id="x")
