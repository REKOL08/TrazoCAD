@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

if "%~1"=="" (
    "%PYTHON_EXE%" main.py --rotar 90
) else (
    "%PYTHON_EXE%" main.py %* --rotar 90
)

echo.
pause
