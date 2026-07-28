"""应用配置(开发规范§9.1 配置外部化；§2.19 敏感信息加密)。

通过环境变量/.env 注入；``.env`` 不入库(§2.4)。生产走 Docker Secrets / 密钥管理。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置(env 注入，默认值与 .env.example 对齐)。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- 运行环境(§9.1) ---
    app_env: str = Field(default="dev")
    log_level: str = Field(default="INFO")
    log_service: str = Field(default="fundlens-api")

    # --- PostgreSQL(§2.20) ---
    postgres_host: str = Field(default="postgres")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="fundlens")
    postgres_user: str = Field(default="fundlens")
    postgres_password: str = Field(default="changeme")
    database_url: str = Field(
        default="postgresql+psycopg://fundlens:changeme@postgres:5432/fundlens"
    )

    # --- Redis(ADR-004；MVP 可选，生产必需) ---
    redis_url: str = Field(default="redis://redis:6379/0")

    # --- API 服务 ---
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    streamlit_api_base: str = Field(default="http://api:8000")

    # --- 鉴权(P0-05 占位，§2.19.6 单用户 MVP) ---
    aes_key: str = Field(default="0" * 64)
    jwt_secret: str = Field(default="changeme-jwt-secret")
    admin_username: str = Field(default="admin")
    admin_session_ttl_min: int = Field(default=30)

    # --- 数据源(§2.15) ---
    tushare_token: str = Field(default="")

    # --- LLM(TP-06 R7 唯一硬依赖；C1 待确认) ---
    llm_provider: str = Field(default="deepseek")
    llm_api_key: str = Field(default="")
    llm_model: str = Field(default="deepseek-chat")
    llm_base_url: str = Field(default="https://api.deepseek.com/v1")
    llm_timeout: int = Field(default=30)
    llm_max_concurrency: int = Field(default=4)

    # --- NL 选基评测门禁(§4.1/§12) ---
    nl_accuracy_target: float = Field(default=0.85)

    # --- 响应信封免责声明(§5.2) ---
    disclaimer: str = Field(default="仅供参考，不构成投资建议")

    @property
    def is_prod(self) -> bool:
        return self.app_env.lower() == "prod"


@lru_cache
def get_settings() -> Settings:
    """获取单例配置(缓存避免重复读 env)。"""
    return Settings()


#: 模块级单例，便于直接 import(测试可 monkeypatch get_settings)。
settings: Settings = get_settings()
