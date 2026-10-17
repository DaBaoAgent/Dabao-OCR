# -*- coding: utf-8 -*-
"""导出器测试：txt / json / jsonl / md / csv 五种格式与编码降级。"""

import csv
import json

import pytest

from dabao_ocr.exporters import (export, result_to_record, write_csv_file,
                                 write_json_file, write_jsonl_file,
                                 write_md_file, write_text_file)
from dabao_ocr.result import OcrResult


def _result(text="系统信息\n设备名称", code=100, end="\n"):
    blocks = [{"text": t, "end": end, "box": [[0, 0], [1, 0], [1, 1], [0, 1]], "score": 0.9}
              for t in text.split("\n")]
    return OcrResult(code, blocks)


def _items(*pairs):
    """pairs: (name, path, OcrResult)"""
    return [{"name": n, "path": p, "result": r} for n, p, r in pairs]


def _read_csv(path):
    """CSV 编码是按内容降级的（本机中文 → GBK），读回时自动适配。"""
    raw = path.read_bytes()
    for enc in ("utf-8", "gbk"):
        try:
            return list(csv.reader(raw.decode(enc).splitlines()))
        except UnicodeDecodeError:
            continue
    raise AssertionError(f"无法解码 CSV：{path}")


class TestSingleFileWriters:
    def test_write_text(self, tmp_path):
        p = tmp_path / "a.txt"
        write_text_file(p, "中文\n第二行")
        assert p.read_text(encoding="utf-8") == "中文\n第二行"

    def test_write_json(self, tmp_path):
        p = tmp_path / "a.json"
        write_json_file(p, {"code": 100, "data": "中文"})
        assert json.loads(p.read_text(encoding="utf-8"))["data"] == "中文"

    def test_write_jsonl(self, tmp_path):
        p = tmp_path / "a.jsonl"
        write_jsonl_file(p, [{"a": 1}, {"a": 2}])
        lines = p.read_text(encoding="utf-8").strip().split("\n")
        assert [json.loads(x)["a"] for x in lines] == [1, 2]

    def test_write_md(self, tmp_path):
        p = tmp_path / "a.md"
        write_md_file(p, [{"name": "图 1.png", "image_rel_path": "img/a b.png", "text": "第一行\n第二行"}],
                      start_datetime="2026-10-17 21:00")
        content = p.read_text(encoding="utf-8")
        assert content.startswith("> 2026-10-17 21:00")
        assert "img/a%20b.png" in content  # 空格必须转义
        assert "> 第一行  " in content and "> 第二行  " in content

    def test_write_csv(self, tmp_path):
        p = tmp_path / "a.csv"
        write_csv_file(p, [["图1.png", "识别文本", "D:/a.png"]])
        rows = _read_csv(p)
        assert rows[0] == ["Name", "OCR", "Path"]
        assert rows[1][0] == "图1.png"


class TestCsvEncoding:
    def test_ascii_text_with_chinese_filename_does_not_crash(self, tmp_path):
        """编码探测必须覆盖所有列：只测 OCR 文本列时，中文文件名会让写入崩掉。"""
        p = tmp_path / "a.csv"
        write_csv_file(p, [["中文文件名.png", "pure ascii text", "D:/x.png"]])
        raw = p.read_bytes()
        assert raw  # 没抛异常，文件已写出
        assert b"pure ascii text" in raw

    def test_chinese_text_picks_non_utf8_codepage(self, tmp_path):
        """中文内容应优先落到系统 ANSI（本机 GBK），与 Umi-OCR 行为一致。"""
        p = tmp_path / "b.csv"
        write_csv_file(p, [["a.png", "中文识别结果", "D:/a.png"]])
        raw = p.read_bytes()
        assert "中文识别结果".encode("gbk") in raw  # GBK 双字节，不是 UTF-8


class TestExportFormats:
    def test_txt(self, tmp_path):
        export(_items(("a.png", "D:/a.png", _result("第一张")),
                      ("b.png", "D:/b.png", _result("第二张"))),
               str(tmp_path), "out", "txt")
        text = (tmp_path / "out.txt").read_text(encoding="utf-8")
        assert "第一张" in text and "第二张" in text
        assert text.endswith("\n")  # 每份结果都补齐换行

    def test_json_records(self, tmp_path):
        export(_items(("a.png", "D:/a.png", _result("文本"))), str(tmp_path), "out", "json")
        data = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
        assert isinstance(data, list) and len(data) == 1
        assert data[0]["fileName"] == "a.png"
        assert data[0]["path"] == "D:/a.png"
        assert data[0]["code"] == 100

    def test_jsonl_records(self, tmp_path):
        export(_items(("a.png", "D:/a.png", _result("文本"))), str(tmp_path), "out", "jsonl")
        line = (tmp_path / "out.jsonl").read_text(encoding="utf-8").strip()
        assert json.loads(line)["fileName"] == "a.png"

    def test_md(self, tmp_path):
        export(_items(("a.png", str(tmp_path / "a.png"), _result("文本"))),
               str(tmp_path), "out", "md", start_datetime="2026-10-17")
        content = (tmp_path / "out.md").read_text(encoding="utf-8")
        assert "> 2026-10-17" in content
        assert "![a.png](a.png)" in content  # 同目录 → 相对路径

    def test_csv_error_and_empty_rows(self, tmp_path):
        export(_items(("ok.png", "D:/ok.png", _result("正常")),
                      ("empty.png", "D:/e.png", OcrResult(101, "no text")),
                      ("bad.png", "D:/b.png", OcrResult(902, "boom"))),
               str(tmp_path), "out", "csv")
        rows = _read_csv(tmp_path / "out.csv")
        assert rows[1][1] == "正常"
        assert rows[2][1] == ""                    # 101 无文字 → 空
        assert "[Error] OCR failed. Code: 902" in rows[3][1]

    def test_unsupported_format(self, tmp_path):
        with pytest.raises(ValueError):
            export(_items(("a.png", "D:/a.png", _result())), str(tmp_path), "out", "xml")

    def test_creates_out_dir(self, tmp_path):
        out = tmp_path / "deep" / "nested"
        export(_items(("a.png", "D:/a.png", _result("x"))), str(out), "out", "txt")
        assert (out / "out.txt").exists()

    def test_result_to_record(self):
        rec = result_to_record("a.png", _result("文本"), "D:/a.png")
        assert set(rec) == {"code", "data", "fileName", "path"}
        assert rec["code"] == 100
