"""components 风格箱定位纯逻辑单测(原型③⑥ 九宫格高亮 · BR-2.3/DC-002 F)。

覆盖回归：此前 ``render`` 用 ``current.split()`` 解析定位，store.FUNDS 的 style 为
无空格 token(如「中盘成长」)被当成单元素 -> cur_col 恒空 -> 当前格永不高亮。
改为子串匹配后两种写法均应命中正确格子，且仅命中一格。
"""

from __future__ import annotations

from app.components.style_box import _matches_current


class TestMatchesCurrent:
    def test_unspaced_token(self) -> None:
        # store.FUNDS 取值无空格(110011「中盘成长」/000961「大盘价值」)
        assert _matches_current("中盘", "成长", "中盘成长")
        assert _matches_current("大盘", "价值", "大盘价值")

    def test_spaced_token(self) -> None:
        # 页面默认传参可能带空格(页02「中盘 成长」)
        assert _matches_current("中盘", "成长", "中盘 成长")

    def test_only_one_cell_matches(self) -> None:
        # 同一 current 下仅命中目标格，其余行列组合均为 False
        current = "中盘成长"
        for row in ("大盘", "中盘", "小盘"):
            for col in ("价值", "平衡", "成长"):
                expected = row == "中盘" and col == "成长"
                assert _matches_current(row, col, current) is expected

    def test_no_style_dash(self) -> None:
        # 债基/货基 style='-'，不应命中任何格
        for row in ("大盘", "中盘", "小盘"):
            for col in ("价值", "平衡", "成长"):
                assert not _matches_current(row, col, "-")

    def test_empty_current(self) -> None:
        # 空定位不命中任何格(防极端输入)
        assert not _matches_current("中盘", "成长", "")
