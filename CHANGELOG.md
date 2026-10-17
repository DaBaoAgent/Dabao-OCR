# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [1.1.0] - 2026-10-17

以「更干净、更简洁、更高效」为目标的一轮全量审查与修复。**识别结果与原版保持逐块一致**，
下列改动只涉及工程外壳、错误处理与资源管理。

### 新增

- **CLI 快通道**：检测到本机常驻服务（默认 `127.0.0.1:18224`）时自动复用，
  省掉每次调用的引擎冷启动（实测约 0.3s/次）。`--no-service` 或 `DABAO_OCR_NO_SERVICE=1` 可关闭。
  新增模块 `dabao_ocr/service.py`（50ms TCP 探活 + `http.client` 直连，连接/读取超时分离）。
- **引擎随父进程退出**：用 Windows Job Object（`KILL_ON_JOB_CLOSE`）绑定引擎子进程，
  服务被 `taskkill /F` 或崩溃时不再残留 ~275MB 的 `RapidOCR-json.exe` 孤儿进程。
- **4 种修正版排版方案**：`single_line_fixed` / `single_none_fixed` /
  `single_code_fixed` / `single_para_fixed`。修正原版单栏方案的两处计算缺陷
  （行高公式误用左边界 `l2`、行包围盒合并误用刚更新的 `b1`）。
  **原 8 种方案完全不变**，需要与原版逐块一致时继续用原方案。
- 环境变量 `DABAO_OCR_NUM_THREAD`：覆盖引擎线程数（默认按 CPU 核心数）。
- `py.typed`：对外声明包内类型标注。
- `install_autostart.py --stop`：按端口定位 PID 停止服务，替代容易误杀的
  `taskkill /IM pythonw.exe`；卸载时也会自动停掉在跑的服务。
- 新增测试：`test_exporters.py`（15 项）、`test_langs.py`（11 项）、
  `test_line_preprocessing.py`（18 项）、`test_options.py`（19 项），
  补齐原先零覆盖的模块；其中 `line_preprocessing.py` 覆盖率 66% → 100%。

### 修复

- `/api/ocr/batch` 的 `images` 直接传 base64 字符串时被误判成本机路径（base64 字母表含 `/`）而失败。
- 客户端提前断开时 `ConnectionResetError/ConnectionAbortedError` 打印整屏 traceback。
- 空识别结果触发 `median([])` 的 `StatisticsError`，导致排版解析静默降级、`end` 字段缺失。
- `OcrEngine.run_path()` 传相对路径时静默返回 `code 200`（引擎 cwd 在引擎目录）。
- CSV 编码探测只检查 OCR 文本列，纯 ASCII 文本 + 中文文件名会导致导出崩溃。
- `export` 的 txt 分支与 `data_to_text` 使用 `+=` 拼接，大结果集下退化为二次方复杂度。
- `parse_pages_spec` 用 list 去重，页数多时为 O(n²)。
- `resolve_language` 在空配置时抛 `TypeError` 而非 `LanguageError`。
- 语言表缓存返回浅拷贝，调用方改写会污染缓存（改为逐层复制）。
- `install_autostart.py --uninstall` 原先提示用 `taskkill /F /IM pythonw.exe` 停服务，
  会连带杀掉本机其他无关的 pythonw 进程。
- 引擎子进程 `kill()` 后未 `wait()`、未关闭 stdin/stdout，长跑会累积句柄。
- 每个引擎实例注册一个 `atexit` 回调，绑定方法强引用实例，导致 LRU 淘汰的实例无法回收。

### 变更

- `--parser` 拼错从「静默降级为 `none`」改为**直接报错**（CLI 报 `invalid choice`，HTTP 返回 804）。
- 引擎响应**超时不再重试**（新增 `OcrEngineTimeout`）：最坏耗时从 2×`timeout` 降到 1×`timeout`。
- 引擎子进程创建标志由 `CREATE_NEW_CONSOLE + SW_HIDE` 改为 `CREATE_NO_WINDOW`。
- `fill_defaults` 改用静态默认值表，不再为 6 个默认值构建整张带文案的选项表。
- 打包配置由硬编码包列表改为 `[tool.setuptools.packages.find]`。
- 许可证元数据改用 **PEP 639** 写法：`license = "MIT"` + `license-files = ["LICENSE"]`，
  产出 `License-Expression: MIT`；同时移除已与之冲突的 `License :: OSI Approved :: MIT License`
  classifier（PEP 639 明确禁止两者并存）。

### 移除

- `vendor/RapidOCR-json/models/ppocr_keys_v1.txt`：与 `dict_chinese.txt` MD5 完全相同的重复文件。
- `vendor/RapidOCR-json/models/ch_PP-OCRv4_det_infer.onnx`（4.7 MB）：`configs.txt` 中
  6 种语言全部使用 `ch_PP-OCRv3_det_infer.onnx`，该文件零引用。

### 单栏方案的两处历史缺陷：已提供修正版，原方案保持不变

tbpu 中有两处变量引用错误，**继承自 Umi-OCR 原版**：

| 位置 | 问题 | 影响范围 |
|---|---|---|
| `parser_single_line.py` | 行高公式 `h = (b1 + b2 - t1 - l2) * 0.5` 用了左边界 `l2`，应为上边界 `t2`；`h` 可能变成大负数，使"间隙过大"恒成立而**误插空格** | `single_line` / `single_none` / `single_para` / `single_code` |
| `parser_single_para.py` | `b2 = max(b1, bb[2])`、`b3 = max(b1, bb[3])` 用了刚被更新的 `b1`，右/下边界偏小 | `single_para` |

处理方式：

- **原 8 种方案保持不变**（继续与 Umi-OCR 逐块一致，供新旧结果比对使用）
- 新增 4 种 `single_*_fixed` 修正版，只改这两处计算，其余逻辑完全继承
- 实测差异：页面右侧同一行的两个中文块，原方案会插入空格（`中文 内容`），
  修正版按 CJK 规则不加（`中文内容`）；页面下部左对齐窄行，原方案把行包围盒右边界
  算成 y 坐标（`1000` 而非 `400`）

选择建议：默认方案 `multi_para` 不受影响；用 `single_*` 且在意空格/段落切分时，
换成对应的 `_fixed` 版本。

## [1.0.0] - 2026-10-07

首个版本：从 Umi-OCR 剥离 GUI 前端，提供 CLI / HTTP API / Python 库三种形态。
