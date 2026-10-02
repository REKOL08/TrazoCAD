@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ============================================
echo  Instalando Planos2DWG
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] No se encontro Python en el sistema.
    echo Instala Python 3.10 o superior desde https://www.python.org/downloads/
    echo e inicia este instalador de nuevo.
    pause
    exit /b 1
)

echo Creando entorno virtual en .venv ...
python -m venv .venv
if errorlevel 1 (
    echo [ERROR] No se pudo crear el entorno virtual.
    pause
    exit /b 1
)

echo Instalando dependencias ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

echo.
echo Instalando lectura de textos (OCR, opcional) ...
".venv\Scripts\python.exe" -m pip install -r requirements-ocr.txt
if errorlevel 1 (
    echo [AVISO] No se pudo instalar el OCR. El programa funciona igual, pero los textos
    echo quedaran solo como dibujo y no como texto editable.
)

echo.
echo ============================================
echo  Instalacion completa.
echo  Ya puedes arrastrar tus PDF sobre convertir.bat
echo ============================================
pause
