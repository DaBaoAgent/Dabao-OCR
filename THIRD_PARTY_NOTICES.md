# 第三方组件声明（THIRD_PARTY NOTICES）

Dabao-OCR 是 [Umi-OCR](https://github.com/hiroi-sora/Umi-OCR) 后端能力的**剥离与工程化产物**。
以下第三方组件/代码被包含或移植进本项目：

## 1. Umi-OCR（嵌入 & 移植）

- 项目：https://github.com/hiroi-sora/Umi-OCR
- 作者：hiroi-sora
- 许可：MIT License
- 涉及内容：
  - `dabao_ocr/tbpu/` — 排版解析模块（text block processing unit）的**源码移植**
    （parser_*.py / parser_tools/ / ignore_area.py 等，仅做包级 import 调整）
  - `dabao_ocr/pdf.py` 中双层 PDF 写入逻辑（移植自 `output_pdf_layered`）
  - `dabao_ocr/engine.py` 引擎管道调用设计（参考其 RapidOCR-json 适配层，重写为线程安全实现）
  - HTTP API 协议设计（`/api/ocr`、`/api/ocr/get_options` 的请求/响应结构）

## 2. RapidOCR-json（嵌入二进制 & 模型）

- 项目：https://github.com/hiroi-sora/RapidOCR-json
- 作者：hiroi-sora
- 许可：MIT License
- 涉及内容：`vendor/RapidOCR-json/`（引擎 exe v1.1.0 + ONNX 模型库 + 字典）

## 3. GapTree_Sort_Algorithm（移植）

- 项目：https://github.com/hiroi-sora/GapTree_Sort_Algorithm
- 作者：hiroi-sora
- 许可：MIT License
- 涉及内容：`dabao_ocr/tbpu/parser_tools/gap_tree.py`（版面阅读顺序排序算法）

## 4. PyMuPDF（可选运行依赖，未随本项目分发）

- 项目：https://github.com/pymupdf/PyMuPDF
- 许可：AGPL-3.0（或商业许可）
- 说明：仅当使用 PDF 功能时由使用者自行 `pip install PyMuPDF`；本项目代码只调用其公开 API，不包含其源码。若在闭源商业环境使用 PDF 功能，请自行评估 PyMuPDF 的 AGPL 合规性（或购买其商业许可）。

---

以上 MIT 组件均保留了原始版权声明；本仓库根目录 `LICENSE` 中附有其完整声明。
