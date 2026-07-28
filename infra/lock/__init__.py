"""infra.lock · 分布式锁(详细设计§3.14.6 分布式锁与调度防重)。

占位：P1-10c 幂等 + 单实例锁(Redis SET NX，Redlock 思路)将在此落地。
ADR-004：多副本下 Redis 为必需，承载调度锁防重触发。
"""

__all__: list[str] = []

# TODO(P1-10c, §3.14.6): RedisDistributedLock (SET NX EX + Lua 释放，防脑裂)
