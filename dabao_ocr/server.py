# -*- coding: utf-8 -*-
"""Dabao-OCR HTTP API 服务（stdlib 实现，无第三方依赖）

兼容 Umi-OCR v2 HTTP API：
    GET  /api/ocr/get_options   → 选项表
    POST /api/ocr               → {"base64": ..., "options": {...}} 识别
                                  （Dabao-OCR 扩展：可用 "path" 代替 "base64"）

增强端点：
    GET  /api/status            → 服务与引擎状态
    POST /api/ocr/batch         → 批量识别 {"images": [{"base64"|"path"}...], "options": {...}}
    POST /api/pdf               → PDF 识别 {"path"|"base64", "options": {"dpi", "pages", ...}}

通用约定（与原版一致）：
    - 响应 JSON 含 code / data；code=100 成功、101 无文字、8xx 请求错误
    - CORS 全开，便于本机网页调用
"""

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import _version
from .engine import (CODE_NO_TEXT, OcrEngineError, clear_engines, get_engine,
                     list_languages)
from .log import logger
from .ocr import recognize
from .options import fill_defaults, get_options, validate_options
from .result import OcrResult

__version__ = _version.__version__

SERVER_NAME = "DabaoOCR"


def _result_to_response(result: OcrResult, data_format: str = "dict") -> dict:
    if data_format == "text":
        return result.to_text_dict()
    return result.to_dict()


