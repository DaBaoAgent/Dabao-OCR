# -*- coding: utf-8 -*-
"""OCR 结果类型与文本拼接"""

from dataclasses import dataclass, field
from typing import List, Union


def data_to_text(blocks: List[dict]) -> str:
    """把文本块列表拼接为纯文本（复刻 Umi-OCR 的 getDataText 行为）。

    每个文本块需含 'text' 与 'end'（排版解析会写入 'end'；
    未经解析的块按换行处理）。
    """
    out = ""
    for i, tb in enumerate(blocks):
        out += tb.get("text", "")
        if i < len(blocks) - 1:
            out += tb.get("end", "\n")
    return out


@dataclass
class OcrResult:
    """一次 OCR 识别的结果。

    - code: RapidOCR-json 返回码（100 成功 / 101 无文字 / 其他为错误）
    - data: 成功时为文本块列表（含 box/score/text，解析后含 end）；失败时为错误信息字符串
    """

    code: int
    data: Union[List[dict], str]

    @property
    def ok(self) -> bool:
        return self.code == 100

    @property
    def empty(self) -> bool:
        """识别成功但未找到文字。"""
        return self.code == 101

    @property
    def blocks(self) -> List[dict]:
        return self.data if isinstance(self.data, list) else []

    @property
    def text(self) -> str:
        """拼接后的纯文本（无文字时为空字符串）。"""
        if self.code == 100:
            return data_to_text(self.data)
        return ""

    @property
    def error(self) -> str:
        return self.data if isinstance(self.data, str) else ""

    def to_dict(self) -> dict:
        return {"code": self.code, "data": self.data}

    def to_text_dict(self) -> dict:
        """data.format=text 风格的字典（兼容 Umi-OCR HTTP API 返回）。"""
        return {"code": self.code, "data": self.text if self.ok else self.data}
