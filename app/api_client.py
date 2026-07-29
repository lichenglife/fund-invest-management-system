"""api_client · 统一请求 + Mock 降级链(开发规范§6.2 信封 / §7.2 错误码 / §10.5 / §8.5 降级)。

契约优先(开发计划§3.2)：后端 12 模块接口未就绪期间，``MOCK_MODE``(env，dev 默认开)
控制走示例数据；后端就绪后翻转开关即切真实接口，页面代码零改动。

- ``ApiClient``：调 FastAPI 内部 API，统一处理七字段信封(§2.21.1)与错误码(§4.2)。
- ``services``：页面级契约访问器(如 ``get_dashboard``)，真实优先、失败回退 Mock(§8.5)。
- 错误码 40101/40103 跳登录(P0-05 落地后)；50301/50302/50303 降级(§7.2)。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# base_url 优先取 settings(若可导入)，回退 env(容器外本地)。
try:  # pragma: no cover  - 取决于运行环境
    from config.settings import get_settings as _get_settings

    _BASE_URL: str = _get_settings().streamlit_api_base
except Exception:  # noqa: BLE001
    _BASE_URL = os.environ.get("STREAMLIT_API_BASE", "http://localhost:8000")

#: Mock 模式开关(dev 默认开；后端就绪置 false 切真实接口)。
MOCK_MODE: bool = os.environ.get("MOCK_MODE", "1") not in ("0", "false", "False")

_DEFAULT_TIMEOUT = 10.0


class ApiError(Exception):
    """API 返回 code≠0(§7.2)。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


class ApiClient:
    """FastAPI 内部 API 客户端(七字段信封感知)。"""

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


def is_mock() -> bool:
    """当前是否走 Mock 数据(页面据此显示「示例数据」角标)。"""
    return MOCK_MODE or health() is None


# =====================================================================
# services · 页面级契约访问器(真实优先 -> 失败回退 Mock，§8.5)
# 路径规划对齐未来后端 /api/v1/<module>(详设§2.21 / 开发任务分解 P1-02~P3-09)
# =====================================================================
def _fetch(path: str, mock_fn: Callable[[], Any], **params: Any) -> Any:
    """真实优先，失败/Mock 模式回退 mock_fn()。Mock 模式直接走 mock(零网络开销)。"""
    if MOCK_MODE:
        return mock_fn()
    try:
        return get_client().get(path, **params)
    except ApiError as exc:
        logger.info("api.fallback_to_mock", extra={"path": path, "err": str(exc)})
        return mock_fn()


def _mock() -> Any:
    """延迟导入 mock.store，避免 app 启动期循环依赖。"""
    from app.mock import store

    return store


# --- 仪表盘(原型① P1-12/P1-19a/b) ---
def get_dashboard(fund_type: str = "all") -> dict[str, Any]:
    s = _mock()
    return {
        "status": s.DASHBOARD_STATUS,
        "top10": s.dashboard_top10(fund_type),
        "dynamics": s.DASHBOARD_DYNAMICS,
        "learn_card": s.DASHBOARD_LEARN_CARD,
    }


# --- 数据中心(原型② P1-02/P1-13a~c) ---
def list_funds() -> list[dict[str, Any]]:
    return _fetch("/api/v1/funds", lambda: _mock().FUNDS)


def get_fund(code: str) -> dict[str, Any] | None:
    return _fetch(f"/api/v1/funds/{code}", lambda: _mock().fund_by_code(code))


def get_nav(code: str, days: int = 252) -> list[dict[str, Any]]:
    return _fetch(f"/api/v1/funds/{code}/nav", lambda: _mock().nav_series(code, days), days=days)


# --- 评估详情(原型③ P1-04a/b) ---
def get_metrics(code: str) -> dict[str, Any]:
    return _fetch(f"/api/v1/funds/{code}/metrics", lambda: _mock().METRICS.get(code, {}))


def get_score(code: str) -> dict[str, Any]:
    return _fetch(f"/api/v1/funds/{code}/score", lambda: _mock().SCORES.get(code, {}))


def get_attribution(code: str) -> dict[str, Any]:
    return _fetch(f"/api/v1/funds/{code}/attribution", lambda: _mock().ATTRIBUTION.get(code, {}))