def _run_ocr(payload: dict, engine_dir=None) -> dict:
    """执行一次（兼容协议风格的）OCR 请求，返回响应字典。

    payload: {"base64": str} 或 {"path": str}，可带 "options": {...}
    """
    if not isinstance(payload, dict) or not payload:
        return {"code": 801, "data": "请求为空。"}
    raw_options = payload.get("options", {})
    if raw_options is None:
        raw_options = {}
    if not isinstance(raw_options, dict):
        return {"code": 803, "data": "请求中 options 字段必须为字典。"}
    try:
        opt = fill_defaults(raw_options, engine_dir)
        validate_options(opt, engine_dir)
    except ValueError as e:
        return {"code": 804, "data": f"options 解释失败。 {e}"}
    except Exception as e:
        return {"code": 804, "data": f"options 解释失败。 {e}"}

    parser = opt.get("tbpu.parser", "multi_para")
    ignore_area = opt.get("tbpu.ignoreArea") or None
    kwargs = dict(
        language=opt.get("ocr.language", "简体中文"),
        angle=bool(opt.get("ocr.angle", False)),
        max_side_len=int(opt.get("ocr.maxSideLen", 1024) or 1024),
        parser=parser,
        ignore_area=ignore_area,
        engine_dir=engine_dir,
    )
    try:
        if "base64" in payload and payload["base64"]:
            from .ocr import recognize_base64

            result = recognize_base64(payload["base64"], **kwargs)
        elif "path" in payload and payload["path"]:
            result = recognize(payload["path"], **kwargs)
        else:
            return {"code": 802, "data": "请求中缺少 base64 字段。"}
    except OcrEngineError as e:
        return {"code": 902, "data": f"引擎错误：{e}"}
    except Exception as e:
        logger.exception("OCR 执行失败")
        return {"code": 900, "data": f"OCR 执行失败：{e}"}
    return _result_to_response(result, opt.get("data.format", "dict"))


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"{SERVER_NAME}/{__version__}"
    # 由 server 实例注入
    engine_dir = None
    max_body = 128 * 1024 * 1024  # 128 MB 请求上限

    # -------------------------------------------------- 基础设施
    def log_message(self, fmt, *args):
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text, status=200, ctype="text/plain; charset=utf-8"):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        """读请求体并解析 JSON。返回 (data, error_response|None)。"""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return None, {"code": 801, "data": "请求为空。"}
        if length > self.max_body:
            return None, {"code": 800, "data": "请求体过大。"}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8")), None
        except Exception as e:
            return None, {"code": 800, "data": f"请求无法解析为json。 {e}"}

    # -------------------------------------------------- 路由
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in ("/", ""):
            self._send_text(
                f"{SERVER_NAME} v{__version__} — 离线 OCR HTTP API（Umi-OCR 兼容）\n"
                "POST /api/ocr  识别图片（base64 或本机 path）\n"
                "GET  /api/ocr/get_options  选项表\n"
                "GET  /api/status  状态\n",
                ctype="text/plain; charset=utf-8",
            )
        elif path == "/api/ocr/get_options":
            try:
                opts = get_options(self.engine_dir)
                self._send_json(opts)
            except Exception as e:
                self._send_json({"code": 900, "data": f"读取选项失败：{e}"})
        elif path == "/api/status":
            self._send_json(self.server.status_info())
        else:
            self._send_json({"code": 404, "data": "Not Found"}, status=404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        if path == "/api/ocr":
            data, err = self._read_json()
            if err:
                self._send_json(err)
                return
            self._send_json(_run_ocr(data, self.engine_dir))
        elif path == "/api/ocr/batch":
            self._handle_batch()
        elif path == "/api/pdf":
            self._handle_pdf()
        else:
            self._send_json({"code": 404, "data": "Not Found"}, status=404)

    # -------------------------------------------------- 增强端点
    def _handle_batch(self):
        data, err = self._read_json()
        if err:
            self._send_json(err)
            return
        if not isinstance(data, dict) or not data:
            self._send_json({"code": 801, "data": "请求为空。"})
            return
        images = data.get("images")
        if not isinstance(images, list) or not images:
            self._send_json({"code": 802, "data": "请求中缺少 images 数组。"})
            return
        results = []
        for item in images:
            if isinstance(item, str):  # 允许直接给路径/base64 字符串
                item = {"base64": item} if not _looks_like_path(item) else {"path": item}
            if not isinstance(item, dict):
                results.append({"code": 803, "data": "images 项必须为对象。"})
                continue
            payload = {"options": data.get("options", {})}
            payload.update({k: item[k] for k in ("base64", "path") if k in item})
            results.append(_run_ocr(payload, self.engine_dir))
        self._send_json({"code": 100, "data": results})

    def _handle_pdf(self):
        data, err = self._read_json()
        if err:
            self._send_json(err)
            return
        if not isinstance(data, dict) or not data:
            self._send_json({"code": 801, "data": "请求为空。"})
            return
        opt_in = data.get("options", {}) or {}
        if not isinstance(opt_in, dict):
            self._send_json({"code": 803, "data": "请求中 options 字段必须为字典。"})
            return
        src_pdf = data.get("path")
        tmp = None
        try:
            if not src_pdf and data.get("base64"):
                import base64 as _b64
                import tempfile

                raw = _b64.b64decode(data["base64"])
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp.write(raw)
                tmp.close()
                src_pdf = tmp.name
            if not src_pdf:
                self._send_json({"code": 802, "data": "请求中缺少 path 或 base64 字段。"})
                return
            from .pdf import ocr_pdf

            results = ocr_pdf(
                src_pdf,
                dpi=int(opt_in.get("dpi", 200)),
                pages=opt_in.get("pages"),
                password=opt_in.get("password"),
                language=opt_in.get("ocr.language", "简体中文"),
                angle=bool(opt_in.get("ocr.angle", False)),
                max_side_len=int(opt_in.get("ocr.maxSideLen", 1024) or 1024),
                parser=opt_in.get("tbpu.parser", "multi_para"),
                engine_dir=self.engine_dir,
            )
            data_fmt = opt_in.get("data.format", "text")
            out = []
            for pr in results:
                if data_fmt == "dict":
                    out.append({"page": pr.pno, "result": pr.result.to_dict()})
                else:
                    out.append({"page": pr.pno, "text": pr.text,
                                "code": pr.result.code})
            self._send_json({"code": 100, "data": out})
        except ImportError as e:
            self._send_json({"code": 900, "data": str(e)})
        except Exception as e:
            logger.exception("PDF 处理失败")
            self._send_json({"code": 900, "data": f"PDF 处理失败：{e}"})
        finally:
            if tmp is not None:
                try:
                    import os

                    os.unlink(tmp.name)
                except OSError:
                    pass


def _looks_like_path(s: str) -> bool:
    return ("\\" in s or "/" in s) and len(s) < 4096


class DabaoOcrServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, host, port, engine_dir=None):
        super().__init__((host, port), _Handler)
        _Handler.engine_dir = engine_dir
        self.engine_dir = engine_dir
        self.started_at = time.time()

    def status_info(self) -> dict:
        try:
            langs = list_languages(self.engine_dir)
        except Exception:
            langs = {}
        return {
            "name": SERVER_NAME,
            "version": __version__,
            "uptime_sec": round(time.time() - self.started_at, 1),
            "engine_dir": str(self.engine_dir) if self.engine_dir else "default",
            "languages": langs,
        }


def serve(host: str = "127.0.0.1", port: int = 18224, engine_dir=None, blocking=True):
    """启动 HTTP 服务。blocking=False 时后台线程运行并返回 server 对象。"""
    server = DabaoOcrServer(host, port, engine_dir=engine_dir)
    logger.info("服务启动: http://%s:%s", host, port)
    if not blocking:
        t = threading.Thread(target=server.serve_forever, name="dabao-ocr-server", daemon=True)
        t.start()
        return server
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("收到中断，正在退出…")
    finally:
        server.server_close()
        clear_engines()


def find_free_port(host: str = "127.0.0.1", start: int = 18224, tries: int = 20) -> int:
    """从 start 起找一个空闲端口（原版风格的端口自增逻辑）。"""
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    raise OSError(f"{host}:{start}~{start + tries - 1} 均被占用。")
