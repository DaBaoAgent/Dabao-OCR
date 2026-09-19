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

# 注：原版 Umi-OCR 对比测试（test_parity_umi / test_tbpu_parity）已于 2026-09-20
# 随本机 Umi-OCR 被彻底删除而移除 —— 它们依赖的 ORIGIN_UMI_TBPU 源码路径与
# ORIGIN_UMI_API(:1224) 在本机都不再存在，留着也只是永久 skip 的假覆盖。
# 需要重做「与原版逐字符/逐块一致」的金标准验证时：自行安装原版 Umi-OCR，
# 并按 git 历史（本次移除提交的父提交）恢复这两个测试文件即可。


@pytest.fixture(scope="session", autouse=True)
def _cleanup_engines():
    yield
    try:
        from dabao_ocr.engine import clear_engines

        clear_engines()
    except Exception:
        pass
