# Agent 使用手册

面向自动化 agent（Hermes / 其他智能体）与脚本作者：如何在任务中调用 Dabao-OCR。

## 0. 一句话

**图片 → 文本**：`dabao-ocr ocr <图片路径>`（stdout 直接得到识别文本）。
**要坐标/置信度**：加 `--json`。**高频调用**：起一次 `dabao-ocr serve`，之后走 HTTP。

## 1. CLI 通道（推荐：一次性任务）

前提：仓库虚拟环境已就绪（`D:\@kaifa\Dabao-OCR\.venv`），或已 `pip install -e .`。

```bash
# 纯文本（最常见）
dabao-ocr ocr "D:/path/img.png"

# 结构化（box 坐标、score 置信度、end 分隔符）
dabao-ocr ocr "D:/path/img.png" --json

# 管道：从 stdin 喂图片字节（截图管道等场景）
dabao-ocr ocr - < shot.png

# 批量：目录/多文件 → jsonl（stdout）或导出到目录
dabao-ocr batch "D:/photos/" -o "D:/out/" --format jsonl
```

关键行为：

- 退出码：`0` 成功（含“无文字”）；`2` 失败（文件不存在 / 引擎错误，stderr 有原因）
- 输出编码始终 UTF-8（与 bash / MSYS 兼容）
- 相对路径按调用者 cwd 解析；引擎自身不弹任何窗口，可放心在后台调用
- 参数：`--language`（6 种）、`--parser`（8 种排版方案）、`--angle`、`--max-side`、`--ignore-area`

## 2. HTTP 通道（推荐：高频/多任务/跨进程）

启动一次（后台常驻，端口默认 18224）：

```bash
dabao-ocr serve --port 18224 --port-auto
```

之后随用随调：

```bash
# 识别本机图片（path 直读；也支持 base64 字段）
curl -s http://127.0.0.1:18224/api/ocr -X POST \
  -H "Content-Type: application/json" \
  -d '{"path": "D:/a.png", "options": {"data.format": "text"}}'

# 输出结构：{"code":100,"data":"..."}  或 dict 格式 {"code":100,"data":[{box,score,text,end}...]}

# 批量一次调用
curl -s 127.0.0.1:18224/api/ocr/batch -X POST \
  -d '{"images":[{"path":"a.png"},{"path":"b.png"}],"options":{"data.format":"text"}}'

# PDF
curl -s 127.0.0.1:18224/api/pdf -X POST \
  -d '{"path":"doc.pdf","options":{"pages":"1-5","dpi":200}}'
```

行为细节：

- 并发请求在服务内排队（引擎串行），线程安全；允许 CORS（本机网页可直接调）
- 二进制不要塞进 JSON 时用 base64：`{"base64": "iVBORw0..."}`（与原版 Umi-OCR 相同）
- 错误码：`800` 非法 JSON / `801` 空请求 / `802` 缺输入 / `803` options 非字典 / `804` options 解释失败 / `9xx` 运行错误

## 3. Python 通道（推荐：agent 自身有 Python 执行能力）

```python
from dabao_ocr import recognize

r = recognize("D:/a.png")           # r.ok / r.text / r.blocks
text = r.text
```

## 4. 场景配方

| 场景 | 做法 |
|---|---|
| 截图/截屏内容提取 | 存成 png → `ocr --parser single_none`（避免多栏重排，保序） |
| 表格/票据（要保行） | `--parser single_line` 或 `multi_line` |
| 代码截图 | `--parser single_code`（保留缩进） |
| 倒置/倾斜照片 | 加 `--angle` |
| 大图/高清 | `--max-side 2048`（更准，更多耗时） |
| 固定模板去水印区 | `--ignore-area "[[[0,0],[800,60]]]"`（像素坐标） |
| 扫描 PDF 检索化 | `pdf --layered out.pdf` → 得到可搜索 PDF |

## 5. 工程化常驻（可选）

若希望 HTTP 服务开机常驻：

```bat
:: 计划任务示例（管理员 cmd）
schtasks /create /tn DabaoOCR /tr "D:\@kaifa\Dabao-OCR\.venv\Scripts\python.exe -m dabao_ocr serve --port 18224" /sc onlogon
```

## 6. 排障

| 现象 | 原因/处理 |
|---|---|
| `找不到 RapidOCR-json 引擎目录` | 确认 `vendor/RapidOCR-json/` 存在；或用环境变量 `DABAO_OCR_ENGINE_DIR` 指定 |
| 首次识别慢（~1-2s） | 引擎冷启动正常；每次进程内会复用（HTTP/批处理场景一次性代价） |
| `code 200 Image path dose not exist` | 路径不存在或格式不对（引擎只认 png/jpg/webp/bmp/tif 等） |
| 长时间无响应 | 单请求默认超时 180s，可 `DABAO_OCR_TIMEOUT` 调大；引擎卡死会自动重启重试 |
| PDF 报 `需要 PyMuPDF` | `pip install PyMuPDF` 或 `pip install -e ".[pdf]"` |
