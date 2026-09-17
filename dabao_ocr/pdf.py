# -*- coding: utf-8 -*-
"""PDF OCR：逐页渲染 → 识别 → 文本 / 双层可搜索 PDF

双层 PDF 写入逻辑移植自 Umi-OCR（MIT, © hiroi-sora）的 output_pdf_layered，
依赖 PyMuPDF（fitz）。
"""

import os
from dataclasses import dataclass
from pathlib import Path

from .log import logger
from .ocr import DEFAULT_PARSER, _finish
from .result import OcrResult

# 渲染 DPI：越高越准越慢（Umi-OCR 默认档位 120 左右；agent 场景默认 200 平衡）
DEFAULT_DPI = 200


def _require_fitz():
    try:
        import pymupdf as fitz  # PyMuPDF >= 1.24 新名

        return fitz
    except ImportError:
        pass
    try:
        import fitz

        return fitz
    except ImportError as e:
        raise ImportError(
            "PDF 功能需要 PyMuPDF：pip install PyMuPDF（或 pip install dabao-ocr[pdf]）"
        ) from e


def parse_pages_spec(spec, total: int) -> list:
    """解析页范围字符串，如 '1-3,5' → [0,1,2,4]（0 基）。None → 全部页。"""
    if not spec:
        return list(range(total))
    out = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            a = int(a) if a.strip() else 1
            b = int(b) if b.strip() else total
            for i in range(a, b + 1):
                if 1 <= i <= total and (i - 1) not in out:
                    out.append(i - 1)
        else:
            i = int(part)
            if 1 <= i <= total and (i - 1) not in out:
                out.append(i - 1)
    return sorted(out)


@dataclass
class PdfPageResult:
    pno: int  # 1 基页码
    result: OcrResult

    @property
    def text(self) -> str:
        return self.result.text


def render_pdf_pages(pdf_path, dpi: int = DEFAULT_DPI, pages=None, password: str = None):
    """把 PDF 每页渲染为 PNG 字节。yield (pno0, png_bytes)。"""
    fitz = _require_fitz()
    doc = fitz.open(str(pdf_path))
    try:
        if doc.is_encrypted:
            if not password or not doc.authenticate(password):
                raise ValueError("PDF 已加密且密码不正确。")
        total = len(doc)
        for i in parse_pages_spec(pages, total):
            page = doc[i]
            pix = page.get_pixmap(dpi=dpi)
            yield i, pix.tobytes("png")
    finally:
        doc.close()


def ocr_pdf(
    pdf_path,
    *,
    dpi: int = DEFAULT_DPI,
    pages=None,
    password: str = None,
    parser: str = DEFAULT_PARSER,
    ignore_area=None,
    language: str = "简体中文",
    angle: bool = False,
    max_side_len: int = 1024,
    num_thread: int = None,
    engine=None,
    engine_dir=None,
    on_page=None,
) -> list:
    """对 PDF 逐页 OCR，返回 [PdfPageResult]。on_page(pno, page_result) 可选回调。"""
    from .engine import get_engine

    eng = engine or get_engine(
        {
            "language": language,
            "angle": angle,
            "maxSideLen": max_side_len,
            "numThread": num_thread,
        },
        engine_dir,
    )
    results = []
    for i, png in render_pdf_pages(pdf_path, dpi=dpi, pages=pages, password=password):
        res = _finish(eng.run_bytes(png), parser, ignore_area)
        pr = PdfPageResult(i + 1, res)
        results.append(pr)
        if on_page:
            try:
                on_page(pr)
            except Exception:
                logger.exception("on_page 回调异常")
    return results


# ------------------------------------------------------------------ 双层 PDF
def _calculate_font_size(font, text: str, w: float, h: float) -> float:
    """计算恰好填满宽度的一行字号（移植自 Umi-OCR）。"""
    if h > w:  # 竖排转横排计算
        w, h = h, w
    fontsize = round(h)  # 以行高为初值
    min_size = 5
    get_len = lambda t, s: font.text_length(t, fontsize=s)  # noqa: E731
    while get_len(text, fontsize) > w and fontsize >= min_size:
        fontsize -= 1
    while get_len(text, fontsize) < w:
        fontsize += 1
    while get_len(text, fontsize) > w and fontsize >= min_size:
        fontsize -= 0.1
    return fontsize


def build_layered_pdf(
    src_pdf,
    out_path,
    pages_blocks: dict,
    password: str = None,
    opacity: float = 0,
):
    """生成双层（可搜索）PDF：在原始页面上写入透明文本层。

    :param pages_blocks: {页号0基: 文本块列表}（来自 PdfPageResult）
    """
    fitz = _require_fitz()
    doc = fitz.open(str(src_pdf))
    if doc.is_encrypted and not doc.authenticate(password or ""):
        raise ValueError("PDF 已加密且密码不正确。")
    font = fitz.Font("cjk")
    is_insert_font = False
    for pno, blocks in pages_blocks.items():
        if pno < 0 or pno >= len(doc):
            continue
        if not blocks:
            continue
        page = doc[pno]
        page.clean_contents()
        protation = page.rotation
        page_font_inserted = False
        for tb in blocks:
            if not page_font_inserted:
                is_insert_font = page_font_inserted = True
                page.insert_font(fontname="cjk", fontbuffer=font.buffer)
            text = tb.get("text", "")
            box = tb.get("box")
            if not text or not box:
                continue
            x0, y0 = box[0]
            x2, y2 = box[2]
            w, h = x2 - x0, y2 - y0
            fontsize = _calculate_font_size(font, text, w, h)
            point = fitz.Point(x0, y2) * page.derotation_matrix
            page.insert_text(
                point,
                text,
                fontsize=fontsize,  # PyMuPDF>=1.26 为 keyword-only，显式传参兼容新旧
                fontname="cjk",
                rotate=protation,
                stroke_opacity=opacity,
                fill_opacity=opacity,
            )
    try:
        if is_insert_font:
            try:
                doc.subset_fonts()
            except Exception:
                logger.warning("构建字体子集失败（忽略继续）。")
            doc.save(str(out_path), deflate=True, garbage=3)
        else:
            doc.save(str(out_path))
    finally:
        doc.close()
    return out_path


def pdf_results_to_text(page_results: list, page_sep: str = "\n") -> str:
    """多页结果拼为整文。"""
    parts = []
    for pr in page_results:
        parts.append(pr.text)
    return page_sep.join(parts)
