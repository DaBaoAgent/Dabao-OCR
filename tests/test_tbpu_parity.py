# -*- coding: utf-8 -*-
"""★ 排版解析一致性测试：移植版 tbpu vs 原版 Umi-OCR tbpu 源码。

直接从原版安装目录加载其 tbpu 包（注入 umi_log shim），
对同一输入逐块对比全部 8 种解析方案的输出。
"""

import copy
import importlib.util
import logging
import sys
import types

import pytest

from dabao_ocr.engine import get_engine
from dabao_ocr.tbpu import getParser
from tests.conftest import IMG_ZH, ORIGIN_UMI_TBPU

PARSERS = [
    "none", "multi_para", "multi_line", "multi_none",
    "single_para", "single_line", "single_none", "single_code",
]


def _ensure_umi_log_shim():
    """原版 line_preprocessing 依赖 umi_log，注入 logger shim。"""
    if "umi_log" not in sys.modules:
        m = types.ModuleType("umi_log")
        m.logger = logging.getLogger("umi_log_shim")
        sys.modules["umi_log"] = m


def load_origin_tbpu():
    if not ORIGIN_UMI_TBPU.is_dir():
        pytest.skip(f"原版 Umi-OCR tbpu 不存在：{ORIGIN_UMI_TBPU}")
    _ensure_umi_log_shim()
    name = "origin_umi_tbpu"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name,
        ORIGIN_UMI_TBPU / "__init__.py",
        submodule_search_locations=[str(ORIGIN_UMI_TBPU)],
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def real_blocks():
    """真实图片识别出的文本块（最贴近生产的输入）。"""
    eng = get_engine()
    res = eng.run_path(IMG_ZH)
    assert res["code"] == 100
    return res["data"]


def _box(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def scene_two_cols():
    blocks = []
    for i, t in enumerate(["左栏第一行内容", "左栏第二行内容", "左栏第三行内容"]):
        blocks.append({"box": _box(50, 100 + i * 40, 300, 130 + i * 40), "score": 0.95, "text": t})
    for i, t in enumerate(["右栏第一行内容", "右栏第二行内容", "右栏第三行内容"]):
        blocks.append({"box": _box(450, 100 + i * 40, 700, 130 + i * 40), "score": 0.95, "text": t})
    return blocks


def scene_paragraph():
    return [
        {"box": _box(60, 90, 720, 120), "score": 0.9, "text": "第一段的第一行文字在这里"},
        {"box": _box(60, 128, 720, 158), "score": 0.9, "text": "第一段的第二行文字在这里"},
        {"box": _box(60, 200, 500, 230), "score": 0.9, "text": "这是独立的一行标题"},
        {"box": _box(60, 270, 720, 300), "score": 0.9, "text": "第二段开始的一些文字内容"},
        {"box": _box(60, 308, 720, 338), "score": 0.9, "text": "第二段的第二行内容文字"},
    ]


def scene_code():
    return [
        {"box": _box(60, 80, 400, 104), "score": 0.9, "text": "def hello():"},
        {"box": _box(100, 112, 420, 136), "score": 0.9, "text": "print('hi')"},
        {"box": _box(100, 144, 460, 168), "score": 0.9, "text": "return 42"},
        {"box": _box(60, 176, 380, 200), "score": 0.9, "text": "hello()"},
    ]


def scene_mixed_spacing():
    return [
        {"box": _box(60, 80, 200, 110), "score": 0.9, "text": "Hello"},
        {"box": _box(260, 80, 420, 110), "score": 0.9, "text": "World"},
        {"box": _box(430, 80, 520, 110), "score": 0.9, "text": "中"},
        {"box": _box(60, 120, 520, 150), "score": 0.9, "text": "混排 ending-"},
    ]


SCENES = {
    "two_cols": scene_two_cols,
    "paragraph": scene_paragraph,
    "code": scene_code,
    "mixed_spacing": scene_mixed_spacing,
}


@pytest.mark.parametrize("parser", PARSERS)
def test_parity_real_image(parser, real_blocks):
    """真实图片 blocks：移植版与原版输出必须逐块一致。"""
    origin = load_origin_tbpu()
    ours = getParser(parser)
    theirs = origin.getParser(parser)
    r_ours = ours.run(copy.deepcopy(real_blocks))
    r_theirs = theirs.run(copy.deepcopy(real_blocks))
    assert r_ours == r_theirs, f"parser={parser} 真实图输出不一致"


@pytest.mark.parametrize("scene", sorted(SCENES))
@pytest.mark.parametrize("parser", PARSERS)
def test_parity_synthetic(scene, parser):
    """手工构造场景：8 种方案 × 4 个场景全对比。"""
    origin = load_origin_tbpu()
    blocks = SCENES[scene]()
    ours = getParser(parser)
    theirs = origin.getParser(parser)
    r_ours = ours.run(copy.deepcopy(blocks))
    r_theirs = theirs.run(copy.deepcopy(blocks))
    assert r_ours == r_theirs, f"scene={scene} parser={parser} 输出不一致"


def test_unknown_parser_fallback():
    """未知 parser 名称回退为 'none'（与原版一致）。"""
    origin = load_origin_tbpu()
    blocks = scene_two_cols()
    r_ours = getParser("nonsense_parser").run(copy.deepcopy(blocks))
    r_theirs = origin.getParser("nonsense_parser").run(copy.deepcopy(blocks))
    assert r_ours == r_theirs
