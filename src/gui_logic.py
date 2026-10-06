"""Lógica de la interfaz (sin ventanas, para poder probarla): comando, archivos y mensajes amables.

La ventana (`app.py`) ejecuta `main.py` como un proceso aparte y traduce las líneas de su registro a
frases cortas de chat. Así un fallo del convertidor no tumba la ventana y se puede detener.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROTATIONS = ("auto", "90", "180", "270")
_LOG_LINE = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d \[(\w+)\] (.*)$")


@dataclass(frozen=True)
class Options:
    """Lo que el usuario enciende o apaga con las fichas de la ventana."""

    photos: tuple[Path, ...] = ()
    output_dir: Path | None = None
    read_text: bool = True
    show_scan_fill: bool = False
    keep_dxf: bool = False
    rotation: str = "auto"


@dataclass(frozen=True)
class Event:
    """Algo que contarle al usuario: kind = info | warn | error | done | summary."""

    kind: str
    text: str


def collect_pdfs(paths: list[str | Path]) -> tuple[list[Path], list[Path]]:
    """Separa lo arrastrado en PDF (las carpetas se abren un nivel) y cosas que no sirven."""
    pdfs: list[Path] = []
    ignored: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found = sorted(p for p in path.iterdir() if p.suffix.lower() == ".pdf" and p.is_file())
            pdfs.extend(found)
            if not found:
                ignored.append(path)
        elif path.suffix.lower() == ".pdf" and path.is_file():
            pdfs.append(path)
        else:
            ignored.append(path)
    return pdfs, ignored


def build_command(python: str, main_py: Path, pdf: Path, options: Options) -> list[str]:
    """Línea de comandos de `main.py` equivalente a las fichas encendidas."""
    command = [python, str(main_py), str(pdf)]
    if not options.read_text:
        command.append("--sin-texto")
    if options.show_scan_fill:
        command.append("--calco-visible")
    if options.keep_dxf:
        command.append("--conservar-dxf")
    if options.rotation in ROTATIONS and options.rotation != "auto":
        command += ["--rotar", options.rotation]
    if options.photos:
        for photo in options.photos:
            command += ["--foto", str(photo)]
    else:
        command.append("--sin-fotos")
    if options.output_dir is not None:
        command += ["--salida", str(options.output_dir)]
    return command


_INVALID_NAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def clean_folder_name(name: str, fallback: str) -> str:
    """Un nombre válido de carpeta de Windows a partir de lo que escribió el usuario."""
    cleaned = _INVALID_NAME_CHARS.sub("", name).strip().rstrip(". ")
    if cleaned.upper() in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(COM|LPT)\d", cleaned.upper() or "-"):
        cleaned = ""
    return cleaned or fallback


# (fragmento del registro, clave de etapa, frase). Cada etapa se cuenta una sola vez.
_STAGES = (
    ("Muros:", "muros", "✔ Muros y ejes dibujados"),
    ("Puertas:", "puertas", "✔ Puertas ubicadas"),
    ("Ventanas:", "ventanas", "✔ Ventanas ubicadas"),
    ("alineada con el plano", "foto", "📷 Usé tus fotos para leer mejor las cotas"),
    ("Sanitarios:", "sanitarios", "✔ Sanitarios ubicados"),
    ("Detalle:", "detalle", "✔ Escaleras, muebles y detalles redibujados"),
    ("DXF generado", "dxf", "✔ Armando el archivo de AutoCAD…"),
)


def friendly_event(line: str, seen: set[str]) -> Event | None:
    """Traduce una línea del registro a un mensaje de chat; None si no hay nada que decir."""
    match = _LOG_LINE.match(line.strip())
    if not match:
        return None
    level, message = match.group(1), match.group(2)

    if level in ("ERROR", "CRITICAL"):
        return Event("error", message)
    if level == "WARNING":
        dpi = re.search(r"tiene solo (\d+) dpi", message)
        if dpi and "dpi" not in seen:
            seen.add("dpi")
            return Event(
                "warn",
                f"⚠ Ojo: tu escaneo es de baja calidad ({dpi.group(1)} dpi). Salió, pero las "
                "cotas pequeñas se leen mejor si escaneas a 300-400 dpi.",
            )
        return None
    if "PLANO LISTO:" in message:
        return Event("done", message.split("PLANO LISTO:", 1)[1].strip())
    if message.strip().startswith("Contiene:"):
        return Event("summary", message.strip()[len("Contiene:"):].strip().rstrip("."))
    if message.startswith("OCR:") and "ocr" not in seen:
        seen.add("ocr")
        return Event("info", "✔ Leí los textos del plano")
    for fragment, key, text in _STAGES:
        if fragment in message and key not in seen:
            seen.add(key)
            return Event("info", text)
    return None
