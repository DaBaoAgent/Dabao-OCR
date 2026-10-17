# tbpu : text block processing unit 文本块后处理

from ..log import logger
from .parser_none import ParserNone

from .ignore_area import IgnoreArea
from .parser_multi_para import MultiPara
from .parser_multi_line import MultiLine
from .parser_multi_none import MultiNone
from .parser_single_para import SinglePara, SingleParaFixed
from .parser_single_line import SingleLine, SingleLineFixed
from .parser_single_none import SingleNone, SingleNoneFixed
from .parser_single_code import SingleCode, SingleCodeFixed

# 排版解析
Parser = {
    "none": ParserNone,  # 不做处理
    "multi_para": MultiPara,  # 多栏-自然段
    "multi_line": MultiLine,  # 多栏-总是换行
    "multi_none": MultiNone,  # 多栏-无换行
    "single_para": SinglePara,  # 单栏-自然段
    "single_line": SingleLine,  # 单栏-总是换行
    "single_none": SingleNone,  # 单栏-无换行
    "single_code": SingleCode,  # 单栏-代码段
    # 修正版：仅修正原版 single_* 的两处计算缺陷，其余行为完全一致。
    # 保留原 8 种是为了与 Umi-OCR 逐块一致，修正版供需要正确间距/包围盒的场景使用。
    "single_para_fixed": SingleParaFixed,
    "single_line_fixed": SingleLineFixed,
    "single_none_fixed": SingleNoneFixed,
    "single_code_fixed": SingleCodeFixed,
}

# 合法方案名（供 CLI / HTTP 校验，避免拼错时静默降级）
PARSER_KEYS = tuple(Parser)


# 获取排版解析器对象
def getParser(key):
    if key in Parser:
        return Parser[key]()
    logger.warning("未知排版解析方案 %r，已回退为 none（可用：%s）", key, list(PARSER_KEYS))
    return Parser["none"]()
