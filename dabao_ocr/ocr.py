# -*- coding: utf-8 -*-
"""Dabao-OCR 高层 OCR API

对图片（路径 / 字节 / base64）执行识别 + 排版解析（tbpu），
产出与 Umi-OCR 一致的文本块结构。
"""

from pathlib import Path
from typing import List, Union

from .engine import OcrEngine, get_engine
from .log import logger
from .result import OcrResult
from .service import try_ocr
from .tbpu import IgnoreArea, getParser

# 可供识别的图片后缀（复刻 Umi-OCR 清单）
IMAGE_SUFFIXES = (
    ".jpg", ".jpe", ".jpeg", ".jfif",
    ".png", ".webp", ".bmp",
    ".tif", ".tiff",
)

DEFAULT_PARSER = "multi_para"


def convert_ignore_area(ignore_area) -> list:
    """把 HTTP/用户格式的忽略区域 [[[x1,y1],[x2,y2]], ...] 转为 tbpu 内部格式。"""
    out = []
    for a in ignore_area or []:
        out.append([[a[0][0], a[0][1]], [], [a[1][0], a[1][1]], []])
    return out


def _postprocess(blocks: List[dict], parser: str = None, ignore_area=None) -> List[dict]:
    """对识别出的文本块执行忽略区域过滤 + 排版解析（与 Umi-OCR 相同顺序）。"""
    stages = []
    if ignore_area:
        stages.append(IgnoreArea(convert_ignore_area(ignore_area)))
    if parser:
        stages.append(getParser(parser))
    for stage in stages:
        blocks = stage.run(blocks)
    return blocks


def _service_options(language, angle, max_side_len, parser, ignore_area) -> dict:
    """把 recognize 的参数翻译成 HTTP 选项表的键。"""
    opts = {
        "ocr.language": language,
        "ocr.angle": bool(angle),
        "ocr.maxSideLen": max_side_len,
        "tbpu.parser": parser,
        "data.format": "dict",
    }
    if ignore_area:
        opts["tbpu.ignoreArea"] = ignore_area
    return opts


def _recognize_via_service(source, options, timeout):
    """走常驻服务的快通道。服务不可用时返回 None（调用方回落本地引擎）。"""
    if isinstance(source, bytes):
        res = try_ocr(image_bytes=source, options=options, timeout=timeout)
    else:
        p = Path(source).resolve()
        if not p.is_file():
            return OcrResult(901, f"图片文件不存在：{p}")
        res = try_ocr(path=p, options=options, timeout=timeout)
    if res is None:
        return None
    # 服务端已完成 tbpu 排版解析，结果可直接使用（不要再解析一遍）
    return OcrResult(res.get("code", 999), res.get("data", ""))


def recognize(
    source: Union[str, Path, bytes],
    *,
    language: str = "简体中文",
    angle: bool = False,
    max_side_len: int = 1024,
    num_thread: int = None,
    parser: str = DEFAULT_PARSER,
    ignore_area=None,
    engine: OcrEngine = None,
    engine_dir=None,
    timeout: float = None,
    use_service: bool = False,
) -> OcrResult:
    """识别一张图片。

    :param source: 图片路径（str/Path）或图片字节（bytes）
    :param language: 语言/模型库名（见 langs / models/configs.txt）
    :param angle: 是否启用方向分类（纠正倾斜/倒置文本，稍慢）
    :param max_side_len: 图像长边压缩上限（默认 1024，越大越准越慢）
    :param num_thread: 引擎线程数（默认按 CPU 核心数）
    :param parser: 排版解析方案（none/multi_para/multi_line/... 共 8 种）
    :param ignore_area: 忽略区域 [[[x1,y1],[x2,y2]], ...]（像素坐标）
    :param engine: 直接指定引擎实例（复用/测试用，优先级最高）
    :param use_service: 优先复用本机常驻 HTTP 服务（省掉引擎冷启动）；
                        服务不可用时自动回落本地引擎
    """
    if use_service and engine is None and engine_dir is None:
        opts = _service_options(language, angle, max_side_len, parser, ignore_area)
        fast = _recognize_via_service(source, opts, timeout)
        if fast is not None:
            return fast

    eng = engine or get_engine(
        {
            "language": language,
            "angle": angle,
            "maxSideLen": max_side_len,
            "numThread": num_thread,
        },
        engine_dir,
    )
    if isinstance(source, bytes):
        res = eng.run_bytes(source)
    else:
        # 绝对化：引擎子进程的 cwd 在引擎目录，相对路径会解析错误
        p = Path(source).resolve()
        if not p.is_file():
            return OcrResult(901, f"图片文件不存在：{p}")
        res = eng.run_path(p)
    return _finish(res, parser, ignore_area)


def recognize_base64(
    image_base64: str,
    *,
    parser: str = DEFAULT_PARSER,
    ignore_area=None,
    engine: OcrEngine = None,
    use_service: bool = False,
    **engine_opts,
) -> OcrResult:
    """识别一张 base64 编码的图片（engine_opts 同 recognize）。"""
    engine_dir = engine_opts.pop("engine_dir", None)
    if use_service and engine is None and engine_dir is None:
        opts = _service_options(
            engine_opts.get("language", "简体中文"),
            engine_opts.get("angle", False),
            engine_opts.get("max_side_len", 1024),
            parser,
            ignore_area,
        )
        res = try_ocr(image_base64=image_base64, options=opts)
        if res is not None:
            return OcrResult(res.get("code", 999), res.get("data", ""))
    eng = engine or get_engine(engine_opts, engine_dir)
    res = eng.run_base64(image_base64)
    return _finish(res, parser, ignore_area)


def recognize_file(
    path: Union[str, Path],
    **kwargs,
) -> OcrResult:
    """recognize 的别名，语义更直白。"""
    return recognize(path, **kwargs)


def _finish(res: dict, parser, ignore_area) -> OcrResult:
    code = res.get("code", 999)
    data = res.get("data", "")
    if code == 100:
        try:
            data = _postprocess(data, parser, ignore_area)
        except Exception:
            logger.exception("排版解析失败，返回未解析结果")
    return OcrResult(code, data)
