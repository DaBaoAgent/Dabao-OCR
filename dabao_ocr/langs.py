# -*- coding: utf-8 -*-
"""语言 / 模型库管理

从引擎的 models/configs.txt 动态解析可用语言列表，
替代 Umi-OCR 原版中依赖 i18n 与插件的实现。
"""

from pathlib import Path

DEFAULT_LANGUAGE = "简体中文"

# configs.txt 格式（每块 5 行，块间空行分隔）：
#   语言名
#   det 模型文件名
#   cls 模型文件名
#   rec 模型文件名
#   keys 字典文件名
_CONFIG_NAME = "models/configs.txt"


class LanguageError(ValueError):
    """语言/模型库解析错误"""


def _engine_dir_or_default(engine_dir):
    """None/空值时回退到默认引擎目录（延迟导入避免循环依赖）。"""
    if not engine_dir:
        from .engine import default_engine_dir

        return default_engine_dir()
    return Path(engine_dir)


def get_language_dict(engine_dir=None) -> dict:
    """解析 configs.txt，返回 {语言名: {det, cls, rec, keys}}。"""
    path = _engine_dir_or_default(engine_dir) / _CONFIG_NAME
    result = {}
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        raise LanguageError(f"无法读取模型配置 {path}: {e}") from e
    for part in content.split("\n\n"):
        items = [x.strip() for x in part.strip().split("\n") if x.strip()]
        if len(items) == 5:
            title, det, cls, rec, keys = items
            result[title] = {"det": det, "cls": cls, "rec": rec, "keys": keys}
    return result


def get_language_list(engine_dir=None) -> list:
    """返回可用语言名列表（保持 configs.txt 中的顺序）。"""
    return list(get_language_dict(engine_dir).keys())


def resolve_language(name: str, engine_dir=None) -> dict:
    """把语言名解析为 {det, cls, rec, keys} 模型文件字典。"""
    langs = get_language_dict(engine_dir)
    if name in langs:
        return langs[name]
    if not langs:
        raise LanguageError(f"模型配置为空：{Path(engine_dir) / _CONFIG_NAME}")
    fallback = DEFAULT_LANGUAGE if DEFAULT_LANGUAGE in langs else next(iter(langs))
    raise LanguageError(
        f"未知语言/模型库：{name!r}；可用：{list(langs)}（如未配置请使用默认 {fallback!r}）"
    )
