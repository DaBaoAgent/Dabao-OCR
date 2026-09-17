# -*- coding: utf-8 -*-
"""Dabao-OCR 引擎封装（RapidOCR-json 管道调用）

源自 Umi-OCR（MIT License, © hiroi-sora）的 RapidOCR-json 适配层，
已剥离 Qt 前端依赖，重写为独立的、线程安全的进程管理实现：

- 常驻子进程，stdin/stdout JSON 行协议（与引擎原生协议一致）
- 线程安全：读写分离（读线程 + 队列），请求串行化（锁）
- 超时保护、崩溃自动重启 + 一次重试
- 不同参数组合的引擎实例按 LRU 缓存复用（默认上限 2 个）
"""

import atexit
import base64
import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path

from .langs import DEFAULT_LANGUAGE, get_language_dict, resolve_language
from .log import logger

# 单次识别请求的超时（秒），大图/低配机可调大
DEFAULT_TIMEOUT = float(os.environ.get("DABAO_OCR_TIMEOUT", "180"))
# 引擎实例缓存上限（每实例 = 一个常驻进程，吃一份模型内存）
MAX_CACHED_ENGINES = int(os.environ.get("DABAO_OCR_MAX_ENGINES", "2"))

# 引擎成功 / 无文字 返回码（与 RapidOCR-json 协议一致）
CODE_SUCCESS = 100
CODE_NO_TEXT = 101


class OcrEngineError(RuntimeError):
    """引擎运行错误（启动失败 / 崩溃 / 超时）"""


