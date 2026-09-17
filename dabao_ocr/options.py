# -*- coding: utf-8 -*-
"""HTTP API 选项表：与 Umi-OCR /api/ocr/get_options 完全兼容的结构。

包含 6 个键：
    ocr.language / ocr.angle / ocr.maxSideLen / tbpu.parser / tbpu.ignoreArea / data.format
"""

from .engine import default_engine_dir
from .langs import DEFAULT_LANGUAGE, get_language_list
from .log import logger

# 排版解析方案（与 Umi-OCR 相同）
PARSER_OPTIONS = [
    ["multi_para", "多栏-按自然段换行"],
    ["multi_line", "多栏-总是换行"],
    ["multi_none", "多栏-无换行"],
    ["single_para", "单栏-按自然段换行"],
    ["single_line", "单栏-总是换行"],
    ["single_none", "单栏-无换行"],
    ["single_code", "单栏-保留缩进"],
    ["none", "不做处理"],
]

MAX_SIDE_OPTIONS = [
    [1024, "1024 （默认）"],
    [2048, "2048"],
    [4096, "4096"],
    [999999, "无限制"],
]


def get_options(engine_dir=None) -> dict:
    """构建完整选项表（结构、文案与 Umi-OCR 一致）。"""
    ed = engine_dir or default_engine_dir()
    langs = get_language_list(ed)
    lang_opts = [[x, x] for x in langs]
    return {
        "ocr.language": {
            "title": "语言/模型库",
            "optionsList": lang_opts,
            "type": "enum",
            "default": DEFAULT_LANGUAGE,
            "advanced": False,
        },
        "ocr.angle": {
            "title": "纠正文本方向",
            "default": False,
            "toolTip": "启用方向分类，识别倾斜或倒置的文本。可能降低识别速度。",
            "type": "boolean",
            "advanced": False,
        },
        "ocr.maxSideLen": {
            "title": "限制图像边长",
            "optionsList": MAX_SIDE_OPTIONS,
            "toolTip": "将边长大于该值的图片进行压缩，可以提高识别速度。可能降低识别精度。",
            "type": "enum",
            "default": 1024,
            "advanced": False,
        },
        "tbpu.parser": {
            "title": "排版解析方案",
            "toolTip": "按什么方式，解析和排序图片中的文字块",
            "default": "multi_para",
            "optionsList": PARSER_OPTIONS,
            "type": "enum",
            "advanced": False,
        },
        "tbpu.ignoreArea": {
            "title": "忽略区域",
            "toolTip": "数组，每一项为[[左上角x,y],[右下角x,y]]。",
            "default": [],
            "type": "var",
            "advanced": False,
        },
        "data.format": {
            "title": "数据返回格式",
            "toolTip": '返回值字典中，["data"] 按什么格式表示OCR结果数据',
            "default": "dict",
            "optionsList": [
                ["dict", "含有位置等信息的原始字典"],
                ["text", "纯文本"],
            ],
            "type": "enum",
            "advanced": False,
        },
    }


def fill_defaults(options: dict, engine_dir=None) -> dict:
    """补全缺失的默认参数（返回新字典）。"""
    opt = dict(options or {})
    defaults = get_options(engine_dir)
    for key, meta in defaults.items():
        if key not in opt:
            opt[key] = meta["default"]
    return opt


def validate_options(options: dict, engine_dir=None):
    """校验选项（复刻 Umi-OCR 的检查，含错误消息）。抛 ValueError。"""
    ia = options.get("tbpu.ignoreArea")
    if ia:
        if not isinstance(ia, list):
            raise ValueError("tbpu.ignoreArea 必须为数组。")
        for a in ia:
            ok = (
                isinstance(a, list)
                and len(a) == 2
                and isinstance(a[0], list)
                and len(a[0]) == 2
                and isinstance(a[1], list)
                and len(a[1]) == 2
                and all(isinstance(x, (int, float)) for x in [a[0][0], a[0][1], a[1][0], a[1][1]])
            )
            if not ok:
                raise ValueError(
                    f"tbpu.ignoreArea 中，每一项的格式必须是 [[x1,y1],[x2,y2]] 。当前值不合法： {ia}"
                )
    msl = options.get("ocr.maxSideLen", 1024)
    try:
        int(msl)
    except (TypeError, ValueError):
        raise ValueError(f"ocr.maxSideLen 必须为整数。当前值不合法：{msl!r}")
    lang = options.get("ocr.language", DEFAULT_LANGUAGE)
    try:
        known = get_language_list(engine_dir)
    except Exception:
        known = None
        logger.debug("无法读取语言列表，跳过语言校验。")
    if known is not None and lang not in known:
        raise ValueError(
            f"未知语言/模型库：{lang!r}；可用：{known}"
        )
    return options
