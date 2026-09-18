# -*- coding: utf-8 -*-
"""Dabao-OCR 看门狗：健康检查 HTTP 服务，不健康则拉起。

由 Windows 计划任务（DabaoOCR_Watchdog）每 5 分钟调用一次；
也可手动运行：.venv\\Scripts\\python.exe scripts\\watchdog.py

判活标准：GET http://127.0.0.1:18224/api/status 返回 name == "DabaoOCR"。
"""

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 18224
STATUS_URL = f"http://127.0.0.1:{PORT}/api/status"
LOG_FILE = ROOT / "logs" / "serve.log"


def healthy(timeout: float = 5.0) -> bool:
    """服务是否健康（响应且是我们的服务）。"""
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data.get("name") == "DabaoOCR"
    except Exception:
        return False


def spawn_server():
    """以完全脱离模式拉起服务（父进程退出后继续存活）。"""
    if sys.platform.startswith("win"):
        pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    else:
        pythonw = ROOT / ".venv" / "bin" / "python"
    if not pythonw.exists():
        pythonw = ROOT / ".venv" / "Scripts" / "python.exe"
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "a", encoding="utf-8")
    try:
        log.write(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [watchdog] spawning server\n"
        )
        log.flush()
    except OSError:
        pass
    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        [str(pythonw), "-m", "dabao_ocr", "serve", "--port", str(PORT)],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        close_fds=True,
    )


def main() -> int:
    # 先清理可能存在的僵尸监听（服务进程崩溃但端口未释放属极端情况，交由服务自身处理）
    if healthy():
        return 0  # 健康，静默退出
    spawn_server()
    # 等启动完成（引擎懒加载，HTTP 服务本身应 3 秒内就绪）
    for _ in range(15):
        time.sleep(1)
        if healthy():
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
