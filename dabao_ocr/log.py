# -*- coding: utf-8 -*-
"""Dabao-OCR 日志模块

统一 logger，默认输出到 stderr；可通过环境变量 DABAO_OCR_LOG_LEVEL 控制级别
（DEBUG / INFO / WARNING / ERROR，默认 WARNING 保持 CLI 输出干净）。
"""

import logging
import os
import sys

_LEVEL = os.environ.get("DABAO_OCR_LOG_LEVEL", "WARNING").upper()

logger = logging.getLogger("dabao_ocr")
if not logger.handlers:
    _h = logging.StreamHandler(sys.stderr)
    _h.setFormatter(
        logging.Formatter("[dabao-ocr][%(levelname)s] %(message)s")
    )
    logger.addHandler(_h)
    try:
        logger.setLevel(getattr(logging, _LEVEL, logging.WARNING))
    except Exception:
        logger.setLevel(logging.WARNING)
    logger.propagate = False
