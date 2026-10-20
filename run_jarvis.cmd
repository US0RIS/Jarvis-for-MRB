@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m jarvis_mrb.cli
) else (
    py -3.14 -m jarvis_mrb.cli
    if errorlevel 1 py -3.12 -m jarvis_mrb.cli
)
endlocal
