# -*- coding: utf-8 -*-
"""Dabao-OCR — 离线 OCR 后端（Umi-OCR 衍生的 agent 友好工具包）

用法速览：
    from dabao_ocr import recognize

    result = recognize("photo.png")
    print(result.text)

    result = recognize("photo.png", parser="single_line", language="English")
    for blk in result.blocks:
        print(blk["text"], blk["score"], blk["box"])
"""

from ._version import __version__
from .engine import (CODE_NO_TEXT, CODE_SUCCESS, OcrEngine, OcrEngineError,
                     clear_engines, get_engine, list_languages,
                     default_engine_dir)
from .ocr import (IMAGE_SUFFIXES, recognize, recognize_base64, recognize_file)
from .result import OcrResult, data_to_text

__all__ = [
    "__version__",
    "OcrEngine",
    "OcrEngineError",
    "get_engine",
    "clear_engines",
    "default_engine_dir",
    "list_languages",
    "recognize",
    "recognize_base64",
    "recognize_file",
    "OcrResult",
    "data_to_text",
    "IMAGE_SUFFIXES",
    "CODE_SUCCESS",
    "CODE_NO_TEXT",
]
