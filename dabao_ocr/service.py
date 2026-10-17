# -*- coding: utf-8 -*-
"""复用本机常驻 HTTP 服务的快通道

CLI 每次调用都要重新拉起引擎子进程（实测：加载模型 ~0.35s + 进程启动 ~0.45s），
而本机通常已经有一个常驻服务（scripts/serve.cmd + 看门狗，默认端口 18224）。
命中则走 HTTP，省掉这部分固定开销；未命中毫秒级回落本地引擎，行为与直连一致。

两个细节：
- 先用 50ms 的 TCP 探活，再发真正的请求。避免"服务没起"时把整段 HTTP 超时等满。
- 连接超时与读取超时分开：连接要快，读取要能等完一次大图识别。

关闭方式：
    环境变量 DABAO_OCR_NO_SERVICE=1  或 CLI 的 --no-service
自定义地址：
    环境变量 DABAO_OCR_SERVICE_URL=http://127.0.0.1:18224
"""

import base64
import http.client
import json
import os
import socket
from urllib.parse import urlsplit

from .engine import DEFAULT_TIMEOUT
from .log import logger

DEFAULT_PORT = 18224
PROBE_TIMEOUT = 0.05  # 探活超时（秒）：本机端口被拒是毫秒级
CONNECT_TIMEOUT = 1.0  # 探活通过后的建连超时

_probe_state = None  # None=尚未探测；True/False=本次进程内的探活结果


def service_url():
    """返回可用的服务基地址；被禁用时返回 None。"""
    if os.environ.get("DABAO_OCR_NO_SERVICE"):
        return None
    return os.environ.get("DABAO_OCR_SERVICE_URL") or f"http://127.0.0.1:{DEFAULT_PORT}"


def _parse(base):
    u = urlsplit(base)
    if u.scheme == "https":
        return u.hostname, u.port or 443, u.path.rstrip("/"), http.client.HTTPSConnection
    return u.hostname, u.port or 80, u.path.rstrip("/"), http.client.HTTPConnection


def _available(base) -> bool:
    """探活（每个进程只做一次）。"""
    global _probe_state
    if _probe_state is None:
        host, port, _, _ = _parse(base)
        try:
            with socket.create_connection((host, port), timeout=PROBE_TIMEOUT):
                _probe_state = True
        except OSError:
            _probe_state = False
    return _probe_state


def try_ocr(path=None, image_bytes=None, image_base64=None, options=None, timeout=None):
    """尝试通过常驻服务识别。

    :return: 服务响应字典 {"code", "data"}；服务不可用/响应异常时返回 None，
             由调用方回落本地引擎。
    """
    base = service_url()
    if not base or not _available(base):
        return None

    payload = {"options": dict(options or {})}
    if path is not None:
        payload["path"] = str(path)
    elif image_base64 is not None:
        payload["base64"] = image_base64
    elif image_bytes is not None:
        payload["base64"] = base64.b64encode(image_bytes).decode("ascii")
    else:
        return None

    host, port, prefix, conn_cls = _parse(base)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    conn = conn_cls(host, port, timeout=CONNECT_TIMEOUT)
    try:
        conn.connect()
        conn.sock.settimeout(timeout or DEFAULT_TIMEOUT)  # 识别本身可能很慢
        conn.request(
            "POST",
            prefix + "/api/ocr",
            body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        raw = conn.getresponse().read()
        res = json.loads(raw.decode("utf-8"))
    except Exception as e:  # 连接失败 / 超时 / 非 JSON，一律回落本地引擎
        logger.debug("常驻服务不可用，回落本地引擎：%s", e)
        return None
    finally:
        conn.close()

    if not isinstance(res, dict) or "code" not in res:
        return None
    return res
