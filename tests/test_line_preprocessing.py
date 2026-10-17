# -*- coding: utf-8 -*-
"""行预处理测试：旋转角度估计、包围盒归一化、空文本过滤。

倾斜文本是真实场景（拍照、扫描歪页），但这部分算法原先零覆盖。
"""

import math

import pytest

from dabao_ocr.tbpu.parser_tools.line_preprocessing import (
    _calculateAngle, _estimateRotation, _getBboxes, linePreprocessing,
    angle_threshold_rad)


def _box(cx, cy, w, h, deg=0.0):
    """构造一个中心在 (cx,cy)、宽 w 高 h、逆时针旋转 deg 度的四点包围盒。"""
    a = math.radians(deg)
    cos, sin = math.cos(a), math.sin(a)
    corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    return [[cx + x * cos - y * sin, cy + x * sin + y * cos] for x, y in corners]


def _tb(text, box, score=0.9):
    return {"text": text, "box": box, "score": score}


class TestCalculateAngle:
    def test_horizontal_is_zero(self):
        assert abs(_calculateAngle(_box(100, 100, 80, 20))) < 1e-9

    def test_rotated_10_degrees(self):
        rad = _calculateAngle(_box(100, 100, 80, 20, deg=10))
        assert rad == pytest.approx(math.radians(10), abs=1e-6)

    def test_vertical_box_uses_long_edge(self):
        """竖排文字（高 > 宽）应取长边计算角度，结果为 ±90° 附近。"""
        rad = _calculateAngle(_box(100, 100, 20, 80))
        assert abs(abs(rad) - math.pi / 2) < 1e-6

    def test_normalized_into_half_pi(self):
        for deg in (-80, -10, 0, 10, 80):
            rad = _calculateAngle(_box(100, 100, 80, 20, deg=deg))
            assert -math.pi / 2 - 0.1 <= rad <= math.pi / 2 + 0.1

    def test_wraps_beyond_plus_half_pi(self):
        """长边朝向超过 +90° 时减 π 折回（倒置但未翻转的框）。"""
        rad = _calculateAngle(_box(100, 100, 80, 20, deg=100))
        assert rad == pytest.approx(math.radians(-80), abs=1e-6)

    def test_wraps_below_minus_half_pi(self):
        """长边朝向低于 -90° 时加 π 折回。"""
        rad = _calculateAngle(_box(100, 100, 80, 20, deg=-100))
        assert rad == pytest.approx(math.radians(80), abs=1e-6)


class TestEstimateRotation:
    def test_median_of_angles(self):
        blocks = [_tb("a", _box(100, 100, 80, 20, deg=10)),
                  _tb("b", _box(100, 140, 80, 20, deg=10)),
                  _tb("c", _box(100, 180, 80, 20, deg=12))]
        assert _estimateRotation(blocks) == pytest.approx(math.radians(10), abs=1e-6)

    def test_single_block(self):
        blocks = [_tb("a", _box(100, 100, 80, 20, deg=5))]
        assert _estimateRotation(blocks) == pytest.approx(math.radians(5), abs=1e-6)


class TestGetBboxes:
    def test_below_threshold_no_rotation(self):
        """角度低于阈值时直接取 min/max，不做旋转变换（性能路径）。"""
        box = _box(100, 100, 80, 20, deg=1)
        bboxes = _getBboxes([_tb("a", box)], angle_threshold_rad / 2)
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        assert bboxes[0] == pytest.approx((min(xs), min(ys), max(xs), max(ys)))

    def test_above_threshold_derotates(self):
        """旋转 10° 的盒子去旋转后应恢复成约 80×20 的轴对齐框。"""
        bboxes = _getBboxes([_tb("a", _box(200, 200, 80, 20, deg=10))], math.radians(10))
        x0, y0, x1, y1 = bboxes[0]
        assert (x1 - x0) == pytest.approx(80, abs=1.5)
        assert (y1 - y0) == pytest.approx(20, abs=1.5)

    def test_negative_coords_are_shifted(self):
        """去旋转后出现负坐标时必须整体平移，保证所有 bbox 非负。"""
        bboxes = _getBboxes([_tb("a", _box(5, 5, 80, 20, deg=30))], math.radians(30))
        x0, y0, x1, y1 = bboxes[0]
        assert min(x0, y0) == pytest.approx(0, abs=1e-9)
        assert x1 >= 0 and y1 >= 0

    def test_multiple_blocks(self):
        blocks = [_tb("a", _box(100, 100, 80, 20, deg=10)),
                  _tb("b", _box(100, 140, 80, 20, deg=10))]
        bboxes = _getBboxes(blocks, math.radians(10))
        assert len(bboxes) == 2
        assert all(len(b) == 4 for b in bboxes)


class TestLinePreprocessing:
    def test_filters_empty_text(self):
        blocks = [_tb("", _box(10, 10, 20, 10)), _tb("有字", _box(10, 40, 20, 10))]
        out = linePreprocessing(blocks)
        assert [b["text"] for b in out] == ["有字"]

    def test_empty_input(self):
        assert linePreprocessing([]) == []

    def test_all_empty(self):
        assert linePreprocessing([_tb("", _box(1, 1, 1, 1))]) == []

    def test_sorted_by_top(self):
        blocks = [_tb("下", _box(10, 100, 20, 10)),
                  _tb("上", _box(10, 10, 20, 10)),
                  _tb("中", _box(10, 50, 20, 10))]
        out = linePreprocessing(blocks)
        assert [b["text"] for b in out] == ["上", "中", "下"]

    def test_adds_normalized_bbox(self):
        out = linePreprocessing([_tb("a", _box(10, 10, 20, 10))])
        assert "normalized_bbox" in out[0]
        assert len(out[0]["normalized_bbox"]) == 4

    def test_tilted_page(self):
        """整页倾斜 8°：所有块仍应拿到合理的归一化包围盒并保持上下顺序。"""
        blocks = [_tb("第一行", _box(200, 100, 300, 30, deg=8)),
                  _tb("第二行", _box(200, 140, 300, 30, deg=8)),
                  _tb("第三行", _box(200, 180, 300, 30, deg=8))]
        out = linePreprocessing(blocks)
        assert [b["text"] for b in out] == ["第一行", "第二行", "第三行"]
        tops = [b["normalized_bbox"][1] for b in out]
        assert tops == sorted(tops)
        assert all(t >= 0 for b in out for t in b["normalized_bbox"])
