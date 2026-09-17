# -*- coding: utf-8 -*-
"""CLI 端到端测试：以子进程方式运行 python -m dabao_ocr。"""

import json
import os
import subprocess
import sys

import pytest

from tests.conftest import IMG_ZH, IMG_ZH2, PDF_SAMPLE, ROOT


def run_cli(*args, timeout=120):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "dabao_ocr", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )


class TestOcrCommand:
    def test_text_output(self):
        r = run_cli("ocr", IMG_ZH)
        assert r.returncode == 0
        assert "系统" in r.stdout

    def test_json_output(self):
        r = run_cli("ocr", IMG_ZH, "--json")
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert data["code"] == 100
        assert isinstance(data["data"], list)
        assert any("系统" in b["text"] for b in data["data"])

    def test_output_to_file(self, tmp_path):
        out = tmp_path / "out.txt"
        r = run_cli("ocr", IMG_ZH, "-o", str(out))
        assert r.returncode == 0
        assert "系统" in out.read_text(encoding="utf-8")

    def test_parser_option(self):
        r = run_cli("ocr", IMG_ZH, "--parser", "single_line")
        assert r.returncode == 0

    def test_missing_file(self):
        r = run_cli("ocr", "Z:/nope/missing_xyz.png")
        assert r.returncode == 2
        assert "Error" in r.stderr

    def test_stdin_bytes(self, tmp_path):
        data = open(IMG_ZH, "rb").read()
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        r = subprocess.run(
            [sys.executable, "-m", "dabao_ocr", "ocr", "-"],
            cwd=str(ROOT),
            input=data,
            capture_output=True,
            timeout=120,
            env=env,
        )
        assert r.returncode == 0
        assert "系统".encode("utf-8") in r.stdout


class TestInfoCommand:
    def test_info(self):
        r = run_cli("info")
        assert r.returncode == 0
        info = json.loads(r.stdout)
        assert info["name"] == "Dabao-OCR"
        assert info["engine_exe_ok"] is True
        assert "简体中文" in info["languages"]["languages"]


class TestBatchCommand:
    def test_batch_stdout_jsonl(self):
        r = run_cli("batch", IMG_ZH, IMG_ZH2)
        assert r.returncode == 0
        lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
        assert len(lines) == 2
        for line in lines:
            rec = json.loads(line)
            assert "path" in rec and "code" in rec

    def test_batch_out_dir(self, tmp_path):
        r = run_cli("batch", IMG_ZH, "-o", str(tmp_path), "--format", "txt")
        assert r.returncode == 0
        files = list(tmp_path.glob("*.txt"))
        assert files
        assert "系统" in files[0].read_text(encoding="utf-8")

    def test_batch_out_dir_md_cross_drive(self, tmp_path):
        """md 导出在跨盘符输出目录下不能崩溃（Windows relpath 限制）。"""
        r = run_cli("batch", IMG_ZH, "-o", str(tmp_path), "--format", "md")
        assert r.returncode == 0, r.stderr
        files = list(tmp_path.glob("*.md"))
        assert files
        content = files[0].read_text(encoding="utf-8")
        assert "系统信息" in content


class TestPdfCommand:
    def test_pdf_text(self):
        r = run_cli("pdf", PDF_SAMPLE, "--dpi", "150")
        assert r.returncode == 0
        assert "Dabao-OCR" in r.stdout

    def test_pdf_jsonl_and_layered(self, tmp_path):
        layered = tmp_path / "out.layered.pdf"
        r = run_cli("pdf", PDF_SAMPLE, "--dpi", "150", "--jsonl",
                    "--layered", str(layered))
        assert r.returncode == 0
        lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0])["page"] == 1
        assert layered.exists() and layered.stat().st_size > 1000


class TestVersion:
    def test_version_flag(self):
        r = run_cli("--version")
        assert r.returncode == 0
        assert "Dabao-OCR" in r.stdout
