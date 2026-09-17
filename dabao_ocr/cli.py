# -*- coding: utf-8 -*-
"""Dabao-OCR 命令行接口

面向 agent / 脚本的最小可用入口：
    dabao-ocr ocr image.png                # 输出纯文本
    dabao-ocr ocr image.png --json         # 输出完整结构
    dabao-ocr batch a.png b/ -o out/       # 批量
    dabao-ocr pdf doc.pdf --layered out.pdf
    dabao-ocr serve --port 18224           # 常驻 HTTP 服务
    dabao-ocr info                         # 环境信息
"""

import argparse
import json
import sys
from pathlib import Path

from ._version import __version__
from .engine import clear_engines, default_engine_dir, get_engine
from .ocr import IMAGE_SUFFIXES, recognize
from .result import OcrResult


def _force_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _add_common_ocr_args(p: argparse.ArgumentParser):
    p.add_argument("--language", default="简体中文", help="语言/模型库（默认 简体中文）")
    p.add_argument("--parser", default="multi_para",
                   help="排版解析方案：multi_para/multi_line/multi_none/single_para/"
                        "single_line/single_none/single_code/none")
    p.add_argument("--angle", action="store_true", help="启用文本方向纠正（慢一些）")
    p.add_argument("--max-side", type=int, default=1024, dest="max_side",
                   help="图像长边压缩上限（默认 1024，越小越快）")
    p.add_argument("--ignore-area", default=None,
                   help='忽略区域 JSON，如 "[[[0,0],[100,50]]]"')


def _parse_ignore_area(s):
    if not s:
        return None
    try:
        val = json.loads(s)
    except json.JSONDecodeError as e:
        raise SystemExit(f"--ignore-area 不是合法 JSON：{e}")
    if not isinstance(val, list):
        raise SystemExit("--ignore-area 必须是数组")
    return val


def _recognize_source(src: str, args) -> OcrResult:
    if src == "-":
        data = sys.stdin.buffer.read()
        return recognize(data, language=args.language, angle=args.angle,
                         max_side_len=args.max_side, parser=args.parser,
                         ignore_area=_parse_ignore_area(args.ignore_area))
    return recognize(src, language=args.language, angle=args.angle,
                     max_side_len=args.max_side, parser=args.parser,
                     ignore_area=_parse_ignore_area(args.ignore_area))


# ------------------------------------------------------------------ ocr
def cmd_ocr(args):
    result = _recognize_source(args.file, args)
    if args.json or args.format == "json":
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        text = result.text
        if text:
            print(text)
    if args.output:
        from .exporters import write_text_file, write_json_file, write_jsonl_file

        out = Path(args.output)
        if args.format == "json":
            write_json_file(out, result.to_dict())
        elif args.format == "jsonl":
            write_jsonl_file(out, [result.to_dict()])
        else:
            write_text_file(out, result.text)
    if not (result.ok or result.empty):
        print(f"[Error] code={result.code}: {result.error}", file=sys.stderr)
        return 2
    return 0


# ------------------------------------------------------------------ batch
def _collect_images(inputs) -> list:
    files = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES:
                    files.append(f)
        elif p.is_file():
            files.append(p)
        else:
            print(f"[Warning] 跳过不存在的路径：{item}", file=sys.stderr)
    return files


def cmd_batch(args):
    files = _collect_images(args.inputs)
    if not files:
        print("[Error] 没有找到可识别的图片。", file=sys.stderr)
        return 2
    results = []
    for f in files:
        r = recognize(f, language=args.language, angle=args.angle,
                      max_side_len=args.max_side, parser=args.parser)
        results.append({"name": f.name, "path": str(f), "result": r})
        if args.verbose:
            status = "OK" if r.ok else ("EMPTY" if r.empty else f"ERR{r.code}")
            print(f"[{status}] {f}", file=sys.stderr)

    if args.out_dir:
        from .exporters import export

        base = args.name or "dabao_ocr"
        export(results, args.out_dir, base, args.format, start_datetime=args.start)
        print(f"已输出 {len(results)} 项到 {args.out_dir}（格式 {args.format}）")
    else:
        for r in results:
            rec = {"path": r["path"], "code": r["result"].code,
                   "text": r["result"].text if r["result"].ok else r["result"].error}
            print(json.dumps(rec, ensure_ascii=False))
    return 0


