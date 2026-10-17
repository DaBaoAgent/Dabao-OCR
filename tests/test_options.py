# -*- coding: utf-8 -*-
"""选项表测试：结构、默认值补全、参数校验与错误消息。"""

import pytest

from dabao_ocr.options import (PARSER_KEYS_ORDERED, PARSER_OPTIONS,
                               fill_defaults, get_options, validate_options)

EXPECTED_KEYS = {
    "ocr.language", "ocr.angle", "ocr.maxSideLen",
    "tbpu.parser", "tbpu.ignoreArea", "data.format",
}


class TestGetOptions:
    def test_keys(self):
        assert set(get_options()) == EXPECTED_KEYS

    def test_each_entry_shape(self):
        for key, meta in get_options().items():
            assert "title" in meta, key
            assert meta["type"] in {"enum", "boolean", "var"}, key
            assert "default" in meta, key

    def test_parser_options_match_keys(self):
        assert [k for k, _ in PARSER_OPTIONS] == list(PARSER_KEYS_ORDERED)
        assert "multi_para" in PARSER_KEYS_ORDERED

    def test_language_options_are_pairs(self):
        opts = get_options()["ocr.language"]["optionsList"]
        assert opts and all(len(x) == 2 for x in opts)


class TestFillDefaults:
    def test_fills_all_keys(self):
        assert set(fill_defaults({})) == EXPECTED_KEYS

    def test_keeps_user_values(self):
        opt = fill_defaults({"ocr.language": "English", "tbpu.parser": "none"})
        assert opt["ocr.language"] == "English"
        assert opt["tbpu.parser"] == "none"

    def test_none_input(self):
        assert set(fill_defaults(None)) == EXPECTED_KEYS

    def test_ignore_area_list_not_shared(self):
        """默认值里的列表必须是新对象，否则调用方 append 会污染后续调用。"""
        first = fill_defaults({})
        first["tbpu.ignoreArea"].append([[0, 0], [1, 1]])
        assert fill_defaults({})["tbpu.ignoreArea"] == []

    def test_matches_option_table_defaults(self):
        table = get_options()
        filled = fill_defaults({})
        assert {k: filled[k] for k in table} == {k: m["default"] for k, m in table.items()}


class TestValidate:
    def test_valid_passes(self):
        validate_options(fill_defaults({}))

    def test_ignore_area_not_list(self):
        with pytest.raises(ValueError, match="必须为数组"):
            validate_options({"tbpu.ignoreArea": "bad"})

    def test_ignore_area_malformed(self):
        with pytest.raises(ValueError, match="格式必须是"):
            validate_options({"tbpu.ignoreArea": [[[0, 0], [1]]]})

    def test_ignore_area_non_numeric(self):
        with pytest.raises(ValueError, match="格式必须是"):
            validate_options({"tbpu.ignoreArea": [[["a", 0], [1, 1]]]})

    def test_ignore_area_valid(self):
        validate_options({"tbpu.ignoreArea": [[[0, 0], [100, 50]]]})

    def test_ignore_area_empty_ok(self):
        validate_options({"tbpu.ignoreArea": []})

    def test_max_side_not_int(self):
        with pytest.raises(ValueError, match="必须为整数"):
            validate_options({"ocr.maxSideLen": "abc"})

    def test_max_side_none(self):
        with pytest.raises(ValueError, match="必须为整数"):
            validate_options({"ocr.maxSideLen": None})

    def test_unknown_language(self):
        with pytest.raises(ValueError, match="未知语言"):
            validate_options({"ocr.language": "火星文"})

    def test_bad_engine_dir_skips_language_check(self, tmp_path):
        """读不到语言表时应跳过校验，而不是把请求判失败。"""
        validate_options({"ocr.language": "任意"}, engine_dir=tmp_path)
