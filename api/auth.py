"""鉴权依赖(§2.19.6 / §6.4 鉴权在依赖注入层)。

- ``get_current_admin``：从 Authorization Bearer 解析 AES 会话令牌，校验用户存在。
- 未登录 40101、无权限 40103(§4.2)。

依赖通过 ``Depends(get_current_admin)`` 注入到受保护路由(§6.4，禁止业务函数散落判断)。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from api.deps import get_db
from config.settings import settings
from infra.db.models.admin import AdminUser
from infra.security.token import InvalidTokenError, decode_access_token
from schemas.errors import AuthError, ErrorCode


def _extract_token(authorization: str | None) -> str:
    """从 Authorization 头提取 Bearer token(§6.4)。"""
    if not authorization:
        # §4.2 40101 未认证
        raise AuthError("未认证，请先登录", code=ErrorCode.UNAUTHENTICATED)
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise AuthError("认证凭证格式错误", code=ErrorCode.UNAUTHENTICATED)
    return parts[1]


def get_current_admin(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> AdminUser:
    """解析并校验当前管理员(§6.4 依赖注入层统一鉴权)。

    §2.19.6 单用户：令牌主体即用户名；查库校验账户存在。
    Raises:
        AuthError(40101): 未认证/令牌无效或过期/账户不存在。
        AuthError(40103): 令牌主体非管理员账户(无权限)。
    """
    token = _extract_token(authorization)
    try:
        username = decode_access_token(token)
    except InvalidTokenError as exc:
        raise AuthError("认证已过期或无效，请重新登录", code=ErrorCode.UNAUTHENTICATED) from exc

    if not isinstance(username, str) or not username:
        raise AuthError("令牌主体异常", code=ErrorCode.UNAUTHENTICATED)

    user = db.query(AdminUser).filter(AdminUser.username == username).first()
    if user is None:
        # 令牌有效但用户已删除 -> 视为未认证(§4.2 40101)
        raise AuthError("账户不存在或已被移除", code=ErrorCode.UNAUTHENTICATED)
    # 单用户 MVP：默认账户即管理员；若未来扩展非管理员账户，此处校验 40103
    if user.username != settings.admin_username:
        raise AuthError("无权限访问管理端点", code=ErrorCode.FORBIDDEN)
    return user


__all__: list[str] = ["get_current_admin"]
