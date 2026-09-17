# 剥离与重写记录（相对 Umi-OCR）

本文件记录 Dabao-OCR 的来历：从本机 Umi-OCR 安装复制、剥离 GUI 前端、
保留/移植后端能力、并重写工程化外壳的全过程，便于后续维护与升级对照。

## 源头

- 来源：本机安装的 `Umi-OCR_Rapid_v2.1.5`（Umi-OCR 2.1.5, RapidOCR 引擎版）
- Umi-OCR 仓库：https://github.com/hiroi-sora/Umi-OCR （MIT, © hiroi-sora）
- 引擎：RapidOCR-json v1.1.0（`UmiOCR-data/plugins/win7_x64_RapidOCR-json/`）

## 剥离（移除的部分）

| 原组件 | 说明 |
|---|---|
| `Umi-OCR.exe` + `main.py` | 启动器与入口（PyStand 运行时引导） |
| `py_src/`（前端部分） | Qt/QML 页面、任务连接器、事件总线、i18n 等 |
| `site-packages/PySide2` | Qt 图形界面框架（约 125 MB） |
| `runtime/` | 嵌入式 Python 运行时（16 MB） |
| `qt_res/` `themes.json` `i18n/` | 界面资源与主题 |
| 截图 OCR / 剪贴板 / 系统托盘 | GUI 交互能力 |
| 二维码（qrcode_server）| 依赖 zxing_cpp 的附加功能，未纳入 |

## 保留与移植（后端部分）

| 内容 | 去向 | 处理 |
|---|---|---|
| `RapidOCR-json.exe` + `models/` | `vendor/RapidOCR-json/` | 原样保留（引擎与 ONNX 模型、字典） |
| 引擎管道调用适配层（`rapidocr.py`） | `dabao_ocr/engine.py` | **重写**：线程安全（读线程+队列）、超时保护、崩溃自动重启+重试、LRU 多实例缓存 |
| 排版解析（`py_src/ocr/tbpu/`） | `dabao_ocr/tbpu/` | **源码移植**：仅调整包级 import（`umi_log` → 内部 logger），算法逐行保持 |
| 双层 PDF 写入（`output_pdf_layered.py`） | `dabao_ocr/pdf.py` | **移植+精简**：去掉 GUI 输出器框架，保留字体注入/透明文本/子集化逻辑 |
| 输出器（txt/jsonl/md/csv） | `dabao_ocr/exporters.py` | **重写**：保留格式与编码降级逻辑，去掉文件句柄常驻模型 |
| HTTP API（`ocr_server.py`/`web_server.py`） | `dabao_ocr/server.py` | **重写**：bottle → 标准库 http.server；协议、选项表、错误码逐项对齐 |
| 语言表（`rapidocr_config.py` + i18n） | `dabao_ocr/langs.py` | **重写**：直接从 `models/configs.txt` 解析，去掉 i18n/psutil 依赖 |

## 新增（原版没有的能力）

- `CLI`：`ocr` / `batch` / `pdf` / `serve` / `info` 子命令，stdout 直接可用（agent 友好）
- HTTP 增强端点：`/api/ocr/batch`、`/api/pdf`（同步返回文本/双层）、`/api/status`
- `/api/ocr` 支持 `path` 字段（服务器本机路径直读，免 base64）
- Python 包化（`pip install -e .`），`class OcrResult` 结果模型
- 测试套件：**与原版 tbpu 源码的逐块一致性对比** + **与原版 HTTP 服务的逐字符对比**（金标准）

## 一致性保证

- 识别结果：同引擎、同默认参数（简中 / maxSideLen 1024 / angle off）下与原版**逐字符一致**
  （测试证据：`tests/test_parity_umi.py`，对原版在线服务直接对比）
- 排版解析：8 种方案 × 5 类输入场景与原版**逐块一致**
  （测试证据：`tests/test_tbpu_parity.py`，直接加载原版源码对比）
- HTTP 选项表：与原版 `get_options` 响应**完全一致**（同上测试）

## 升级路径

若未来升级 Umi-OCR / RapidOCR-json 版本：

1. 用新版 `RapidOCR-json.exe` + `models/` 替换 `vendor/RapidOCR-json/`
2. 用新版 `py_src/ocr/tbpu/` 源码覆盖 `dabao_ocr/tbpu/`，只需把
   `from umi_log import logger` 调整为仓库内 logger（其余不动）
3. 对照新版 `ocr_server.py` 刷新 `dabao_ocr/options.py` 的选项表
4. 重跑 `pytest tests`（一致性测试会自动对照新版行为）
