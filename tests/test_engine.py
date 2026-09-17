# -*- coding: utf-8 -*-
"""引擎层测试：启动、识别、错误路径、缓存复用。"""

import os
import time

import pytest

from dabao_ocr.engine import (OcrEngine, OcrEngineError, clear_engines,
                              default_engine_dir, get_engine,
                              normalize_options)
from tests.conftest import IMG_ZH


class TestEngineLifecycle:
    def test_engine_dir_found(self):
        d = default_engine_dir()
        assert (d / "RapidOCR-json.exe").exists()
        assert (d / "models" / "configs.txt").exists()

    def test_start_stop(self):
        eng = OcrEngine()
        assert not eng.alive
        eng.start()
        assert eng.alive
        eng.start()  # 幂等
        assert eng.alive
        eng.stop()
        assert not eng.alive
        eng.stop()  # 幂等

    def test_context_manager(self):
        with OcrEngine() as eng:
            assert eng.alive
        assert not eng.alive

    def test_run_path(self):
        eng = get_engine()
        res = eng.run_path(IMG_ZH)
        assert res["code"] == 100
        assert isinstance(res["data"], list) and len(res["data"]) > 3
        blk = res["data"][0]
        assert set(blk.keys()) >= {"box", "score", "text"}
        assert len(blk["box"]) == 4

    def test_run_bytes(self):
        eng = get_engine()
        data = open(IMG_ZH, "rb").read()
        res = eng.run_bytes(data)
        assert res["code"] == 100
        assert any("系统" in b["text"] for b in res["data"])

    def test_run_missing_file(self):
        eng = get_engine()
        res = eng.run_path("Z:/definitely/not/exist_12345.png")
        assert res["code"] != 100
        assert res["code"] not in (100, 101)

    def test_engine_restart_after_kill(self):
        eng = OcrEngine()
        eng.start()
        eng._proc.kill()  # 模拟崩溃
        eng._proc.wait(timeout=5)
        time.sleep(0.1)
        assert not eng.alive
        res = eng.run_path(IMG_ZH)  # 应自动重启并成功
        assert res["code"] == 100
        assert eng.alive
        eng.stop()


class TestNormalizeOptions:
    def test_defaults(self):
        o = normalize_options()
        assert o["keys"] == "dict_chinese.txt"
        assert o["rec"] == "rec_ch_PP-OCRv4_infer.onnx"
        assert o["angle"] is False
        assert o["maxSideLen"] == 1024
        assert o["numThread"] >= 1

    def test_language_switch(self):
        o = normalize_options({"language": "English"})
        assert o["keys"] == "dict_en.txt"
        assert "en" in o["rec"]

    def test_unknown_language_raises(self):
        with pytest.raises(ValueError):
            normalize_options({"language": "火星文"})

    def test_snake_case_aliases(self):
        o = normalize_options({"max_side_len": 2048, "num_thread": 2})
        assert o["maxSideLen"] == 2048
        assert o["numThread"] == 2


class TestEngineCache:
    def test_same_options_reuse(self):
        a = get_engine({"language": "简体中文"})
        b = get_engine({"language": "简体中文", "maxSideLen": 1024})
        assert a is b

    def test_different_options_different_engine(self):
        a = get_engine({"language": "简体中文", "maxSideLen": 1024})
        b = get_engine({"language": "English", "maxSideLen": 1024})
        assert a is not b
        a.start()
        b.start()
        assert a.alive and b.alive

    def test_lru_eviction(self):
        clear_engines()
        e1 = get_engine({"language": "简体中文", "maxSideLen": 1024})
        e1.start()
        e2 = get_engine({"language": "English", "maxSideLen": 1024})
        e2.start()
        e3 = get_engine({"language": "简体中文", "maxSideLen": 2048})
        e3.start()
        # 默认上限 2：最早的 e1 应被淘汰
        assert not e1.alive
        assert e2.alive and e3.alive
        clear_engines()
        assert not e2.alive and not e3.alive
