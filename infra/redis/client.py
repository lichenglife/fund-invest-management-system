"""infra.redis 包 · Redis 客户端(ADR-004；MVP 可选，生产/多副本必需)。

承载共享评分缓存(§2.8)、admin 会话(§2.19.6)、调度锁(§3.14.6)。
MVP 单机可省；连接失败返回 None，不阻断核心查询(§8.5 降级)。
"""

from __future__ import annotations

import logging

from redis import Redis
from redis.exceptions import RedisError

from config.settings import settings

logger = logging.getLogger(__name__)

_client: Redis | None = None  # type: ignore[type-arg]
_tried: bool = False


def get_redis() -> Redis | None:  # type: ignore[type-arg]
    """获取 Redis 单例；连接失败/未配置返回 None(MVP 降级，§8.5)。

    成功缓存、失败也缓存(避免每次请求重试拖慢 P95)；可由调用方判断 None 走内存兜底。
    """
    global _client, _tried
    if _tried:
        return _client
    _tried = True
    try:
        client = Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        _client = client
        logger.info("redis.connected", extra={"action": "redis.connect"})
    except RedisError as exc:
        _client = None
        logger.warning(
            "redis.unavailable",
            extra={"action": "redis.connect", "degraded": True, "err": str(exc)},
        )
    return _client


__all__: list[str] = ["get_redis"]
