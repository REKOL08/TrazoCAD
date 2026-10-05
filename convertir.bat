@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo ============================================
echo  Convirtiendo planos a AutoCAD ...
echo  (detecta solo si el plano esta de lado)
echo ============================================
echo.

if "%~1"=="" (
    "%PYTHON_EXE%" main.py
) else (
    "%PYTHON_EXE%" main.py %*
)

echo.
if exist "Convertidos_DWG" start "" "Convertidos_DWG"
pause
