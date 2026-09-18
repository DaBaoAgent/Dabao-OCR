@echo off
rem ============================================================
rem  Dabao-OCR HTTP server launcher (single-instance guarded)
rem  Called by Startup\DabaoOCR.vbs (logon) or manually.
rem  NOTE: keep this file ASCII-only (cmd parses it in ANSI).
rem ============================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

rem Single-instance guard: skip if port 18224 is already LISTENING
netstat -ano | findstr ":18224" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [DabaoOCR] port 18224 already serving, skip.
  exit /b 0
)

if not exist logs mkdir logs
echo [%date% %time%] [serve.cmd] starting Dabao-OCR server >> logs\serve.log
".venv\Scripts\pythonw.exe" -m dabao_ocr serve --port 18224 >> logs\serve.log 2>&1
