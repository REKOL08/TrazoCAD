"""Utilidades comunes: logging, validaciones y constantes del proyecto."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

# Carpetas estándar del proyecto, relativas a la raíz del repositorio.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"

# DPI por defecto usado para rasterizar cada página del PDF antes de
# detectar líneas. A mayor DPI, mejor precisión pero más tiempo de proceso.
DEFAULT_DPI = 300
MIN_DPI = 72
MAX_DPI = 600

# Tamaño máximo de PDF que procesamos sin advertir al usuario (en MB).
MAX_PDF_SIZE_WARN_MB = 80

# Nombre fijo de la subcarpeta de resultados, creada automáticamente junto a
# cada PDF de entrada. Es fijo (no se pregunta al usuario) para que el
# proceso de arrastrar-y-soltar no requiera ninguna interacción adicional.
OUTPUT_SUBFOLDER_NAME = "Convertidos_DWG"
PHOTOS_SUBFOLDER_NAME = "planos_de_prueba"


class ConversionError(Exception):
    """Error controlado durante la conversión de un PDF a DWG/DXF."""


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configura logging a consola y a un archivo rotativo en logs/.

    Se usa un logger con nombre fijo ("planos2dwg") para que todos los
    módulos del paquete compartan la misma configuración sin duplicar
    handlers si se llama más de una vez.
    """
    logger = logging.getLogger("planos2dwg")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / "conversion.log",
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # Si no se puede escribir el log en disco (permisos, disco lleno),
        # seguimos solo con la consola en vez de interrumpir la conversión.
        logger.warning("No se pudo crear el archivo de log; se continúa solo con consola.")

    return logger


def validate_pdf(path: Path) -> None:
    """Valida que `path` sea un PDF existente, legible y no vacío.

    Lanza ConversionError con un mensaje claro en español si algo falla,
    en vez de dejar propagar excepciones genéricas de bajo nivel.
    """
    if not path.exists():
        raise ConversionError(f"El archivo no existe: {path}")
    if not path.is_file():
        raise ConversionError(f"La ruta no es un archivo: {path}")
    if path.suffix.lower() != ".pdf":
        raise ConversionError(f"El archivo no tiene extensión .pdf: {path}")
    if path.stat().st_size == 0:
        raise ConversionError(f"El archivo PDF está vacío: {path}")

    with path.open("rb") as handle:
        header = handle.read(5)
    if header != b"%PDF-":
        raise ConversionError(
            f"El archivo no parece un PDF válido (encabezado incorrecto): {path}"
        )


def ensure_output_dir(directory: Path) -> Path:
    """Crea `directory` si no existe y la devuelve."""
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def find_pdfs(inputs: list[Path]) -> list[Path]:
    """Expande una lista de rutas (archivos y/o carpetas) a una lista de PDFs.

    Las carpetas se recorren de forma no recursiva (solo el primer nivel),
    que es el caso de uso esperado cuando alguien arrastra una carpeta de
    planos. Los duplicados se eliminan preservando el orden de aparición.
    """
    pdfs: list[Path] = []
    seen: set[Path] = set()

    for item in inputs:
        item = Path(item)
        if item.is_dir():
            candidates = sorted(item.glob("*.pdf")) + sorted(item.glob("*.PDF"))
        elif item.is_file():
            candidates = [item]
        else:
            continue

        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved not in seen:
                seen.add(resolved)
                pdfs.append(candidate)

    return pdfs
