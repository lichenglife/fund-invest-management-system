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

    def get(self, path: str, *, headers: dict[str, str] | None = None, **params: Any) -> Any:
        return self._request("GET", path, params=params, headers=headers)

    def post(self, path: str, *, headers: dict[str, str] | None = None, **json_body: Any) -> Any:
        return self._request("POST", path, json=json_body, headers=headers)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        try:
            resp = self._client.request(method, path, params=params, json=json, headers=headers)
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
def _dashboard_mock(fund_type: str) -> dict[str, Any]:
    s = _mock()
    return {
        "status": s.DASHBOARD_STATUS,
        "top10": s.dashboard_top10(fund_type),
        "dynamics": s.DASHBOARD_DYNAMICS,
        "learn_card": s.DASHBOARD_LEARN_CARD,
    }


def get_dashboard(fund_type: str = "all") -> dict[str, Any]:
    return _fetch("/api/v1/dashboard", lambda: _dashboard_mock(fund_type), type=fund_type)


# --- 数据中心(原型② P1-02/P1-13a~c) ---
def list_funds(
    q: str | None = None, fund_type: str | None = None, page: int = 1, page_size: int = 100
) -> list[dict[str, Any]]:
    """基金列表(§3.2.2)。真实后端返回 {items,total,...}，提取 items；mock 返回 list。"""
    data = _fetch(
        "/api/v1/funds",
        lambda: _mock().FUNDS,
        q=q, type=fund_type, page=page, page_size=page_size,
    )
    if isinstance(data, dict):
        return data.get("items", [])
    return data or []


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
def screen_funds(
    filters: dict[str, Any] | None = None, sort_by: str = "综合评分"
) -> list[dict[str, Any]]:
    """表单筛选 + 排序(本地演示)；NL 解析、去重见 store。

    筛选口径(滑杆为百分点，指标为比率，故阈值 ÷100)：
    - ``fund_type``/``theme`` 等值过滤；
    - ``max_drawdown`` ≤ 阈值(回撤为负值，|drawdown| 越小越好 -> drawdown ≥ -阈值/100)；
    - ``min_return`` ≥ 阈值/100；``min_tenure`` ≥ 年。
    排序：综合评分 / 夏普 / 回撤(升序，越小越好) / 年化(降序)。
    真实接口由后端向量化过滤；此处 Mock 形状与之一致(切换零改动)。
    """
    s = _mock()
    rows = list(s.FUNDS)
    f = filters or {}
    if f.get("fund_type") and f["fund_type"] != "all":
        rows = [r for r in rows if r["type"] == f["fund_type"]]
    if f.get("theme") and f["theme"] != "不限":
        rows = [r for r in rows if r["theme"] == f["theme"]]
    if f.get("max_drawdown") is not None:
        thr = float(f["max_drawdown"]) / 100.0
        rows = [r for r in rows if s.fund_metrics_summary(r["code"])["max_drawdown"] >= -thr]
    if f.get("min_return") is not None:
        thr = float(f["min_return"]) / 100.0
        rows = [r for r in rows if s.fund_metrics_summary(r["code"])["return_pct"] >= thr]
    if f.get("min_tenure") is not None:
        thr = float(f["min_tenure"])
        rows = [r for r in rows if s.fund_manager_tenure_years(r["code"]) >= thr]

    # 排序键(综合评分用 fund.score；其余用指标摘要)
    sort_keys: dict[str, tuple[str, bool]] = {
        "综合评分": ("score", True),
        "夏普": ("sharpe", True),
        "年化": ("return_pct", True),
        "回撤": ("max_drawdown", True),  # 回撤为负，升序=回撤小(优)在前
    }
    field, desc = sort_keys.get(sort_by, ("score", True))
    if field == "score":
        return sorted(rows, key=lambda x: x["score"], reverse=desc)
    return sorted(rows, key=lambda x: s.fund_metrics_summary(x["code"])[field], reverse=desc)


# --- 模拟交易(原型⑤ P1-07a~e;本地 session 记账) ---
# 注：账户/持仓用 state.py 本地记账(不连后端)，以下仅初始/定投回测走降级链。
def get_paper_account() -> dict[str, Any]:
    """初始账户(后端就绪后从 /api/v1/paper/account 取真实)。"""
    return _fetch("/api/v1/paper/account", lambda: _mock().PAPER_ACCOUNT)


def get_paper_positions() -> list[dict[str, Any]]:
    return _fetch("/api/v1/paper/positions", lambda: _mock().PAPER_POSITIONS)


def get_dca_backtest() -> dict[str, Any]:
    return _fetch("/api/v1/paper/dca-backtest", lambda: _mock().DCA_BACKTEST)


