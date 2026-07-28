"""api_client · 统一请求封装(开发规范§6.2 信封 / §7.2 错误码 / §10.5)。

调 FastAPI 内部 API，统一处理信封与错误码 -> 全局提示 / 降级。
禁止硬编码 URL/Token(§10.5)；错误码 40101/40103 跳登录(P0-05 落地后)。
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# base_url 优先取 settings(若可导入)，回退 env(容器外本地)。
try:  # pragma: no cover  - 取决于运行环境
    from config.settings import get_settings as _get_settings

    _BASE_URL: str = _get_settings().streamlit_api_base
except Exception:  # noqa: BLE001
    _BASE_URL = os.environ.get("STREAMLIT_API_BASE", "http://localhost:8000")

_DEFAULT_TIMEOUT = 10.0


class ApiError(Exception):
    """API 返回 code≠0(§7.2)。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class ApiClient:
    """FastAPI 内部 API 客户端(信封感知)。"""

    def __init__(self, base_url: str = _BASE_URL, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def _unwrap(self, body: dict[str, Any]) -> Any:
        code = body.get("code", -1)
        if code == 0:
            return body.get("data")
        raise ApiError(code, body.get("message") or "请求失败")

    def get(self, path: str, **params: Any) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, **json_body: Any) -> Any:
        return self._request("POST", path, json=json_body)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = self._client.request(method, path, **kwargs)
            resp.raise_for_status()
            return self._unwrap(resp.json())
        except httpx.HTTPError as exc:
            # §8.5 降级：网络错误不阻断，返回 None + 日志
            logger.warning("api.network_error", extra={"action": "api_call", "err": str(exc)})
            raise ApiError(50302, "网络连接失败，请稍后重试") from exc


_client: ApiClient | None = None


def get_client() -> ApiClient:
    """单例客户端。"""
    global _client
    if _client is None:
        _client = ApiClient()
    return _client


def health() -> dict[str, str] | None:
    """健康探测(用于首页状态指示)；失败返回 None(降级，§8.5)。"""
    try:
        data = get_client().get("/api/v1/health")
        return data if isinstance(data, dict) else None
    except ApiError:
        return None
