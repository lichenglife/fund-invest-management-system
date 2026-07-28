"""SQLAlchemy 声明式基类(§2.20 表模型在 P0-04a 继承 ``Base``)。

同步驱动(MVP 单机；pandas/empyrical/vectorbt 均同步，§2.7 未要求 async)。
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类(P0-04a 各表继承)。"""