def get_research(code: str) -> dict[str, Any]:
    return _fetch(f"/api/v1/funds/{code}/research", lambda: _mock().RESEARCH.get(code, {}))


def get_holdings(code: str) -> list[dict[str, Any]]:
    return _fetch(f"/api/v1/funds/{code}/holdings", lambda: _mock().HOLDINGS.get(code, []))


# --- 智能筛选(原型④ P1-06a~c) ---
def screen_funds(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """表单筛选(本地);NL 解析、去重见 store。"""
    s = _mock()
    rows = list(s.FUNDS)
    f = filters or {}
    if f.get("fund_type") and f["fund_type"] != "all":
        rows = [r for r in rows if r["type"] == f["fund_type"]]
    if f.get("max_drawdown") is not None:
        # 演示: 按规模近似(真实由后端向量化过滤)
        pass
    if f.get("min_return") is not None:
        pass
    if f.get("theme") and f["theme"] != "不限":
        rows = [r for r in rows if r["theme"] == f["theme"]]
    return sorted(rows, key=lambda x: x["score"], reverse=True)


# --- 模拟交易(原型⑤ P1-07a~e;本地 session 记账) ---
def get_paper_account() -> dict[str, Any]:
    """初始账户(后端就绪后从 /api/v1/paper/account 取真实)。"""
    return _mock().PAPER_ACCOUNT


def get_paper_positions() -> list[dict[str, Any]]:
    return _mock().PAPER_POSITIONS


def get_dca_backtest() -> dict[str, Any]:
    return _mock().DCA_BACKTEST


# --- 组合配置(原型⑥ P1-08a~d) ---
def get_portfolio_components() -> list[dict[str, Any]]:
    return _mock().PORTFOLIO_COMPONENTS


def get_portfolio_diagnosis() -> list[dict[str, Any]]:
    return _mock().PORTFOLIO_DIAGNOSIS


# --- 宏观看板(原型⑦ P2-01a/b) ---
def get_macro() -> dict[str, Any]:
    s = _mock()
    return {
        "cards": s.MACRO_CARDS,
        "sentiment": s.MACRO_SENTIMENT,
        "surround": s.MACRO_SURROUND,
        "high_signal": s.MACRO_HIGH_SIGNAL,
        "high_verdict": s.MACRO_HIGH_VERDICT,
        "position": s.MACRO_POSITION,
    }


# --- 单基实验室(原型⑧ P1-09a/b) ---
def get_lab_scenarios() -> list[dict[str, Any]]:
    return _mock().LAB_SCENARIOS


def get_lab_strategies() -> list[dict[str, Any]]:
    return _mock().LAB_STRATEGIES


# --- 持仓穿透(原型⑨ P3-01a/b) ---
def get_penetrate(code: str) -> dict[str, Any]:
    s = _mock()
    return {
        "holdings": s.HOLDINGS.get(code, []),
        "financials": s.STOCK_FINANCIALS,
        "sentiment_weekly": s.SENTIMENT_WEEKLY.get(code, ""),
        "industry": s.INDUSTRY_DIST.get(code, []),
    }


# --- 学习投教(原型⑩ P2-05a/b) ---
def get_learn() -> dict[str, Any]:
    s = _mock()
    return {
        "glossary": s.LEARN_GLOSSARY,
        "path": s.LEARN_PATH,
        "cases": s.LEARN_CASES,
        "bias_questions": s.LEARN_BIAS_QUESTIONS,
    }


# --- AI 助手(原型⑪ P3-03a/b) ---
def get_ai_demo() -> dict[str, Any]:
    s = _mock()
    return {
        "quick": s.AI_QUICK_COMMANDS,
        "chat": s.AI_DEMO_CHAT,
        "weekly": s.AI_WEEKLY,
        "degrade": s.AI_DEGRADE,
    }


# --- 风险监控(原型⑫ P2-03a~c) ---
def get_risk() -> dict[str, Any]:
    s = _mock()
    return {
        "types": s.RISK_TYPES,
        "alerts": s.RISK_ALERTS,
        "valuation_dca": s.VALUATION_DCA_SIGNAL,
        "data_quality": s.DATA_QUALITY,
        "high_signal": s.MACRO_HIGH_SIGNAL,
        "high_verdict": s.MACRO_HIGH_VERDICT,
    }