def default_engine_dir() -> Path:
    """定位引擎目录：环境变量优先，否则用仓库内 vendor/RapidOCR-json。"""
    env = os.environ.get("DABAO_OCR_ENGINE_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
        raise FileNotFoundError(f"DABAO_OCR_ENGINE_DIR 指向的目录不存在：{env}")
    cand = Path(__file__).resolve().parent.parent / "vendor" / "RapidOCR-json"
    if cand.is_dir():
        return cand
    raise FileNotFoundError(
        "找不到 RapidOCR-json 引擎目录。请设置环境变量 DABAO_OCR_ENGINE_DIR，"
        f"或确认 {cand} 存在。"
    )


def normalize_options(options: dict = None, engine_dir=None) -> dict:
    """把用户级参数归一化为引擎级参数（用于启动命令行与缓存 key）。

    接受键：language / det / cls / rec / keys / angle / maxSideLen / numThread
    （同时兼容蛇形命名 max_side_len / num_thread）
    """
    o = dict(options or {})
    ed = Path(engine_dir) if engine_dir else default_engine_dir()

    lang = o.get("language") or DEFAULT_LANGUAGE
    resolved = None
    if not (o.get("det") and o.get("cls") and o.get("rec") and o.get("keys")):
        resolved = resolve_language(lang, ed)

    res = {
        "det": o.get("det") or resolved["det"],
        "cls": o.get("cls") or resolved["cls"],
        "rec": o.get("rec") or resolved["rec"],
        "keys": o.get("keys") or resolved["keys"],
        "angle": bool(o.get("angle", False)),
    }
    msl = o.get("maxSideLen", o.get("max_side_len"))
    res["maxSideLen"] = int(msl) if msl else 1024
    nt = o.get("numThread", o.get("num_thread"))
    res["numThread"] = int(nt) if nt else (os.cpu_count() or 4)
    return res


class OcrEngine:
    """一个 RapidOCR-json 引擎子进程的封装（线程安全）。

    同一实例的所有识别请求经由内部锁串行化；读线程持续消费 stdout 防管道阻塞。
    """

    def __init__(self, engine_dir=None, options: dict = None, timeout: float = None):
        self.dir = Path(engine_dir) if engine_dir else default_engine_dir()
        self.exe = self.dir / "RapidOCR-json.exe"
        if not self.exe.exists():
            raise FileNotFoundError(f"引擎可执行文件不存在：{self.exe}")
        self.options = normalize_options(options, self.dir)
        self.timeout = float(timeout) if timeout else DEFAULT_TIMEOUT
        self._proc = None
        self._q = None
        self._lock = threading.RLock()
        self._exit_hooked = False

    # ------------------------------------------------------------------ 命令
    def _build_command(self) -> list:
        o = self.options
        cmd = [str(self.exe), "--models=models"]
        for k in ("det", "cls", "rec", "keys"):
            cmd.append(f"--{k}={o[k]}")
        # 输出统一用 UTF-8 + ascii 转义，解析侧无损
        cmd.append("--ensureAscii=1")
        ang = 1 if o.get("angle") else 0
        cmd.append(f"--doAngle={ang}")
        cmd.append(f"--mostAngle={ang}")
        cmd.append(f"--maxSideLen={int(o['maxSideLen'])}")
        cmd.append(f"--numThread={int(o['numThread'])}")
        return cmd

    # ------------------------------------------------------------------ 生命周期
    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self):
        """启动引擎并等待初始化完成（幂等）。"""
        with self._lock:
            if self.alive:
                return
            self.stop()
            cmd = self._build_command()
            logger.debug("启动引擎：%s", " ".join(cmd))
            startupinfo = None
            if sys.platform.startswith("win"):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags = (
                    subprocess.CREATE_NEW_CONSOLE | subprocess.STARTF_USESHOWWINDOW
                )
                startupinfo.wShowWindow = subprocess.SW_HIDE
            self._proc = subprocess.Popen(
                cmd,
                cwd=str(self.dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                startupinfo=startupinfo,
            )
            self._q = queue.Queue()
            threading.Thread(
                target=self._read_loop,
                args=(self._proc.stdout, self._q),
                name="dabao-ocr-reader",
                daemon=True,
            ).start()
            deadline = time.monotonic() + self.timeout
            while True:
                if self._proc.poll() is not None:
                    code = self._proc.returncode
                    self.stop()
                    raise OcrEngineError(
                        f"引擎启动失败，进程提前退出（code={code}）。"
                        f"可尝试手动运行：{self.exe}"
                    )
                remain = deadline - time.monotonic()
                if remain <= 0:
                    self.stop()
                    raise OcrEngineError("引擎初始化超时。")
                try:
                    raw = self._q.get(timeout=min(remain, 0.5))
                except queue.Empty:
                    continue
                if raw is None:
                    continue
                line = raw.decode("utf-8", errors="ignore")
                if "OCR init completed." in line:
                    break
            if not self._exit_hooked:
                atexit.register(self.stop)
                self._exit_hooked = True
            logger.info("引擎就绪：%s", self.exe.name)

    def stop(self):
        """停止引擎子进程（幂等）。"""
        with self._lock:
            proc, self._proc = self._proc, None
            self._q = None
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                except Exception:
                    pass

    @staticmethod
    def _read_loop(stream, q: queue.Queue):
        """后台读线程：持续把 stdout 行塞进队列，EOF 放哨兵 None。"""
        try:
            for raw in iter(stream.readline, b""):
                q.put(raw)
        except Exception:
            pass
        finally:
            q.put(None)

    # ------------------------------------------------------------------ 请求
    def _request(self, payload: dict) -> dict:
        """发送一条指令并等待一行 JSON 响应（调用方保证锁内串行）。"""
        if not self.alive:
            self.start()
        line = json.dumps(payload, ensure_ascii=True) + "\n"
        try:
            self._proc.stdin.write(line.encode("utf-8"))
            self._proc.stdin.flush()
        except Exception as e:
            raise OcrEngineError(f"写入引擎失败（疑似进程崩溃）：{e}") from e
        deadline = time.monotonic() + self.timeout
        while True:
            if self._proc.poll() is not None:
                raise OcrEngineError(
                    f"引擎进程崩溃（code={self._proc.returncode}）。"
                )
            remain = deadline - time.monotonic()
            if remain <= 0:
                self.stop()
                raise OcrEngineError("引擎响应超时（已终止引擎，下次请求自动重启）。")
            try:
                raw = self._q.get(timeout=min(remain, 0.5))
            except queue.Empty:
                continue
            if raw is None:
                if self._proc.poll() is not None:
                    raise OcrEngineError("引擎输出流关闭（进程已退出）。")
                continue
            text = raw.decode("utf-8", errors="ignore").strip()
            if not text:
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                logger.debug("忽略引擎非 JSON 输出行：%s", text[:120])
                continue

    def _run_with_retry(self, payload: dict) -> dict:
        with self._lock:
            try:
                return self._request(payload)
            except OcrEngineError as e:
                logger.warning("引擎请求失败，重启后重试一次：%s", e)
                self.stop()
                self.start()
                return self._request(payload)

    # ------------------------------------------------------------------ 公开 API
    def run_path(self, image_path) -> dict:
        """识别本地图片路径。返回引擎原始响应 {"code": int, "data": list|str}。"""
        return self._run_with_retry({"image_path": str(image_path)})

    def run_base64(self, image_base64: str) -> dict:
        """识别 base64 图片。"""
        return self._run_with_retry({"image_base64": image_base64})

    def run_bytes(self, image_bytes: bytes) -> dict:
        """识别图片字节流。"""
        return self.run_base64(base64.b64encode(image_bytes).decode("ascii"))

    def info(self) -> dict:
        """引擎状态信息。"""
        return {
            "engine_dir": str(self.dir),
            "exe": str(self.exe),
            "alive": self.alive,
            "options": dict(self.options),
            "timeout": self.timeout,
        }

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()


# ---------------------------------------------------------------------- 缓存
_cache = OrderedDict()  # key -> OcrEngine
_cache_lock = threading.Lock()


def _options_key(options: dict) -> str:
    return json.dumps(options, sort_keys=True, ensure_ascii=False)


def get_engine(options: dict = None, engine_dir=None) -> OcrEngine:
    """获取（或创建）与参数匹配的引擎实例，LRU 缓存复用。

    相同参数的调用共享同一常驻引擎；超出上限时关闭最久未用的实例。
    """
    ed = Path(engine_dir) if engine_dir else default_engine_dir()
    norm = normalize_options(options, ed)
    key = _options_key(norm)
    with _cache_lock:
        eng = _cache.get(key)
        if eng is not None and not eng.alive:
            eng = None  # 崩溃的实例丢弃重建
        if eng is None:
            eng = OcrEngine(engine_dir=ed, options=norm)
            _cache[key] = eng
        _cache.move_to_end(key)
        while len(_cache) > MAX_CACHED_ENGINES:
            _, old = _cache.popitem(last=False)
            old.stop()
    return eng


def clear_engines():
    """关闭并清空所有缓存引擎（测试/退出用）。"""
    with _cache_lock:
        for eng in _cache.values():
            eng.stop()
        _cache.clear()


def list_languages(engine_dir=None) -> dict:
    """返回可用语言清单 {"languages": [...], "current": ...}"""
    ed = Path(engine_dir) if engine_dir else default_engine_dir()
    d = get_language_dict(ed)
    return {"languages": list(d.keys()), "default": DEFAULT_LANGUAGE}
