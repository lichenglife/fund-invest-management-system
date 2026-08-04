"""ORM 模型与迁移的数据库约束单测(详设§2.20.2 / §2.20.3 建表约定)。

用 compose PostgreSQL 实测 FK/CHECK/CASCADE/JSONB(§2.20.3 外键约束、CHECK 约束)。
隔离：使用独立 test schema，测试后 drop；不污染 dev 库。
标记 ``db`` group，CI 无 PG 时跳过(``pytest -m "not db"``)。
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from infra.db.models import Fund

pytestmark = pytest.mark.db


def test_all_ten_tables_created(engine: Engine) -> None:
    """§2.20.2：10 核心表全部建成。"""
    insp = inspect(engine)
    tables = {t for t in insp.get_table_names() if not t.startswith("alembic")}
    expected = {
        "funds",
        "navs",
        "holdings",
        "scores",
        "research_metrics",
        "paper_accounts",
        "paper_positions",
        "paper_trades",
        "portfolios",
        "portfolio_weights",
    }
    assert expected.issubset(tables), f"missing: {expected - tables}"


def test_fund_nav_cascade_delete(engine: Engine) -> None:
    """§2.20.2 navs FK ON DELETE CASCADE：删基金级联删净值。"""
    with Session(engine) as s:
        s.add(_fund("000001.OF"))
        s.commit()
        s.execute(
            text(
                "INSERT INTO navs(code,trade_date,nav,adj_nav,source,as_of) "
                "VALUES(:c,:d,:n,:a,:s,:o)"
            ),
            {
                "c": "000001.OF",
                "d": date(2025, 7, 28),
                "n": Decimal("1.0120"),
                "a": Decimal("1.0120"),
                "s": "AkShare",
                "o": date(2025, 7, 28),
            },
        )
        s.commit()
        # 删基金 -> navs 应级联删除
        s.execute(text("DELETE FROM funds WHERE code='000001.OF'"))
        s.commit()
        cnt = s.execute(text("SELECT count(*) FROM navs WHERE code='000001.OF'")).scalar()
    assert cnt == 0


def test_paper_trades_side_check(engine: Engine) -> None:
    """§2.20.2 paper_trades.side CHECK('buy','sell')：非法值被拒。

    用 4 字符非法值 'xxxx'(匹配 VARCHAR(4) 长度)，确保触发 CHECK 而非长度截断 DataError。
    """
    with Session(engine) as s:
        s.add(_fund("000002.OF"))
        s.execute(text("INSERT INTO paper_accounts(account_id,cash) VALUES('acct1',100000)"))
        s.commit()
        # 非法 side -> IntegrityError(CHECK 拒绝)
        with pytest.raises(IntegrityError):
            s.execute(
                text(
                    "INSERT INTO paper_trades(account_id,code,side,shares,nav,trade_date) "
                    "VALUES('acct1','000002.OF','xxxx',100,1.0,'2025-07-28')"
                )
            )
            s.commit()


def test_portfolios_source_check(engine: Engine) -> None:
    """§2.20.2 portfolios.source CHECK('template','manual','import')。"""
    with Session(engine) as s:
        s.execute(text("INSERT INTO paper_accounts(account_id,cash) VALUES('acct2',100000)"))
        s.commit()
        with pytest.raises(IntegrityError):
            s.execute(
                text(
                    "INSERT INTO portfolios(portfolio_id,account_id,source) "
                    "VALUES('pf1','acct2','bogus')"
                )
            )
            s.commit()


def test_scores_jsonb_roundtrip(engine: Engine) -> None:
    """§2.20.2 scores.weights/factors 为 JSONB，可存取字典。"""
    weights = {"ret": 20, "risk": 25, "perf": 20, "scale": 15, "manager": 10}  # 新口径(§4 红线)
    factors = {"ret": 88.0, "risk": 75.0, "perf": 80.0, "scale": 65.0, "manager": 70.0}
    with Session(engine) as s:
        s.add(_fund("000003.OF"))
        s.commit()
        s.execute(
            text(
                "INSERT INTO scores(code,weights,composite,factors,as_of) "
                "VALUES(:c,CAST(:w AS JSONB),:comp,CAST(:f AS JSONB),:o)"
            ),
            {
                "c": "000003.OF",
                "w": json.dumps(weights),
                "comp": Decimal("82.3"),
                "f": json.dumps(factors),
                "o": date(2025, 7, 28),
            },
        )
        s.commit()
        row = s.execute(text("SELECT weights, factors FROM scores WHERE code='000003.OF'")).one()
    assert row[0]["ret"] == 20  # 五因子新口径
    assert row[1]["manager"] == 70.0


def test_composite_pk_holdings(engine: Engine) -> None:
    """§2.20.2 holdings 复合 PK(code, report_date, stock_code)。"""
    with Session(engine) as s:
        s.add(_fund("000004.OF"))
        s.commit()  # 先提交基金，满足 holdings 的 FK
        s.execute(
            text(
                "INSERT INTO holdings(code,report_date,stock_code,weight,source,as_of) "
                "VALUES('000004.OF','2025-06-30','600519.SH',0.08,'AkShare','2025-07-01')"
            )
        )
        s.commit()
        # 同 PK 重复 -> IntegrityError
        with pytest.raises((IntegrityError, DataError)):
            s.execute(
                text(
                    "INSERT INTO holdings(code,report_date,stock_code,weight,source,as_of) "
                    "VALUES('000004.OF','2025-06-30','600519.SH',0.09,'AkShare','2025-07-01')"
                )
            )
            s.commit()


# --- helpers ---


def _fund(code: str) -> Fund:
    """构造测试 Fund 实例。"""
    return Fund(
        code=code,
        name=f"测试基金{code[:6]}",
        type_="mixed",
        source="AkShare",
        as_of=date(2025, 7, 28),
    )
