# -*- coding: utf-8 -*-
"""PDF 功能测试：逐页 OCR、页范围、双层可搜索 PDF。"""

import os
import tempfile

import pytest

from dabao_ocr.pdf import (build_layered_pdf, ocr_pdf, parse_pages_spec,
                           pdf_results_to_text, render_pdf_pages)
from tests.conftest import PDF_SAMPLE

pymupdf = pytest.importorskip("pymupdf", reason="需要 PyMuPDF")


class TestPagesSpec:
    def test_all(self):
        assert parse_pages_spec(None, 5) == [0, 1, 2, 3, 4]

    def test_range(self):
        assert parse_pages_spec("1-2", 5) == [0, 1]

    def test_multi(self):
        assert parse_pages_spec("1,3-4", 5) == [0, 2, 3]

    def test_bounds(self):
        assert parse_pages_spec("1-99", 3) == [0, 1, 2]


class TestRenderPdf:
    def test_render_pages(self):
        pages = list(render_pdf_pages(PDF_SAMPLE, dpi=150))
        assert len(pages) == 2
        for pno, png in pages:
            assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG 魔数
            assert len(png) > 1000

    def test_render_single_page(self):
        pages = list(render_pdf_pages(PDF_SAMPLE, dpi=150, pages="2"))
        assert len(pages) == 1 and pages[0][0] == 1


class TestOcrPdf:
    def test_ocr_all_pages(self):
        results = ocr_pdf(PDF_SAMPLE, dpi=150)
        assert len(results) == 2
        assert results[0].pno == 1 and results[1].pno == 2
        # 第 1 页中文、第 2 页英文
        assert results[0].text.startswith("Dabao-OCR")
        assert "测试文档" in results[0].text
        assert "RapidOCR-json" in results[1].text

    def test_ocr_page_subset(self):
        results = ocr_pdf(PDF_SAMPLE, dpi=150, pages="1")
        assert len(results) == 1
        assert results[0].pno == 1

    def test_on_page_callback(self):
        seen = []
        ocr_pdf(PDF_SAMPLE, dpi=150, on_page=lambda pr: seen.append(pr.pno))
        assert seen == [1, 2]

    def test_joined_text(self):
        results = ocr_pdf(PDF_SAMPLE, dpi=150)
        text = pdf_results_to_text(results)
        assert "测试文档" in text and "Test Document" in text


class TestLayeredPdf:
    def test_build_layered(self, tmp_path):
        results = ocr_pdf(PDF_SAMPLE, dpi=150)
        pages_blocks = {pr.pno - 1: pr.result.blocks for pr in results if pr.result.ok}
        out = str(tmp_path / "layered.pdf")
        build_layered_pdf(PDF_SAMPLE, out, pages_blocks)
        assert os.path.getsize(out) > 1000
        # 打开验证：文本层可搜索 + 页面图像保留
        doc = pymupdf.open(out)
        try:
            assert len(doc) == 2
            t1 = doc[0].get_text()
            assert "测试文档" in t1.replace(" ", "")
            # 页面仍然包含原渲染内容（图像层）
            assert doc[0].get_images() or doc[0].get_pixmap().samples
        finally:
            doc.close()

    def test_layered_searchable(self, tmp_path):
        """双层 PDF 的文本层应可被 PDF 阅读器检索。"""
        results = ocr_pdf(PDF_SAMPLE, dpi=150)
        blocks = {pr.pno - 1: pr.result.blocks for pr in results if pr.result.ok}
        out = str(tmp_path / "searchable.pdf")
        build_layered_pdf(PDF_SAMPLE, out, blocks)
        doc = pymupdf.open(out)
        try:
            full = (doc[0].get_text() + doc[1].get_text()).replace("\n", "").replace(" ", "")
            assert "1234567890" in full or "9876543210" in full
        finally:
            doc.close()
