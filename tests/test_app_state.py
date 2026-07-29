"""state session_state 封装单测(开发规范§10.3)。

用 dict 替身 st.session_state，避免依赖 Streamlit 运行时。
"""

from __future__ import annotations

from app import state
from app.mock import store


class _FakeSessionState(dict):
    """dict 子类，模拟 st.session_state 的 get/__contains__/__setitem__。"""


def _patch_session(monkeypatch, initial: dict | None = None) -> _FakeSessionState:
    ss = _FakeSessionState(initial or {})
    monkeypatch.setattr(state.st, "session_state", ss)
    return ss


class TestStateBasic:
    def test_get_default(self, monkeypatch) -> None:
        _patch_session(monkeypatch)
        assert state.get("nope", "d") == "d"

    def test_set_and_get(self, monkeypatch) -> None:
        _patch_session(monkeypatch)
        state.set("k", 42)
        assert state.get("k") == 42

    def test_ensure_factory(self, monkeypatch) -> None:
        ss = _patch_session(monkeypatch)
        state.ensure("list", list)
        assert ss["list"] == []
        # 二次 ensure 不覆盖
        ss["list"].append(1)
        state.ensure("list", list)
        assert ss["list"] == [1]


class TestPaperAccount:
    def test_init_from_mock(self, monkeypatch) -> None:
        _patch_session(monkeypatch)
        acct = state.paper_account()
        assert acct["init_capital"] == store.PAPER_ACCOUNT["init_capital"]
        pos = state.paper_positions()
        assert len(pos) == len(store.PAPER_POSITIONS)

    def test_reset(self, monkeypatch) -> None:
        ss = _patch_session(monkeypatch)
        state.paper_account()["cash"] = 0.0
        state.paper_positions().append({"code": "X"})
        state.reset_paper()
        assert ss["paper_account"]["cash"] == store.PAPER_ACCOUNT["cash"]
        assert len(ss["paper_positions"]) == len(store.PAPER_POSITIONS)

    def test_select_fund(self, monkeypatch) -> None:
        _patch_session(monkeypatch)
        state.select_fund("110011")
        assert state.selected_fund() == "110011"


class TestScoreWeights:
    def test_default_weights(self, monkeypatch) -> None:
        _patch_session(monkeypatch)
        w = state.score_weights()
        assert w == store.DEFAULT_WEIGHTS
