# -*- coding: utf-8 -*-
"""语言/模型库测试：configs.txt 解析、mtime 缓存、错误路径。"""

import pytest

from dabao_ocr.langs import (DEFAULT_LANGUAGE, LanguageError,
                             get_language_dict, get_language_list,
                             resolve_language)

BLOCK_ZH = "简体中文\nch_PP-OCRv3_det_infer.onnx\nch_cls.onnx\nrec_ch.onnx\ndict_chinese.txt\n\n"
BLOCK_EN = "English\nch_PP-OCRv3_det_infer.onnx\nch_cls.onnx\nrec_en.onnx\ndict_en.txt\n"


def _make_engine_dir(root, content):
    models = root / "models"
    models.mkdir(parents=True, exist_ok=True)
    cfg = models / "configs.txt"
    cfg.write_text(content, encoding="utf-8")
    return root


class TestParse:
    def test_real_config(self):
        d = get_language_dict()
        assert DEFAULT_LANGUAGE in d
        assert d["简体中文"]["keys"] == "dict_chinese.txt"
        assert set(d["简体中文"]) == {"det", "cls", "rec", "keys"}

    def test_list_keeps_order(self):
        langs = get_language_list()
        assert langs[0] == DEFAULT_LANGUAGE

    def test_temp_config(self, tmp_path):
        root = _make_engine_dir(tmp_path, BLOCK_ZH + "\n" + BLOCK_EN)
        d = get_language_dict(root)
        assert list(d) == ["简体中文", "English"]
        assert d["English"]["rec"] == "rec_en.onnx"

    def test_missing_config_raises(self, tmp_path):
        with pytest.raises(LanguageError):
            get_language_dict(tmp_path)

    def test_malformed_block_ignored(self, tmp_path):
        root = _make_engine_dir(tmp_path, "只有一行\n\n" + BLOCK_EN)
        assert list(get_language_dict(root)) == ["English"]


class TestCache:
    def test_returns_copy(self, tmp_path):
        """返回值必须是副本，调用方改写不能污染缓存。"""
        root = _make_engine_dir(tmp_path, BLOCK_EN)
        first = get_language_dict(root)
        first["English"]["rec"] = "被改掉了"
        assert get_language_dict(root)["English"]["rec"] == "rec_en.onnx"

    def test_mtime_invalidates(self, tmp_path):
        """改了 configs.txt 必须读到新内容，不能吃旧缓存。"""
        root = _make_engine_dir(tmp_path, BLOCK_EN)
        assert list(get_language_dict(root)) == ["English"]

        cfg = root / "models" / "configs.txt"
        cfg.write_text(BLOCK_ZH + "\n" + BLOCK_EN, encoding="utf-8")
        assert list(get_language_dict(root)) == ["简体中文", "English"]

    def test_same_content_stable(self, tmp_path):
        root = _make_engine_dir(tmp_path, BLOCK_EN)
        assert get_language_dict(root) == get_language_dict(root)


class TestResolve:
    def test_known(self):
        m = resolve_language("English")
        assert m["keys"] == "dict_en.txt"

    def test_unknown_lists_available(self):
        with pytest.raises(LanguageError) as ei:
            resolve_language("火星文")
        msg = str(ei.value)
        assert "火星文" in msg and "English" in msg

    def test_empty_config_reports_path(self, tmp_path):
        """空配置时应报 LanguageError 并带上路径，而不是 Path(None) 的 TypeError。"""
        root = _make_engine_dir(tmp_path, "\n\n")
        with pytest.raises(LanguageError) as ei:
            resolve_language("简体中文", root)
        assert "configs.txt" in str(ei.value)
