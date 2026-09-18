# -*- coding: utf-8 -*-
"""Dabao-OCR 开机自启部署（Windows）

安装两件套：
  1. Startup\\DabaoOCR.vbs      —— 登录时静默启动 HTTP 服务（单实例守卫在 serve.cmd）
  2. 计划任务 DabaoOCR_Watchdog —— 每 5 分钟健康检查，服务掉了自动拉起

用法：
  .venv\\Scripts\\python.exe scripts\\install_autostart.py            # 安装
  .venv\\Scripts\\python.exe scripts\\install_autostart.py --uninstall # 卸载
  .venv\\Scripts\\python.exe scripts\\install_autostart.py --status    # 查看状态
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
TASK_NAME = "DabaoOCR_Watchdog"
PORT = 18224


def _startup_dir() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"


def _vbs_target() -> Path:
    return _startup_dir() / "DabaoOCR.vbs"


def _vbs_content() -> str:
    # 纯 ASCII 内容（WSH 解析最稳）；中文说明见仓库文档
    return (
        "' Dabao-OCR HTTP service - logon autostart (silent)\n"
        "' Launcher: scripts\\serve.cmd (single-instance guarded)\n"
        "Option Explicit\n"
        "Dim fso, sh, target\n"
        f'target = "{SCRIPTS / "serve.cmd"}"\n'
        "Set fso = CreateObject(\"Scripting.FileSystemObject\")\n"
        "If Not fso.FileExists(target) Then WScript.Quit 0\n"
        "Set sh = CreateObject(\"WScript.Shell\")\n"
        "sh.Run \"cmd.exe /c call \"\"\" & target & \"\"\"\", 0, False\n"
    )


def _run_schtasks(args: list) -> tuple:
    """调用 schtasks；中文 Windows 输出为 GBK，手动解码。"""
    r = subprocess.run(["schtasks", *args], capture_output=True, timeout=30)
    out = (r.stdout or b"").decode("gbk", errors="replace")
    err = (r.stderr or b"").decode("gbk", errors="replace")
    return r.returncode, out, err


def task_exists() -> bool:
    code, out, _ = _run_schtasks(["/query", "/tn", TASK_NAME])
    return code == 0 and TASK_NAME in out


def install():
    # 1. Startup vbs
    vbs = _vbs_target()
    vbs.parent.mkdir(parents=True, exist_ok=True)
    # 纯 ASCII 内容，无 BOM 写入最稳（ANSI/UTF-8 解析均可）
    vbs.write_text(_vbs_content(), encoding="ascii", errors="replace")
    print(f"[OK] 登录自启已写入: {vbs}")

    # 2. 计划任务（看门狗）
    pythonw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    watchdog = SCRIPTS / "watchdog.py"
    if not pythonw.exists():
        print(f"[WARN] 未找到 {pythonw}，请先创建 .venv")
    tr = f'"{pythonw}" "{watchdog}"'
    code, out, err = _run_schtasks(
        ["/create", "/tn", TASK_NAME, "/tr", tr, "/sc", "minute", "/mo", "5", "/f"]
    )
    if code == 0:
        print(f"[OK] 看门狗计划任务已创建: {TASK_NAME}（每 5 分钟）")
    else:
        print(f"[FAIL] 计划任务创建失败（code={code}）: {out.strip()} {err.strip()}")
        return 1

    # 3. 立即拉起一次服务
    r = subprocess.run(
        [str(pythonw), str(watchdog)], capture_output=True, timeout=60
    )
    if r.returncode == 0:
        print(f"[OK] 服务已就绪: http://127.0.0.1:{PORT}/api/status")
    else:
        print("[WARN] 服务拉起未确认成功，请手动检查 logs/serve.log")
    return 0


def uninstall():
    # 1. 删 Startup vbs
    vbs = _vbs_target()
    if vbs.exists():
        vbs.unlink()
        print(f"[OK] 已删除: {vbs}")
    else:
        print("[i] 登录自启文件不存在，跳过")
    # 2. 删计划任务
    if task_exists():
        code, out, err = _run_schtasks(["/delete", "/tn", TASK_NAME, "/f"])
        if code == 0:
            print(f"[OK] 已删除计划任务: {TASK_NAME}")
        else:
            print(f"[FAIL] 删除任务失败: {out.strip()} {err.strip()}")
    else:
        print("[i] 计划任务不存在，跳过")
    print("[i] 服务进程如需停止：taskkill /F /IM pythonw.exe（注意可能误杀其他 pythonw）")
    return 0


def status():
    vbs = _vbs_target()
    print(f"登录自启 vbs : {'存在  ' + str(vbs) if vbs.exists() else '不存在'}")
    ok = task_exists()
    print(f"看门狗任务   : {'存在' if ok else '不存在'} ({TASK_NAME})")
    if ok:
        _, out, _ = _run_schtasks(["/query", "/tn", TASK_NAME, "/fo", "LIST"])
        for line in out.splitlines():
            if any(k in line for k in ("状态", "Status", "下次", "Next", "上次", "Last")):
                print("              ", line.strip())
    try:
        import json
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/status", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        print(f"服务状态     : 在线（{data.get('name')} v{data.get('version')}，uptime {data.get('uptime_sec')}s）")
    except Exception:
        print("服务状态     : 离线")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--uninstall" in sys.argv:
        sys.exit(uninstall())
    if "--status" in sys.argv:
        sys.exit(status())
    sys.exit(install())
