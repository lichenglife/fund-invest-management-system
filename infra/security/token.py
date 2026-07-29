"""AES 会话令牌签发与校验(详设§2.19.6)。

§2.19.6 会话：登录成功签发短期有效期令牌(默认 30 min，可配)，admin 请求须携带，
过期重新登录。**前后端 AES 加解密**：令牌即 AES-256-GCM 加密后的 payload(base64)，
无独立 JWT 依赖(§2.19.6 未指定 JWT；密钥复用 AES_KEY)。

payload 明文格式：``<username>|<expire_unix>``；解密后校验过期与用户。
"""

from __future__ import annotations

import time

from config.settings import settings
from infra.security import crypto

_SEP = "|"


def create_access_token(subject: str, *, ttl_minutes: int | None = None) -> str:
    """签发 AES 会话令牌(§2.19.6)。

    Args:
        subject: 令牌主体(用户名)。
        ttl_minutes: 有效期分钟，默认取 settings.admin_session_ttl_min。
    Returns:
        AES-256-GCM 加密的 base64 令牌(前端原样携带，后端解密)。
    """
    ttl = ttl_minutes if ttl_minutes is not None else settings.admin_session_ttl_min
    expire = int(time.time()) + ttl * 60
    payload = f"{subject}{_SEP}{expire}"
    return crypto.encrypt(payload)


class InvalidTokenError(Exception):
    """令牌无效或过期(映射 40101)。"""


def decode_access_token(token: str) -> str:
    """校验并解码 AES 会话令牌(§2.19.6)。

    Args:
        token: create_access_token() 产出的令牌。
    Returns:
        令牌主体(用户名)。
    Raises:
        InvalidTokenError: 令牌损坏、密钥不符或已过期。
    """
    try:
        plain = crypto.decrypt(token)
    except Exception as exc:  # noqa: BLE001  统一映射为令牌无效
        raise InvalidTokenError("令牌无效") from exc
    if _SEP not in plain:
        raise InvalidTokenError("令牌格式异常")
    subject, expire_str = plain.rsplit(_SEP, 1)
    try:
        expire = int(expire_str)
    except ValueError as exc:
        raise InvalidTokenError("令牌过期字段异常") from exc
    if expire < int(time.time()):
        raise InvalidTokenError("令牌已过期")
    return subject


__all__: list[str] = ["create_access_token", "decode_access_token", "InvalidTokenError"]
