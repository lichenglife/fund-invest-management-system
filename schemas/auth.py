"""鉴权请求/响应模型(§2.19.6 / §2.21 信封)。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """管理员登录请求(§2.19.6)。"""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    """首次登录强制改密(§2.19.6 强制首次登录修改)。"""

    model_config = ConfigDict(extra="forbid")

    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class LoginData(BaseModel):
    """登录成功响应载荷。"""

    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "Bearer"
    must_change_password: bool = False
    expires_in_minutes: int


class WhoAmIData(BaseModel):
    """当前用户信息(受保护端点示例)。"""

    model_config = ConfigDict(extra="forbid")

    username: str
    must_change_password: bool
