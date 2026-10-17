# -*- coding: utf-8 -*-
"""single_* 修正版解析器测试。

原版 `single_*` 有两处计算缺陷（继承自 Umi-OCR）：
1. 行高公式把左边界 l2 混进高度，h 可能变成大负数 → "间隙过大"恒成立 → 误插空格
2. 行包围盒合并时用刚更新的 b1 去算 b2/b3 → 右/下边界偏小

为保持与原版逐块一致，原 8 种保持不变；修正版是独立的新方案。
"""

import pytest

from dabao_ocr.tbpu import PARSER_KEYS, Parser
from dabao_ocr.tbpu.parser_single_line import SingleLine, SingleLineFixed
from dabao_ocr.tbpu.parser_single_para import SinglePara, SingleParaFixed


def _blk(text, x0, y0, x1, y1):
    return {
        "text": text,
        "score": 0.9,
        "box": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
    }


def _blocks(*items):
    return [_blk(*it) for it in items]


class TestLineHeightBug:
    """同一行、靠右、间隙很小的两块：旧公式会误判为"间隙过大"。"""

    def _row(self):
        # 两块都在页面右侧（x≈500），间隙 5px，行高 30px
        return _blocks(("中文", 500, 100, 600, 130),
                       ("内容", 605, 100, 700, 130))

    def test_old_inserts_space(self):
        out = SingleLine().run(self._row())
        assert out[0]["end"] == " ", "旧公式应误插空格（记录当前行为）"

    def test_fixed_keeps_cjk_joined(self):
        out = SingleLineFixed().run(self._row())
        assert out[0]["end"] == "", "修正版应按 CJK 规则不加分隔符"

    def test_fixed_still_spaces_real_gap(self):
        """真正的大间隙（> 1.5 倍行高）仍应插入空格。"""
        out = SingleLineFixed().run(
            _blocks(("中文", 100, 100, 200, 130), ("内容", 400, 100, 500, 130))
        )
        assert out[0]["end"] == " "

    def test_fixed_english_gets_space(self):
        """英文相邻块本来就该有空格，修正后仍应如此。"""
        out = SingleLineFixed().run(
            _blocks(("hello", 100, 100, 200, 130), ("world", 205, 100, 300, 130))
        )
        assert out[0]["end"] == " "


def _low_left_row():
    """页面下部、左对齐的窄行：y≈1000 远大于 x（0..400）。

    旧公式 b2 = max(b1=1000, 400) = 1000，右边界被算成 y 坐标。
    """
    return _blocks(("甲", 0, 1000, 200, 1030),
                   ("乙", 205, 1000, 400, 1030))


class TestParaBboxBug:
    @staticmethod
    def _capture(parser):
        """拦下 ParagraphParse，直接读合并后的行包围盒。"""
        captured = []
        parser.pp.run = lambda tbs: captured.extend(tbs)
        parser.run(_low_left_row())
        return captured[0]["normalized_bbox"]

    def test_old_bbox_wrong(self):
        assert self._capture(SinglePara()) == (0, 1000, 1000, 1030)

    def test_fixed_bbox_right(self):
        assert self._capture(SingleParaFixed()) == (0, 1000, 400, 1030)


class TestRegistry:
    def test_fixed_variants_registered(self):
        for key in ("single_line_fixed", "single_none_fixed",
                    "single_code_fixed", "single_para_fixed"):
            assert key in Parser
            assert key in PARSER_KEYS

    def test_original_eight_untouched(self):
        for key in ("none", "multi_para", "multi_line", "multi_none",
                    "single_para", "single_line", "single_none", "single_code"):
            assert key in Parser

    def test_flags_only_on_fixed(self):
        assert SingleLine.FIX_LINE_HEIGHT is False
        assert SinglePara.FIX_LINE_BBOX is False
        assert SingleLineFixed.FIX_LINE_HEIGHT is True
        assert SingleParaFixed.FIX_LINE_BBOX is True
        assert SingleParaFixed.FIX_LINE_HEIGHT is True

    def test_options_table_covers_all(self):
        from dabao_ocr.options import PARSER_KEYS_ORDERED

        assert set(PARSER_KEYS_ORDERED) == set(PARSER_KEYS)


class TestRealImage:
    @pytest.mark.parametrize("parser", [
        "single_line_fixed", "single_none_fixed",
        "single_code_fixed", "single_para_fixed",
    ])
    def test_fixed_parsers_run(self, parser):
        from tests.conftest import IMG_ZH

        from dabao_ocr import recognize

        r = recognize(IMG_ZH, parser=parser)
        assert r.ok and r.blocks
        assert all("end" in b for b in r.blocks)
        assert all("normalized_bbox" not in b for b in r.blocks)  # 临时字段必须清掉
