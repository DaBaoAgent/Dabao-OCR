# 排版解析-单栏-自然段

from .parser_single_line import SingleLine
from .parser_tools.line_preprocessing import linePreprocessing  # 行预处理
from .parser_tools.paragraph_parse import ParagraphParse  # 段内分析器


class SinglePara(SingleLine):
    # 是否修正行包围盒的合并。原版在合并时用刚被更新的 b1 去算 b2/b3，
    # 导致右/下边界偏小。默认沿用原逻辑以保持一致性；修正版见 SingleParaFixed。
    FIX_LINE_BBOX = False

    def __init__(self):
        self.tbpuName = "排版解析-单栏-自然段"

        # 段内分析器对象
        get_info = lambda tb: (tb["normalized_bbox"], tb["text"])

        def set_end(tb, end):  # 获取预测的块尾分隔符
            tb["line"][-1]["end"] = end

        self.pp = ParagraphParse(get_info, set_end)

    def run(self, textBlocks):
        textBlocks = linePreprocessing(textBlocks)  # 预处理
        lines = self.get_lines(textBlocks)  # 获取每一行
        # 将行封装为tb
        temp_tbs = []
        for line in lines:
            b0, b1, b2, b3 = line[0]["normalized_bbox"]
            # 搜索bbox
            for i in range(1, len(line)):
                bb = line[i]["normalized_bbox"]
                b1 = min(b1, bb[1])
                if self.FIX_LINE_BBOX:
                    b2 = max(b2, bb[2])
                    b3 = max(b3, bb[3])
                else:
                    # 原版公式（缺陷）：b2/b3 用了刚更新的 b1
                    b2 = max(b1, bb[2])
                    b3 = max(b1, bb[3])
            # 构建tb
            temp_tbs.append(
                {
                    "normalized_bbox": (b0, b1, b2, b3),
                    "text": line[0]["text"][0] + line[-1]["text"][-1],
                    "line": line,
                }
            )
        # 预测结尾分隔符
        self.pp.run(temp_tbs)
        # 解包
        textBlocks = []
        for t in temp_tbs:
            for tb in t["line"]:
                del tb["normalized_bbox"]
                textBlocks.append(tb)
        return textBlocks


class SingleParaFixed(SinglePara):
    """单栏-自然段（修正版）：同时修正行高公式与行包围盒合并。"""

    FIX_LINE_HEIGHT = True
    FIX_LINE_BBOX = True

    def __init__(self):
        super().__init__()
        self.tbpuName = "排版解析-单栏-自然段（修正）"
