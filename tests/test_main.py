"""API 装配与异常映射单测(详细设计§8.2 / §6.2)。"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from api.main import EnvelopeResponse, _format_validation_errors, create_app
from infra.logging import set_trace_id
from schemas.errors import NotFoundError, ParamError


def test_envelope_response_injects_trace_id() -> None:
    """EnvelopeResponse.render 从 contextvar 注入 trace_id(§6.2)。"""
    set_trace_id("tid-xyz-123")
    resp = EnvelopeResponse(status_code=200, content={"code": 0, "message": "ok"})
    body = json.loads(resp.body)
    assert body["trace_id"] == "tid-xyz-123"


def test_format_validation_errors_human_readable() -> None:
    errs = [{"loc": ["body", "amount"], "msg": "field required"}, {"loc": [], "msg": "bad"}]
    text = _format_validation_errors(errs)
    assert "amount" in text and "bad" in text


def test_param_error_maps_envelope() -> None:
    """§8.2：ParamError -> 40001 信封。"""
    app = create_app()

    @app.get("/_raise_param")
    def _raise() -> None:
        raise ParamError("bad input")

    with TestClient(app) as c:
        resp = c.get("/_raise_param")
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == 40001
    assert body["data"] is None
    assert body["trace_id"]  # 必带


def test_not_found_error_maps_envelope() -> None:
    """§8.2：NotFoundError -> 40002 信封(http 404)。"""
    app = create_app()

    @app.get("/_raise_nf")
    def _raise() -> None:
        raise NotFoundError("基金不存在")

    with TestClient(app) as c:
        resp = c.get("/_raise_nf")
    assert resp.status_code == 404
    assert resp.json()["code"] == 40002
