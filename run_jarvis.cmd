@echo off
setlocal
py -3.14 -m jarvis_mrb.cli
if errorlevel 1 py -3.12 -m jarvis_mrb.cli
endlocal