# --- 组合配置(原型⑥ P1-08a~d) ---
def get_portfolio_components() -> list[dict[str, Any]]:
    return _fetch("/api/v1/portfolio/components", lambda: _mock().PORTFOLIO_COMPONENTS)


def get_portfolio_diagnosis() -> list[dict[str, Any]]:
    return _fetch("/api/v1/portfolio/diagnosis", lambda: _mock().PORTFOLIO_DIAGNOSIS)


# --- 宏观看板(原型⑦ P2-01a/b) ---
def _macro_mock() -> dict[str, Any]:
    s = _mock()
    return {
        "cards": s.MACRO_CARDS,
        "sentiment": s.MACRO_SENTIMENT,
        "surround": s.MACRO_SURROUND,
        "high_signal": s.MACRO_HIGH_SIGNAL,
        "high_verdict": s.MACRO_HIGH_VERDICT,
        "position": s.MACRO_POSITION,
    }


def get_macro() -> dict[str, Any]:
    return _fetch("/api/v1/macro", _macro_mock)


# --- 单基实验室(原型⑧ P1-09a/b) ---
_LAB_SCENARIO_LABEL = {"conservative": "保守", "baseline": "基准", "optimistic": "乐观"}


def get_lab_breakeven(code: str) -> dict[str, Any]:
    """回本测算(§3.8.2)。真实返 {return_rate, breakeven_gain_pct, months_to_breakeven,...}。"""
    return _fetch(f"/api/v1/funds/{code}/breakeven", lambda: {"available": False})


def get_lab_scenarios(code: str) -> list[dict[str, Any]]:
    """三情景推演(§3.8.2)。

    真实返 {months, projections:{保守/基准/乐观:[curve]}, assumptions}；
    适配为页面消费的列表 [{scenario, expected, final_value, impact}]。
    mock 直接返列表。
    """
    data = _fetch(f"/api/v1/funds/{code}/scenarios", lambda: _mock().LAB_SCENARIOS)
    if isinstance(data, list):
        return data
    # 真实后端 -> 适配为摘要表
    rows: list[dict[str, Any]] = []
    projections = data.get("projections", {}) if isinstance(data, dict) else {}
    assumptions = data.get("assumptions", {}) if isinstance(data, dict) else {}
    for key, label in _LAB_SCENARIO_LABEL.items():
        curve = projections.get(key, [])
        final = curve[-1]["value"] if curve else None
        ann = assumptions.get(key)
        rows.append({
            "scenario": label,
            "expected": ann,
            "final_value": final,
            "impact": "正收益" if (ann or 0) > 0 else "负收益",
        })
    return rows


def get_lab_strategies(code: str) -> list[dict[str, Any]]:
    """五策略对照(§3.8.2)。真实返 [{strategy,name,final_value,total_return,max_drawdown,note}]。"""
    data = _fetch(f"/api/v1/funds/{code}/strategies", lambda: _mock().LAB_STRATEGIES)
    if isinstance(data, list):
        return data
    return []


# --- 持仓穿透(原型⑨ P3-01a/b) ---
def _penetrate_mock(code: str) -> dict[str, Any]:
    s = _mock()
    return {
        "holdings": s.HOLDINGS.get(code, []),
        "financials": s.STOCK_FINANCIALS,
        "sentiment_weekly": s.SENTIMENT_WEEKLY.get(code, ""),
        "industry": s.INDUSTRY_DIST.get(code, []),
    }


def get_penetrate(code: str) -> dict[str, Any]:
    return _fetch(f"/api/v1/funds/{code}/penetrate", lambda: _penetrate_mock(code))


# --- 学习投教(原型⑩ P2-05a/b) ---
def _learn_mock() -> dict[str, Any]:
    s = _mock()
    return {
        "glossary": s.LEARN_GLOSSARY,
        "path": s.LEARN_PATH,
        "cases": s.LEARN_CASES,
        "bias_questions": s.LEARN_BIAS_QUESTIONS,
    }


def get_learn() -> dict[str, Any]:
    return _fetch("/api/v1/learn", _learn_mock)


# --- AI 助手(原型⑪ P3-03a/b) ---
def _ai_demo_mock() -> dict[str, Any]:
    s = _mock()
    return {
        "quick": s.AI_QUICK_COMMANDS,
        "chat": s.AI_DEMO_CHAT,
        "weekly": s.AI_WEEKLY,
        "degrade": s.AI_DEGRADE,
    }


def get_ai_demo() -> dict[str, Any]:
    return _fetch("/api/v1/ai/demo", _ai_demo_mock)


