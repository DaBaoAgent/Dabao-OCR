# -*- coding: utf-8 -*-
"""结果导出：txt / json / jsonl / md / csv

行为对齐 Umi-OCR 的对应输出器（txtPlain / jsonl / md / csv），
去掉 GUI 相关部分，保持文件格式兼容。
"""

import csv
import json
import os

from .log import logger
from .result import OcrResult

# CSV 保存编码优先级（复刻 Umi-OCR 逻辑）
_CSV_ENCODINGS = ["ansi", "ascii", "gbk", "big5", "shift_jis", "euc-kr", "utf-8"]


def write_text_file(path, text: str):
    """写纯文本文件（UTF-8）。"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_json_file(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_jsonl_file(path, records: list):
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_md_file(path, sections: list, start_datetime: str = ""):
    """写 Markdown：每个 sections 项 = {"name", "image_rel_path", "text"}。"""
    with open(path, "w", encoding="utf-8") as f:
        if start_datetime:
            f.write(f"> {start_datetime}\n\n")
        for s in sections:
            name = s["name"]
            p = s.get("image_rel_path", "")
            p = p.replace(" ", "%20")
            f.write(f"\n---\n![{name}]({p})\n[{name}]({p})\n\n")
            for line in s.get("text", "").split("\n"):
                f.write(f"> {line}  \n")


def write_csv_file(path, rows: list):
    """写 CSV（表头 Name/OCR/Path；编码按内容自动降级，复刻 Umi-OCR 逻辑）。"""
    all_text = "".join(str(r[1]) for r in rows)
    encoding = "utf-8"
    for e in _CSV_ENCODINGS:
        try:
            all_text.encode(e)
            encoding = e
            break
        except Exception:
            continue
    logger.debug("csv encoding: %s", encoding)
    with open(path, "w", encoding=encoding, newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "OCR", "Path"])
        for row in rows:
            writer.writerow(row)


def result_to_record(name: str, result: OcrResult, path: str = "") -> dict:
    """把 OcrResult 转为 jsonl 记录（兼容 Umi-OCR jsonl 输出结构）。"""
    rec = {"code": result.code, "data": result.data, "fileName": name, "path": path}
    return rec


def export(
    results: list,
    out_dir: str,
    base_name: str,
    fmt: str,
    start_datetime: str = "",
):
    """批量导出。results = [{"name", "path", "result": OcrResult}]。

    fmt: txt | json | jsonl | md | csv
    """
    os.makedirs(out_dir, exist_ok=True)
    if fmt == "txt":
        text = ""
        for r in results:
            t = r["result"].text
            if t and not t.endswith("\n"):
                t += "\n"
            text += t
        write_text_file(os.path.join(out_dir, base_name + ".txt"), text)
    elif fmt == "json":
        write_json_file(
            os.path.join(out_dir, base_name + ".json"),
            [result_to_record(r["name"], r["result"], r["path"]) for r in results],
        )
    elif fmt == "jsonl":
        write_jsonl_file(
            os.path.join(out_dir, base_name + ".jsonl"),
            [result_to_record(r["name"], r["result"], r["path"]) for r in results],
        )
    elif fmt == "md":
        sections = []
        for r in results:
            if r["path"]:
                try:
                    rel = os.path.relpath(r["path"], out_dir)
                except ValueError:
                    # Windows 跨盘符等场景无法计算相对路径，退化为绝对路径
                    rel = str(r["path"]).replace("\\", "/")
            else:
                rel = r["name"]
            sections.append(
                {"name": r["name"], "image_rel_path": rel, "text": r["result"].text}
            )
        write_md_file(os.path.join(out_dir, base_name + ".md"), sections, start_datetime)
    elif fmt == "csv":
        rows = []
        for r in results:
            res = r["result"]
            if res.ok:
                text = res.text
            elif res.code == 101:
                text = ""
            else:
                text = f'[Error] OCR failed. Code: {res.code}, Msg: {res.data} .\n'
            rows.append([r["name"], text, r["path"]])
        write_csv_file(os.path.join(out_dir, base_name + ".csv"), rows)
    else:
        raise ValueError(f"不支持的导出格式：{fmt}")
