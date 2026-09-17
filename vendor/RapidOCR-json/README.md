# RapidOCR-json 引擎（vendored）

本目录为 **Dabao-OCR** 内置的离线 OCR 引擎运行时，内容来自
[Umi-OCR](https://github.com/hiroi-sora/Umi-OCR)（MIT License）所附带的
[RapidOCR-json](https://github.com/hiroi-sora/RapidOCR-json)（MIT License, © hiroi-sora）组件：

- `RapidOCR-json.exe` — RapidOCR 的 C++ 封装（v1.1.0），管道模式调用：
  从 stdin 逐行读取 JSON 指令（`{"image_path": ...}` / `{"image_base64": ...}`），
  从 stdout 逐行返回 JSON 结果（`code=100` 成功 / `101` 无文字）。
- `models/` — ONNX 模型库（PaddleOCR 系列检测/方向/识别模型 + 字典），
  可用语言见 `models/configs.txt`（简体中文 / English / 繁體中文 / 日本語 / 한국어 / Русский）。

本目录不参与 Python 打包（不进入 wheel），由仓库随附；
`dabao_ocr` 通过环境变量 `DABAO_OCR_ENGINE_DIR` 或默认相对路径 `vendor/RapidOCR-json` 定位。

许可：MIT（见仓库根 `THIRD_PARTY_NOTICES.md`）。请勿单独替换本目录下二进制以外的 Python 代码。