# ------------------------------------------------------------------ pdf
def cmd_pdf(args):
    try:
        from .pdf import build_layered_pdf, ocr_pdf, pdf_results_to_text
    except ImportError as e:
        print(f"[Error] {e}", file=sys.stderr)
        return 2
    try:
        results = ocr_pdf(
            args.file,
            dpi=args.dpi,
            pages=args.pages,
            password=args.password,
            language=args.language,
            angle=args.angle,
            max_side_len=args.max_side,
            parser=args.parser,
        )
    except Exception as e:
        print(f"[Error] PDF 处理失败：{e}", file=sys.stderr)
        return 2

    if args.jsonl:
        for pr in results:
            print(json.dumps({"page": pr.pno, "code": pr.result.code,
                              "text": pr.text}, ensure_ascii=False))
    else:
        text = pdf_results_to_text(results)
        if args.output:
            from .exporters import write_text_file

            write_text_file(args.output, text)
            print(f"已写入 {args.output}（{len(results)} 页）", file=sys.stderr)
        else:
            print(text)
    if args.layered:
        pages_blocks = {
            pr.pno - 1: [tb for tb in pr.result.blocks]
            for pr in results
            if pr.result.ok
        }
        build_layered_pdf(args.file, args.layered, pages_blocks, password=args.password)
        print(f"双层 PDF 已生成：{args.layered}", file=sys.stderr)
    return 0


# ------------------------------------------------------------------ serve
def cmd_serve(args):
    from .server import find_free_port, serve

    port = args.port
    if args.port_auto:
        free = find_free_port(args.host, args.port)
        if free != args.port:
            print(f"[i] 端口 {args.port} 被占用，改用 {free}", file=sys.stderr)
        port = free
    try:
        serve(args.host, port, engine_dir=None, blocking=True)
    except OSError as e:
        print(f"[Error] 无法监听 {args.host}:{port} — {e}", file=sys.stderr)
        return 2
    return 0


# ------------------------------------------------------------------ info
def cmd_info(args):
    try:
        edir = default_engine_dir()
        exe_ok = (edir / "RapidOCR-json.exe").exists()
    except FileNotFoundError as e:
        edir, exe_ok = str(e), False
    from .engine import list_languages

    try:
        langs = list_languages()
    except Exception as e:
        langs = {"error": str(e)}
    info = {
        "name": "Dabao-OCR",
        "version": __version__,
        "python": sys.version.split()[0],
        "engine_dir": str(edir),
        "engine_exe_ok": exe_ok,
        "languages": langs,
    }
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


# ------------------------------------------------------------------ main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dabao-ocr",
        description="Dabao-OCR — 离线图片/PDF 文字识别（Umi-OCR 后端衍生的 agent 友好 CLI）",
    )
    p.add_argument("-V", "--version", action="version", version=f"Dabao-OCR {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_ocr = sub.add_parser("ocr", help="识别单张图片（路径或 - 从 stdin 读字节）")
    p_ocr.add_argument("file", help="图片路径，或 - 表示从 stdin 读取")
    p_ocr.add_argument("--json", action="store_true", help="输出完整 JSON（含 box/score）")
    p_ocr.add_argument("--format", choices=["text", "json", "jsonl"], default="text",
                       help="输出格式（默认 text）")
    p_ocr.add_argument("-o", "--output", help="写入文件")
    _add_common_ocr_args(p_ocr)
    p_ocr.set_defaults(func=cmd_ocr)

    p_batch = sub.add_parser("batch", help="批量识别图片/目录")
    p_batch.add_argument("inputs", nargs="+", help="图片或目录（可多个）")
    p_batch.add_argument("-o", "--out-dir", dest="out_dir", help="输出目录（缺省输出到 stdout 的 jsonl）")
    p_batch.add_argument("--name", help="输出文件名前缀")
    p_batch.add_argument("--start", default="", help="输出文件头时间戳（md 用）")
    p_batch.add_argument("--format", choices=["txt", "json", "jsonl", "md", "csv"],
                         default="jsonl", help="导出格式（配合 --out-dir）")
    p_batch.add_argument("-v", "--verbose", action="store_true")
    _add_common_ocr_args(p_batch)
    p_batch.set_defaults(func=cmd_batch)

    p_pdf = sub.add_parser("pdf", help="识别 PDF（可生成双层可搜索 PDF）")
    p_pdf.add_argument("file", help="PDF 路径")
    p_pdf.add_argument("--dpi", type=int, default=200, help="页面渲染 DPI（默认 200）")
    p_pdf.add_argument("--pages", help='页范围，如 "1-3,5"（默认全部）')
    p_pdf.add_argument("--password", help="PDF 密码")
    p_pdf.add_argument("--layered", help="输出双层（可搜索）PDF 的路径")
    p_pdf.add_argument("--jsonl", action="store_true", help="按页输出 jsonl")
    p_pdf.add_argument("-o", "--output", help="文本写入文件")
    _add_common_ocr_args(p_pdf)
    p_pdf.set_defaults(func=cmd_pdf)

    p_serve = sub.add_parser("serve", help="启动 HTTP API 服务")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=18224)
    p_serve.add_argument("--port-auto", action="store_true", help="端口被占用时自动+1 探测")
    p_serve.set_defaults(func=cmd_serve)

    p_info = sub.add_parser("info", help="显示引擎与语言信息")
    p_info.set_defaults(func=cmd_info)
    return p


def main(argv=None) -> int:
    _force_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        return 130
    finally:
        clear_engines()


if __name__ == "__main__":
    raise SystemExit(main())
