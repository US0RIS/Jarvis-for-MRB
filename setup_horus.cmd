@echo off
setlocal
cd /d "%~dp0"
echo Horus Windows setup
echo ===================
echo.
if not exist ".venv\Scripts\python.exe" (
    echo Creating an isolated Python environment...
    py -3.14 -m venv .venv 2>nul
    if errorlevel 1 py -3.12 -m venv .venv
    if errorlevel 1 (
        echo Python 3.12 or 3.14 is required. Install it from python.org and rerun setup_horus.cmd.
        pause
        exit /b 1
    )
)
set "PYTHON=%CD%\.venv\Scripts\python.exe"
echo Installing Horus dependencies...
"%PYTHON%" -m pip install --disable-pip-version-check -e .
if errorlevel 1 (
    echo Dependency installation failed. Check the error above.
    pause
    exit /b 1
)
echo.
echo Backend installed. Local models and optional service credentials require separate setup.
choice /C YN /M "Configure access from your phone on a trusted private network"
if errorlevel 2 goto start_service
"%PYTHON%" -m jarvis_mrb.remote_setup
if errorlevel 1 goto failure
echo Enter the LAN URL and token shown above in Horus iPhone Settings.
:start_service
echo.
choice /C YN /M "Start Horus automatically when you sign in to Windows"
if errorlevel 2 goto one_time
"%PYTHON%" -m jarvis_mrb.startup
if errorlevel 1 goto failure
goto done
:one_time
echo Starting Horus service for this session...
start "Horus Service" /min "%PYTHON%" -m jarvis_mrb.service
goto done
:failure
echo Setup could not complete the selected optional step.
pause
exit /b 1
:done
echo.
echo Setup complete. Open run_jarvis.cmd for the text console.
pause
endlocal
