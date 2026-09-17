# Dabao-OCR

> 离线 OCR 后端 —— 从 [Umi-OCR](https://github.com/hiroi-sora/Umi-OCR) 剥离 GUI 前端后，
> 面向 **agent / 脚本 / 服务** 的纯后端工具包。

Dabao-OCR 与 Umi-OCR 使用**同一套识别引擎（RapidOCR-json）与同一套排版解析算法**，
因此识别结果与原版逐字符一致（见「一致性验证」），但去掉了整个 Qt 图形界面，
改为三种更适合自动化的使用形态：**CLI 命令行**、**HTTP API（Umi-OCR 协议兼容）**、**Python 库**。

## 特性

- 🔌 **完全离线**：识别过程零网络依赖（引擎与模型全部内置在 `vendor/`）
- 🈶 **6 种语言模型**：简体中文 / English / 繁體中文 / 日本語 / 한국어 / Русский
- 📐 **8 种排版解析**：多栏/单栏 × 自然段/换行/无换行/代码缩进（Umi-OCR 同款算法）
- 📄 **PDF 支持**：逐页识别、页范围选取、生成**双层可搜索 PDF**
- 🌐 **HTTP API**：兼容原版 Umi-OCR 的 `/api/ocr` 协议（现有客户端可无缝迁移）；
  另提供 `batch` / `pdf` / `status` 增强端点
- 🧰 **零基础依赖**：核心仅用 Python 标准库；PDF 功能为可选依赖（PyMuPDF）
- ✅ **135+ 项自动化测试**：含与原版 Umi-OCR 的逐字符一致性测试

## 快速开始

要求：Windows x64、Python ≥ 3.9（仓库自带引擎与模型）。

```bash
# 1. 准备虚拟环境（可选但推荐）
uv venv .venv
uv pip install --python .venv/Scripts/python.exe -e .        # 核心（零依赖）
uv pip install --python .venv/Scripts/python.exe -e ".[pdf]" # 含 PDF 功能

# 2. 直接使用 CLI
.venv/Scripts/dabao-ocr ocr  图片.png                # 输出纯文本
.venv/Scripts/dabao-ocr ocr  图片.png --json         # 完整结构（含坐标/置信度）
.venv/Scripts/dabao-ocr info                         # 引擎/语言信息
```

> 未安装包时也可直接 `python -m dabao_ocr ...`（在仓库根目录下运行）。

### CLI 速查

```bash
# 单图识别
dabao-ocr ocr photo.png                          # → 纯文本
dabao-ocr ocr photo.png --json                   # → {code, data:[{box,score,text,end}]}
dabao-ocr ocr photo.png --parser single_line     # 换排版方案
dabao-ocr ocr photo.png --language English       # 换语言
dabao-ocr ocr -  < photo.png                     # 从 stdin 读图片字节
dabao-ocr ocr photo.png -o out.txt               # 写文件

# 批量（支持目录递归）
dabao-ocr batch 图片目录/ -o out/ --format jsonl  # 导出 txt/json/jsonl/md/csv
dabao-ocr batch a.png b.png                       # 直接输出 jsonl 到 stdout

# PDF
dabao-ocr pdf doc.pdf                             # 全页识别 → 文本
dabao-ocr pdf doc.pdf --pages 1-5 --dpi 200
dabao-ocr pdf doc.pdf --layered out.pdf           # 生成双层（可搜索）PDF

# 常驻 HTTP 服务（默认 127.0.0.1:18224）
dabao-ocr serve --port 18224
```

### HTTP API

```bash
dabao-ocr serve &

# ① 识别（Umi-OCR 兼容协议；本实现额外支持 path 代替 base64）
curl -s http://127.0.0.1:18224/api/ocr -X POST \
  -H "Content-Type: application/json" \
  -d '{"path": "D:/photos/a.png", "options": {"data.format": "text"}}'
# → {"code":100, "data":"识别出的文本…"}

# ② 选项表（与 Umi-OCR /api/ocr/get_options 一致）
curl -s http://127.0.0.1:18224/api/ocr/get_options

# ③ 批量
curl -s http://127.0.0.1:18224/api/ocr/batch -X POST \
  -H "Content-Type: application/json" \
  -d '{"images": [{"path": "a.png"}, {"path": "b.png"}], "options": {"data.format": "text"}}'

# ④ PDF → 每页文本
curl -s http://127.0.0.1:18224/api/pdf -X POST \
  -H "Content-Type: application/json" \
  -d '{"path": "D:/docs/a.pdf", "options": {"pages": "1-10"}}'

# ⑤ 健康检查
curl -s http://127.0.0.1:18224/api/status
```

请求/响应约定（与 Umi-OCR 原版一致）：

| 要素 | 说明 |
|---|---|
| `options` 键 | `ocr.language` / `ocr.angle` / `ocr.maxSideLen` / `tbpu.parser` / `tbpu.ignoreArea` / `data.format` |
| `code` | `100` 成功、`101` 无文字、`8xx` 请求错误（800 解析/801 空/802 缺输入/803 options 非法/804 options 解释失败）、`9xx` 运行错误 |
| `data` | `data.format=dict` 时为文本块数组；`=text` 时为纯文本字符串 |

### Python 库

```python
from dabao_ocr import recognize

r = recognize("photo.png")                 # 简中 + 多栏自然段解析（默认）
print(r.text)                              # 拼接后的纯文本
for blk in r.blocks:                       # {'box': [[x,y]*4], 'score': .., 'text': .., 'end': ..}
    print(blk["score"], blk["text"])

r = recognize(b"...image bytes...", language="English", parser="single_line")
r = recognize("photo.png", max_side_len=2048, angle=True)   # 高精度 / 方向纠正
r = recognize("photo.png", ignore_area=[[[0,0],[400,60]]])  # 忽略区域（像素坐标）

# PDF
from dabao_ocr.pdf import ocr_pdf, build_layered_pdf
pages = ocr_pdf("doc.pdf", dpi=200)        # → [PdfPageResult(pno, result)]
build_layered_pdf("doc.pdf", "out.pdf", {p.pno-1: p.result.blocks for p in pages})
```

## Agent 集成

Dabao-OCR 为 agent 场景设计了两条最顺的通道（详见 `examples/agent-usage.md`）：

```bash
# 通道 A：CLI（一次性调用，适合 agent 的终端工具）
dabao-ocr ocr /path/to/image.png --json   # stdout 即结构化结果

# 通道 B：HTTP（常驻服务，适合高频调用）
dabao-ocr serve &                          # 只启动一次
curl -s 127.0.0.1:18224/api/ocr -X POST -d '{"path":"..."}'
```

## 项目结构

```
Dabao-OCR/
├── dabao_ocr/                 # Python 包（纯标准库）
│   ├── engine.py              #   引擎进程管理（线程安全 / 自动重启 / LRU 缓存）
│   ├── ocr.py                 #   高层 API：recognize / recognize_base64
│   ├── result.py              #   结果类型与文本拼接
│   ├── tbpu/                  #   排版解析（移植自 Umi-OCR，8 种方案）
│   ├── pdf.py                 #   PDF 渲染 / 识别 / 双层 PDF
│   ├── exporters.py           #   txt/json/jsonl/md/csv 导出
│   ├── options.py             #   HTTP 选项表（Umi-OCR 兼容）
│   ├── server.py              #   HTTP 服务（stdlib 实现）
│   └── cli.py                 #   命令行入口
├── vendor/RapidOCR-json/      # 引擎二进制 + 模型（MIT, © hiroi-sora）
├── tests/                     # 测试套件（含与原版的一致性对比）
├── examples/agent-usage.md    # agent 使用手册
├── docs/STRIPPING.md          # 剥离与重写记录（相对 Umi-OCR 的差异）
├── pyproject.toml
└── LICENSE / THIRD_PARTY_NOTICES.md
```

## 测试

```bash
uv pip install --python .venv/Scripts/python.exe -e ".[dev]"
.venv/Scripts/python -m pytest tests -q
```

测试覆盖：引擎生命周期与崩溃恢复、识别全路径（路径/字节/base64/相对路径）、
8 种排版解析、忽略区域、6 类语言切换、PDF（渲染/识别/双层/可搜索）、
HTTP API（兼容协议/错误码/CORS/增强端点）、CLI 端到端。

**一致性验证（重点）**：`tests/test_tbpu_parity.py` 把本仓库移植的排版解析
与 Umi-OCR 原版源码逐块对比（8 方案 × 5 场景）；`tests/test_parity_umi.py`
在本机原版 Umi-OCR 服务（:1224）在线时与其逐字符对比识别输出——
两套测试在开发机上全部通过。

## 已知边界

- 仅支持 Windows x64（引擎二进制为 Windows 版）
- 二维码识别（原版 Umi-OCR 的附加功能）未包含；如有需要可基于 `zxing-cpp` 扩展
- 截图/剪贴板等 GUI 交互不在范围内（已随前端剥离）
- 引擎为单进程管道串行模型，超大并发请多起服务实例

## 许可与致谢

本项目以 **MIT License** 发布。识别引擎与排版算法来自
[Umi-OCR](https://github.com/hiroi-sora/Umi-OCR) /
[RapidOCR-json](https://github.com/hiroi-sora/RapidOCR-json)（MIT, © hiroi-sora），
完整声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
