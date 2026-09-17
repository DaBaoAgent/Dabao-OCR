# -*- coding: utf-8 -*-
"""★ 金标准一致性测试：Dabao-OCR vs 本机运行中的原版 Umi-OCR HTTP 服务。

原版服务（127.0.0.1:1224）不在线时自动跳过。
"""

import base64
import json
import urllib.request

import pytest

from dabao_ocr import recognize
from dabao_ocr.options import get_options
from tests.conftest import IMG_MULTI, IMG_ZH, IMG_ZH2, ORIGIN_UMI_API


def _api_alive() -> bool:
    try:
        with urllib.request.urlopen(ORIGIN_UMI_API + "/api/ocr/get_options", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _api_alive(), reason="原版 Umi-OCR 服务(:1224)不在线，跳过金标准对比"
)


def _origin_ocr(img_path, options) -> dict:
    b64 = base64.b64encode(open(img_path, "rb").read()).decode()
    payload = {"base64": b64, "options": options}
    req = urllib.request.Request(
        ORIGIN_UMI_API + "/api/ocr",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


@pytest.mark.parametrize("img", [IMG_ZH, IMG_MULTI, IMG_ZH2])
@pytest.mark.parametrize("parser", ["multi_para", "single_line", "multi_none"])
def test_text_output_identical(img, parser):
    """text 格式输出：与原版逐字符一致。"""
    opts = {
        "ocr.language": "简体中文",
        "ocr.angle": False,
        "ocr.maxSideLen": 1024,
        "tbpu.parser": parser,
        "data.format": "text",
    }
    origin = _origin_ocr(img, opts)
    ours = recognize(img, parser=parser)
    assert origin["code"] == (100 if ours.ok else origin["code"])
    if origin["code"] == 100:
        assert ours.text == origin["data"], "text 输出应与原版逐字符一致"


def test_dict_output_structure_identical():
    """dict 格式输出：块数量、文本、分数与盒子一致。"""
    opts = {
        "ocr.language": "简体中文",
        "ocr.angle": False,
        "ocr.maxSideLen": 1024,
        "tbpu.parser": "multi_para",
        "data.format": "dict",
    }
    origin = _origin_ocr(IMG_ZH, opts)
    ours = recognize(IMG_ZH, parser="multi_para")
    assert origin["code"] == 100
    ob, mb = origin["data"], ours.blocks
    assert len(ob) == len(mb)
    for a, b in zip(ob, mb):
        assert a["text"] == b["text"]
        assert a["score"] == b["score"]
        assert a["box"] == b["box"]


def test_get_options_identical():
    """选项表与原版完全一致。"""
    origin = json.loads(
        urllib.request.urlopen(ORIGIN_UMI_API + "/api/ocr/get_options", timeout=5)
        .read()
        .decode("utf-8")
    )
    ours = get_options()
    assert ours == origin, "get_options 应与原版完全一致"
