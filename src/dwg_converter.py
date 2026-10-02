"""Conversión opcional de DXF a DWG binario real usando ODA File Converter.

Ninguna librería de Python libre puede escribir archivos .dwg binarios
(es un formato propietario de Autodesk). El camino gratuito estándar en
la industria es generar DXF (formato abierto que AutoCAD lee de forma
nativa) y, si se quiere un .dwg real además, convertirlo con la
herramienta de línea de comandos gratuita "ODA File Converter" de la
Open Design Alliance. Esta función la detecta automáticamente si está
instalada; si no, el DXF se deja como resultado final (ver README).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger("planos2dwg")

# Nombres y rutas típicas de instalación en Windows, de más reciente a más
# antigua. ODA cambia el número de versión en el nombre de carpeta/ejecutable.
_CANDIDATE_NAMES = ["ODAFileConverter.exe", "ODAFileConverter"]
_CANDIDATE_DIRS = [
    Path(r"C:\Program Files\ODA"),
    Path(r"C:\Program Files (x86)\ODA"),
]

DWG_OUTPUT_VERSION = "ACAD2018"
_WARNED_MISSING = False


def find_oda_file_converter() -> Path | None:
    """Busca el ejecutable de ODA File Converter en el PATH o en Program Files.

    Devuelve None si no está instalado; en ese caso la conversión se queda
    en DXF, que AutoCAD abre igualmente.
    """
    for name in _CANDIDATE_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)

    for base_dir in _CANDIDATE_DIRS:
        if not base_dir.exists():
            continue
        for exe in base_dir.rglob("ODAFileConverter.exe"):
            return exe

    return None


def convert_dxf_to_dwg(
    dxf_path: Path,
    output_dir: Path,
    oda_converter_path: Path | None = None,
) -> Path | None:
    """Convierte `dxf_path` a .dwg real usando ODA File Converter.

    ODA File Converter solo trabaja por carpetas (no admite un único
    archivo como argumento), así que copiamos el DXF a una carpeta temporal
    de entrada y recogemos el resultado de la carpeta temporal de salida.

    Devuelve la ruta del .dwg generado, o None si el conversor no está
    disponible o la conversión falla (en ambos casos el DXF ya generado
    sigue siendo un resultado válido y utilizable en AutoCAD).
    """
    global _WARNED_MISSING
    converter = oda_converter_path or find_oda_file_converter()
    if converter is None:
        if _WARNED_MISSING:
            return None
        _WARNED_MISSING = True
        logger.warning(
            "ODA File Converter no está instalado: se entrega el plano en "
            "formato DXF (AutoCAD lo abre igual). Instálalo si necesitas "
            "un archivo .dwg real; ver instrucciones en el README."
        )
        return None

    with tempfile.TemporaryDirectory(prefix="planos2dwg_in_") as tmp_in, \
            tempfile.TemporaryDirectory(prefix="planos2dwg_out_") as tmp_out:
        tmp_in_path = Path(tmp_in)
        tmp_out_path = Path(tmp_out)
        shutil.copy2(dxf_path, tmp_in_path / dxf_path.name)

        command = [
            str(converter),
            str(tmp_in_path),
            str(tmp_out_path),
            DWG_OUTPUT_VERSION,
            "DWG",
            "0",  # no recursivo
            "1",  # auditar archivos de entrada
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.error("Fallo al ejecutar ODA File Converter: %s", exc)
            return None

        if result.returncode != 0:
            logger.error(
                "ODA File Converter terminó con error (código %d): %s",
                result.returncode,
                result.stderr.strip() or result.stdout.strip(),
            )
            return None

        generated = tmp_out_path / f"{dxf_path.stem}.dwg"
        if not generated.exists():
            logger.error("ODA File Converter no generó el .dwg esperado para %s", dxf_path.name)
            return None

        output_dir.mkdir(parents=True, exist_ok=True)
        final_path = output_dir / generated.name
        shutil.move(str(generated), final_path)
        logger.info("DWG generado: %s", final_path)
        return final_path
