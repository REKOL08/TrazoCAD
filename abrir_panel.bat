@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Panel de avance de TrazoCAD en http://127.0.0.1:8765/panel/index.html
echo (deja esta ventana abierta; ciérrala para apagar el panel)
start "" "http://127.0.0.1:8765/panel/index.html"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m http.server 8765 --bind 127.0.0.1
) else (
    python -m http.server 8765 --bind 127.0.0.1
)