# --- 风险监控(原型⑫ P2-03a~c) ---
def _risk_mock() -> dict[str, Any]:
    s = _mock()
    return {
        "types": s.RISK_TYPES,
        "alerts": s.RISK_ALERTS,
        "valuation_dca": s.VALUATION_DCA_SIGNAL,
        "data_quality": s.DATA_QUALITY,
        "high_signal": s.MACRO_HIGH_SIGNAL,
        "high_verdict": s.MACRO_HIGH_VERDICT,
    }


def get_risk() -> dict[str, Any]:
    return _fetch("/api/v1/risk", _risk_mock)


# --- 后台管理(详设§2.16 系统监控 / §3.14 任务调度与监控 / §2.19.6 管理端点鉴权 / P1-10b) ---
#: 管理员会话令牌(登录后由页面 set_admin_token 写入；真实模式请求带 Bearer 头)。
_ADMIN_TOKEN: str | None = None


def set_admin_token(token: str | None) -> None:
    """页面登录成功后写入令牌(§2.19.6 30min session)。"""
    global _ADMIN_TOKEN
    _ADMIN_TOKEN = token


def _admin_login_mock() -> dict[str, Any]:
    """Mock 登录(开发期；返回示例令牌，不校验密码)。"""
    return {
        "access_token": "mock-admin-token",
        "must_change_password": False,
        "expires_in_minutes": 30,
    }


def admin_login(username: str, password: str) -> dict[str, Any]:
    """管理员登录(§2.19.6 AES 密码校验)；Mock 模式直接返示例令牌。"""
    if MOCK_MODE:
        token = _admin_login_mock()
        set_admin_token(token["access_token"])
        return token
    try:
        data = get_client().post("/api/v1/admin/login", username=username, password=password)
        set_admin_token(data.get("access_token"))
        return data
    except ApiError:
        return _admin_login_mock()


def _admin_headers() -> dict[str, str]:
    """构造 admin 鉴权头(§2.19.6 Bearer)。"""
    return {"Authorization": f"Bearer {_ADMIN_TOKEN}"} if _ADMIN_TOKEN else {}


def _admin_fetch(path: str, mock_fn: Callable[[], Any], **params: Any) -> Any:
    """admin 鉴权请求：真实优先(带 Bearer)，失败/Mock 模式回退 mock_fn。"""
    if MOCK_MODE:
        return mock_fn()
    try:
        return get_client().get(path, headers=_admin_headers(), **params)
    except ApiError as exc:
        logger.info("api.fallback_to_mock", extra={"path": path, "err": str(exc)})
        return mock_fn()


def _admin_jobs_mock() -> list[dict[str, Any]]:
    return _mock().ADMIN_JOBS


def get_admin_jobs(limit: int = 100, days: int = 7) -> list[dict[str, Any]]:
    """定时任务执行历史(§3.14.3 scheduler_jobs)。"""
    return _admin_fetch("/api/v1/admin/jobs", _admin_jobs_mock, limit=limit, days=days)


def _admin_monitor_mock() -> dict[str, Any]:
    return _mock().ADMIN_MONITOR


def get_admin_monitor() -> dict[str, Any]:
    """§2.16 五维监控汇总(数据采集/数据质量/API/定时任务/资源)。"""
    return _admin_fetch("/api/v1/admin/monitor", _admin_monitor_mock)


def _admin_quality_mock() -> dict[str, Any]:
    return _mock().ADMIN_QUALITY


def get_admin_quality() -> dict[str, Any]:
    """数据质量看板(对齐 P2-03c /quality/dashboard)。"""
    return _admin_fetch("/api/v1/admin/quality", _admin_quality_mock)


def _admin_change_mock() -> dict[str, Any]:
    return _mock().ADMIN_CHANGE_ASSESSMENT


def get_admin_change_assessment() -> dict[str, Any]:
    """变更评审评估(开发规范§9.3 OQ + §2.16 阈值触发)。"""
    return _admin_fetch("/api/v1/admin/change-assessment", _admin_change_mock)


def trigger_admin_job(job: str, **kwargs: Any) -> dict[str, Any]:
    """手动触发采集作业(§3.14.4，须管理员)；Mock 模式返示例结果。"""
    if MOCK_MODE:
        return {"upserted": 1, "job": job, "trigger": "manual", "status": "success"}
    try:
        return get_client().post(
            "/api/v1/admin/trigger-job", headers=_admin_headers(), job=job, **kwargs
        )
    except ApiError as exc:
        logger.info("api.fallback_to_mock", extra={"path": "trigger-job", "err": str(exc)})
        return {"upserted": 0, "job": job, "trigger": "manual", "status": "failed"}
