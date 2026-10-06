# Crea el acceso directo "TrazoCAD" (con su logo) en el escritorio.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $found = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($found) { $pythonw = $found.Source } else { throw "No encuentro Python. Ejecuta primero instalar.bat" }
}
$desktop = [Environment]::GetFolderPath("Desktop")
$link = Join-Path $desktop "TrazoCAD.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "`"$(Join-Path $root 'app.py')`""
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = (Join-Path $root "assets\trazocad.ico") + ",0"
$shortcut.Description = "Convierte un plano escaneado (PDF) en un archivo de AutoCAD"
$shortcut.Save()
Write-Host "Acceso directo creado: $link"
