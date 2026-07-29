"""Live 烟测(真实 AkShare，P1-01a 补测)。

真实调 AkShare 拉一只基金净值，验证：
- 网络可达 + 接口可用
- 返回条数 > 0
- 字段非空(nav/acc_nav)
- 日期连续性(无大缺口)

> 标 ``live``：CI 无网络时跳过(``pytest -m "not live"``)。本地手动跑验证数据源健康。
> 非 DoD 门禁；用于开发期数据源健壮性核查(就绪评估 O1 补充)。
"""

from __future__ import annotations

from datetime import date

import pytest

from infra.external.akshare_source import AkShareDataSource

pytestmark = pytest.mark.live

#: 烟测样本基金(华夏成长混合，长期存在)。
SAMPLE_CODE = "000001"


class TestAkShareLive:
    """真实 AkShare 接口烟测(需网络)。"""

    def test_fund_list_nonempty(self) -> None:
        """名单接口可达且返回基金。"""
        src = AkShareDataSource()
        records = src.fetch_fund_list()
        assert len(records) > 0, "AkShare 名单为空(网络/接口异常?)"
        # 至少含混合型
        types = {r["type_"] for r in records[:200]}
        assert "mixed" in types or "stock" in types

    def test_fetch_nav_real(self) -> None:
        """净值接口：返回条数 > 0，nav 非空，日期格式正确。"""
        src = AkShareDataSource()
        # 近 30 天
        end = date.today().strftime("%Y%m%d")
        start = date.today().replace(year=date.today().year - 1).strftime("%Y%m%d")
        records = src.fetch_nav(SAMPLE_CODE, start=start, end=end)
        assert len(records) > 0, f"基金 {SAMPLE_CODE} 近一年无净值数据"
        # 字段非空
        r = records[-1]
        assert r["nav"] is not None and r["nav"] > 0
        assert r["trade_date"]  # 日期非空
        # acc_nav 可能为 None(D6 累计净值接口失败时)，但 nav 必须有
        # 日期格式 YYYY-MM-DD
        assert len(r["trade_date"]) == 10

    def test_fetch_nav_date_continuity(self) -> None:
        """净值日期无大缺口(>30 天视为异常，§2.16 缺失天数告警)。"""
        src = AkShareDataSource()
        end = date.today().strftime("%Y%m%d")
        start = date.today().replace(month=1, day=1).strftime("%Y%m%d")
        records = src.fetch_nav(SAMPLE_CODE, start=start, end=end)
        if len(records) >= 2:
            dates = sorted(date.fromisoformat(r["trade_date"]) for r in records)
            max_gap = 0
            for i in range(1, len(dates)):
                gap = (dates[i] - dates[i - 1]).days
                max_gap = max(max_gap, gap)
            # 周末/节假日 gap 可达 3-7 天；>30 天才告警(§2.16 缺失天数)
            assert max_gap <= 30, f"净值缺口过大: {max_gap} 天(可能数据源异常)"
