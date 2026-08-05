"""Redis 缓存层(P1-11，详设§2.8 / ADR-004)。

热键缓存(fund:*)：仪表盘聚合 / Top10 榜单 / 单基评分 / 盘中 / 字段词典 / 宏观。

降级策略(§8.5)：
- Redis 可用 -> 走 Redis(多副本一致)。
- Redis 不可用(MVP 单机) -> 进程内 dict 兜底，不阻断核心查询。
- ``get_redis`` 成功/失败均缓存，避免每次请求重试拖慢 P95。

失效策略(§3.3.8)：权重变更 -> ``invalidate_score(code)`` 删 ``fund:score:{code}``；
定时任务刷新榜单缓存。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from infra.redis.client import get_redis

logger = logging.getLogger(__name__)

#: §2.8 热键 TTL(秒)。
TTL: dict[str, int] = {
    "dashboard": 5 * 60,  # 5 min
    "top10": 15 * 60,  # 15 min
    "score": 30 * 60,  # 30 min
    "intraday": 5 * 60,  # 5 min
    "glossary": 60 * 60,  # 1 h
    "macro": 60 * 60,  # 1 h
    "quality": 5 * 60,  # 5 min(§3.1 fund:quality:latest)
}

#: Key 模板(§2.8)。
KEY_TPL: dict[str, str] = {
    "dashboard": "fund:dashboard:{account_id}",
    "top10": "fund:top10:{type}",
    "score": "fund:score:{code}",
    "intraday": "fund:intraday:{code}",
    "glossary": "fund:glossary:{field}",
    "macro": "fund:macro:latest",
    "quality": "fund:quality:latest",
}

#: 进程内兜底缓存(Redis 不可用时)。
_memory_cache: dict[str, tuple[str, float]] = {}


def cache_key(name: str, **kw: Any) -> str:
    """构造缓存键(§2.8 模式)。"""
    tpl = KEY_TPL.get(name, f"fund:{name}")
    return tpl.format(**kw)


def cache_get(name: str, **kw: Any) -> Any:
    """读缓存；未命中返回 None。

    Redis 不可用 -> 走进程内 dict(检查过期)。
    """
    key = cache_key(name, **kw)
    client = get_redis()
    if client is not None:
        try:
            raw = client.get(key)
            return json.loads(raw) if raw else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache.get_failed", extra={"key": key, "err": str(exc)})
            return _memory_get(key)
    return _memory_get(key)


def cache_set(name: str, value: Any, **kw: Any) -> None:
    """写缓存(带 TTL)；Redis 不可用 -> 进程内 dict。"""
    key = cache_key(name, **kw)
    ttl = TTL.get(name, 5 * 60)
    payload = json.dumps(value, default=str, ensure_ascii=False)
    client = get_redis()
    if client is not None:
        try:
            client.setex(key, ttl, payload)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache.set_failed", extra={"key": key, "err": str(exc)})
    _memory_set(key, payload, ttl)


def cache_delete(name: str, **kw: Any) -> None:
    """删缓存(失效)。"""
    key = cache_key(name, **kw)
    client = get_redis()
    if client is not None:
        try:
            client.delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache.delete_failed", extra={"key": key, "err": str(exc)})
    _memory_cache.pop(key, None)


def invalidate_score(code: str) -> None:
    """权重变更失效(§3.3.8)：删 fund:score:{code}。"""
    cache_delete("score", code=code)


def _memory_get(key: str) -> Any:
    """进程内兜底读(检查过期)。"""
    import time

    entry = _memory_cache.get(key)
    if entry is None:
        return None
    payload, expires_at = entry
    if time.time() > expires_at:
        _memory_cache.pop(key, None)
        return None
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return None


def _memory_set(key: str, payload: str, ttl: int) -> None:
    """进程内兜底写。"""
    import time

    _memory_cache[key] = (payload, time.time() + ttl)


def clear_memory_cache() -> None:
    """清进程内缓存(测试用)。"""
    _memory_cache.clear()


__all__: list[str] = [
    "TTL",
    "KEY_TPL",
    "cache_key",
    "cache_get",
    "cache_set",
    "cache_delete",
    "invalidate_score",
    "clear_memory_cache",
]
