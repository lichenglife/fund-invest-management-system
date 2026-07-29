"""管理鉴权域 ORM 模型(详设§2.19.6 单用户 MVP 轻量鉴权)。

> 表名 ``admin_users`` 与字段为推断(§2.20 未列出此表，属 D2 同类待澄清)；
> §2.19.6 明确要求"密码 AES-256 加密后落库"+"默认管理员账户初始化"，
> 据此设计最小表结构。见 docs/DEFERRED.md D2。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import TIMESTAMP, BigInteger, Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from infra.db.base import Base


class AdminUser(Base):
    """管理员账户表(§2.19.6)。

    单用户 MVP：默认账户 ``admin``，初始密码首次启动从 env 注入，强制首次登录修改。
    密码以 AES-256-GCM 加密后存 ``password_encrypted``(base64)，不存明文(§2.19.6)。
    """

    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_encrypted: Mapped[str] = mapped_column(String(256), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true"), default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )
