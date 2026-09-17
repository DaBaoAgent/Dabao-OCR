# -*- coding: utf-8 -*-
"""高层 API 测试：recognize 全路径 / 排版解析 / 忽略区域 / 语言 / 文本拼接。"""

import base64

import pytest

from dabao_ocr import recognize, recognize_base64
from dabao_ocr.engine import CODE_NO_TEXT
from dabao_ocr.ocr import IMAGE_SUFFIXES, convert_ignore_area
from dabao_ocr.result import OcrResult, data_to_text
from tests.conftest import IMG_MULTI, IMG_ZH, IMG_ZH2

ALL_PARSERS = [
    "none", "multi_para", "multi_line", "multi_none",
    "single_para", "single_line", "single_none", "single_code",
]


class TestRecognize:
    def test_basic_chinese(self):
        r = recognize(IMG_ZH)
        assert r.ok
        assert "系统信息" in r.text
        assert "TEST-PC-01" in r.text
        assert "16.0" in r.text
        assert len(r.blocks) > 3
        # 每块都有 end（排版解析后）
        assert all("end" in b for b in r.blocks)

    def test_second_image(self):
        r = recognize(IMG_ZH2)
        assert r.ok or r.empty  # 截图可能为空但不应报错

    def test_bytes_input(self):
        data = open(IMG_ZH, "rb").read()
        r = recognize(data)
        assert r.ok and "系统" in r.text

    def test_base64_input(self):
        b64 = base64.b64encode(open(IMG_ZH, "rb").read()).decode()
        r = recognize_base64(b64)
        assert r.ok and "系统" in r.text

    def test_pathlib_input(self):
        from pathlib import Path

        r = recognize(Path(IMG_ZH))
        assert r.ok

    def test_relative_path(self):
        """相对路径必须正确定位（引擎 cwd 与调用方不同）。"""
        import os

        from tests.conftest import ROOT

        old = os.getcwd()
        try:
            os.chdir(ROOT)
            r = recognize("tests/assets/info_panel.png")
            assert r.ok, f"相对路径识别失败 code={r.code} {r.data}"
        finally:
            os.chdir(old)

    def test_missing_file(self):
        r = recognize("Z:/nope/missing_12345.png")
        assert r.code == 901
        assert not r.ok

    def test_text_matches_blocks(self):
        r = recognize(IMG_ZH)
        assert r.text == data_to_text(r.blocks)


class TestParserOptions:
    @pytest.mark.parametrize("parser", ALL_PARSERS)
    def test_all_parsers_run(self, parser):
        r = recognize(IMG_ZH, parser=parser)
        assert r.ok
        assert len(r.blocks) > 0
        assert all("end" in b for b in r.blocks)

    def test_parser_changes_layout(self):
        r1 = recognize(IMG_MULTI, parser="multi_para")
        r2 = recognize(IMG_MULTI, parser="single_line")
        assert r1.ok and r2.ok
        # 两种方案的换行结构应不同（多栏 vs 单栏）
        assert r1.text != r2.text or [b["end"] for b in r1.blocks] != [
            b["end"] for b in r2.blocks
        ]


class TestIgnoreArea:
    def test_convert_format(self):
        out = convert_ignore_area([[[0, 0], [100, 50]]])
        assert out == [[[0, 0], [], [100, 50], []]]

    def test_ignore_area_filters_blocks(self):
        r0 = recognize(IMG_ZH, parser="none")
        assert r0.ok and len(r0.blocks) > 3
        blk = r0.blocks[0]
        x0, y0 = blk["box"][0]
        x2, y2 = blk["box"][2]
        r1 = recognize(IMG_ZH, parser="none", ignore_area=[[[x0 - 2, y0 - 2], [x2 + 2, y2 + 2]]])
        assert r1.ok
        assert len(r1.blocks) < len(r0.blocks)


class TestEngineOptions:
    def test_angle_on(self):
        r = recognize(IMG_ZH, angle=True)
        assert r.ok

    def test_max_side_len_variants(self):
        for msl in (1024, 2048):
            r = recognize(IMG_ZH, max_side_len=msl)
            assert r.ok

    def test_language_english_on_chinese_img(self):
        # 用英文模型识别中文图：允许识别质量差，但流程必须成功
        r = recognize(IMG_MULTI, language="English")
        assert r.code in (100, 101)

    def test_num_thread(self):
        r = recognize(IMG_MULTI, num_thread=2)
        assert r.ok

    def test_unknown_language_propagates(self):
        with pytest.raises(ValueError):
            recognize(IMG_ZH, language="不存在的语言")


class TestResultModel:
    def test_result_properties(self):
        r = OcrResult(100, [{"text": "a", "end": "。"}, {"text": "b", "end": "\n"}])
        assert r.ok and r.text == "a。b"
        assert r.to_text_dict() == {"code": 100, "data": "a。b"}

    def test_no_text(self):
        r = OcrResult(CODE_NO_TEXT, "no text")
        assert r.empty and not r.ok
        assert r.text == ""

    def test_error(self):
        r = OcrResult(902, "boom")
        assert not r.ok and not r.empty
        assert r.error == "boom"
        assert r.blocks == []
