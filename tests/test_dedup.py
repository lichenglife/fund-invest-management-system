"""相似去重单测(P1-06c，§3.4.7 / DC-004，纯逻辑无 DB)。

覆盖：Jaccard 重叠计算、阈值 0.70、相似/不相似判定、空持仓。
"""

from __future__ import annotations

from domain.screen import SIMILARITY_OVERLAP, similarity_dedup


def _holdings(stocks: list[str]) -> list[dict[str, object]]:
    return [{"stock_code": s, "weight": 0.1} for s in stocks]


class TestSimilarityDedup:
    """§3.4.7 前十大重叠 Jaccard。"""

    def test_high_overlap_similar(self) -> None:
        """8/10 共享(并集12) -> Jaccard 0.67；9/10 共享(并集11)->0.82 达标。"""
        common = list("ABCDEFGHI")
        hm = {
            "F1": _holdings(common + ["X"]),  # 10 只
            "F2": _holdings(common + ["Y"]),  # 9 共享 + 1 独有
        }
        r = similarity_dedup(hm)
        assert len(r.pairs) == 1
        assert r.pairs[0].overlap == 9 / 11  # 9 交集 / 11 并集
        assert r.pairs[0].is_similar is True  # 0.818 >= 0.70
        assert r.similar_count == 1

    def test_low_overlap_not_similar(self) -> None:
        """仅 2/10 共享 -> 不相似。"""
        hm = {
            "F1": _holdings(["A", "B", "C", "D", "E", "F", "G", "H", "X", "Y"]),
            "F2": _holdings(["A", "B", "Z", "W", "V", "U", "T", "S", "R", "Q"]),
        }
        r = similarity_dedup(hm)
        assert r.pairs[0].overlap == 2 / 18  # 2 交集 / 18 并集
        assert r.pairs[0].is_similar is False
        assert r.similar_count == 0

    def test_identical_holdings(self) -> None:
        """完全相同 -> Jaccard 1.0。"""
        stocks = list("ABCDEFGHIJ")
        hm = {"F1": _holdings(stocks), "F2": _holdings(stocks)}
        r = similarity_dedup(hm)
        assert r.pairs[0].overlap == 1.0
        assert r.pairs[0].is_similar is True

    def test_no_overlap(self) -> None:
        """完全不同 -> 0.0。"""
        hm = {"F1": _holdings(["A"]), "F2": _holdings(["B"])}
        r = similarity_dedup(hm)
        assert r.pairs[0].overlap == 0.0
        assert r.pairs[0].is_similar is False

    def test_empty_holdings(self) -> None:
        """空持仓 -> overlap 0。"""
        hm = {"F1": [], "F2": []}
        r = similarity_dedup(hm)
        assert r.pairs[0].overlap == 0.0
        assert r.pairs[0].is_similar is False

    def test_single_fund_no_pairs(self) -> None:
        """单基金 -> 无对。"""
        r = similarity_dedup({"F1": _holdings(["A"])})
        assert r.pairs == []
        assert r.similar_count == 0

    def test_three_funds_pairs(self) -> None:
        """三基金 -> 3 对(C(3,2))。"""
        hm = {
            "F1": _holdings(["A", "B", "C"]),
            "F2": _holdings(["A", "B", "D"]),
            "F3": _holdings(["X", "Y", "Z"]),
        }
        r = similarity_dedup(hm)
        assert len(r.pairs) == 3  # F1-F2, F1-F3, F2-F3

    def test_threshold_constant(self) -> None:
        assert SIMILARITY_OVERLAP == 0.70
