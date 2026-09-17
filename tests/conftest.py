# -*- coding: utf-8 -*-
"""pytest 公共配置：项目根目录注入 sys.path、资产路径、引擎清理。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

ASSETS = Path(__file__).resolve().parent / "assets"

IMG_ZH = str(ASSETS / "info_panel.png")
IMG_ZH2 = str(ASSETS / "multi_column.png")
IMG_MULTI = str(ASSETS / "multi_column.png")
PDF_SAMPLE = str(ASSETS / "sample_two_pages.pdf")

# 原版 Umi-OCR 安装位置（用于一致性对比测试；不存在时相关测试自动跳过）
ORIGIN_UMI_TBPU = Path(
    r"D:\@kaifa\Umi-OCR\Umi-OCR_Rapid_v2.1.5\UmiOCR-data\py_src\ocr\tbpu"
)
ORIGIN_UMI_API = "http://127.0.0.1:1224"


@pytest.fixture(scope="session", autouse=True)
def _cleanup_engines():
    yield
    try:
        from dabao_ocr.engine import clear_engines

        clear_engines()
    except Exception:
        pass
