#!/usr/bin/env python3
"""Punto de entrada: convierte planos PDF escaneados a DXF/DWG editable.

Modos de uso:
  1. Arrastrar uno o varios PDF (o una carpeta) sobre `convertir.bat`.
  2. Ejecutar `python main.py plano1.pdf plano2.pdf` desde la consola.
  3. Ejecutar `python main.py` sin argumentos: se abre un selector de
     carpeta (o se pide la ruta por consola si no hay entorno gráfico).

Los archivos de salida (.dxf y, si está disponible ODA File Converter,
.dwg) se guardan automáticamente en la subcarpeta "Convertidos_DWG" dentro
de esta misma carpeta del programa (no junto al PDF de entrada); el nombre
de esa subcarpeta es fijo, así que nunca se pregunta nada al usuario.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Evita caracteres corruptos (acentos, ñ) al imprimir en la consola de Windows,
# que por defecto no siempre usa UTF-8.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass

from src.converter import (  # noqa: E402
    DEFAULT_MIN_LENGTH_MM,
    MODE_LINES,
    MODE_TRACE,
    VALID_ROTATIONS,
    convert_pdf,
)
from src.utils import (  # noqa: E402
    DEFAULT_DPI,
    MAX_DPI,
    MIN_DPI,
    OUTPUT_SUBFOLDER_NAME,
    PHOTOS_SUBFOLDER_NAME,
    PROJECT_ROOT,
    find_pdfs,
    setup_logging,
)


def _ask_folder_interactively() -> Path | None:
    """Abre un selector de carpeta gráfico; si no hay GUI, pregunta por consola."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            title="Selecciona la carpeta con los planos PDF a convertir"
        )
        root.destroy()
        return Path(selected) if selected else None
    except Exception:
        try:
            entered = input(
                "Arrastra la carpeta con los PDF aquí y presiona Enter "
                "(o escribe la ruta manualmente): "
            ).strip().strip('"')
        except EOFError:
            return None
        return Path(entered) if entered else None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convierte planos PDF escaneados a DXF/DWG editable."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Archivos PDF y/o carpetas a convertir (arrastrados o escritos a mano).",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"Resolución de escaneo a usar, entre {MIN_DPI} y {MAX_DPI} (por defecto {DEFAULT_DPI}).",
    )
    parser.add_argument(
        "--modo",
        choices=(MODE_TRACE, MODE_LINES),
        default=MODE_TRACE,
        help=(
            "'fiel' (por defecto) calca la tinta del escaneo y se ve igual que el PDF; "
            "'lineas' detecta solo líneas rectas (resultado más limpio pero muy incompleto)."
        ),
    )
    parser.add_argument(
        "--rotar",
        type=int,
        choices=VALID_ROTATIONS,
        default=None,
        help="Gira el plano en sentido antihorario (0, 90, 180 o 270). Si se omite, se detecta solo.",
    )
    parser.add_argument(
        "--ignorar-inferior",
        type=float,
        default=None,
        help=(
            "Fracción de la altura (0 a 0.5) de la franja inferior (el cajetín) que se ignora al "
            "buscar muros y ejes. Si se omite, se detecta sola."
        ),
    )
    parser.add_argument(
        "--grosor-muro",
        type=float,
        default=None,
        help=(
            "Espesor de los muros en milímetros sobre el papel. Si se omite, se mide solo "
            "el espesor más repetido del plano."
        ),
    )
    parser.add_argument(
        "--sin-texto",
        action="store_true",
        help="No leer los textos con OCR (más rápido; los textos quedan solo como calco).",
    )
    parser.add_argument(
        "--fotos",
        type=Path,
        default=None,
        metavar="CARPETA",
        help=(
            "Carpeta con fotos de partes del plano para leer mejor las cotas y los textos "
            "(por defecto 'planos_de_prueba'; las fotos que no coinciden con el plano se ignoran)."
        ),
    )
    parser.add_argument(
        "--sin-fotos",
        action="store_true",
        help="No usar fotos de partes del plano, aunque haya en la carpeta.",
    )
    parser.add_argument(
        "--conservar-dxf",
        action="store_true",
        help="Guardar también el .dxf junto al .dwg (por defecto se entrega un solo archivo por plano).",
    )
    parser.add_argument(
        "--calco-visible",
        action="store_true",
        help="Dejar encendido el relleno gris del escaneo (por defecto va en el archivo pero apagado).",
    )
    parser.add_argument(
        "--solo-limpio",
        action="store_true",
        help="No incluir la capa CALCADO_REFERENCIA: solo muros y ejes reconstruidos.",
    )
    parser.add_argument(
        "--min-length",
        type=float,
        default=DEFAULT_MIN_LENGTH_MM,
        dest="min_length_mm",
        help=(
            "Longitud mínima en milímetros (sobre el plano final) para conservar un "
            f"segmento detectado; solo aplica al modo 'lineas' (por defecto {DEFAULT_MIN_LENGTH_MM})."
        ),
    )
    parser.add_argument(
        "--no-dwg",
        action="store_true",
        help="Generar solo .dxf, sin intentar convertir a .dwg real con ODA File Converter.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Mostrar información detallada de depuración.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    logger = setup_logging(verbose=args.verbose)

    if not args.dpi or not (MIN_DPI <= args.dpi <= MAX_DPI):
        logger.error("El valor de --dpi debe estar entre %d y %d.", MIN_DPI, MAX_DPI)
        return 2

    raw_inputs = [Path(item) for item in args.inputs]
    if not raw_inputs:
        logger.info("No se recibieron archivos ni carpetas; se abre el selector.")
        folder = _ask_folder_interactively()
        if folder is None:
            logger.error("No se seleccionó ninguna carpeta. Operación cancelada.")
            return 1
        raw_inputs = [folder]

    pdfs = find_pdfs(raw_inputs)
    if not pdfs:
        logger.error("No se encontró ningún archivo .pdf en lo indicado: %s", raw_inputs)
        return 1

    output_dir = PROJECT_ROOT / OUTPUT_SUBFOLDER_NAME
    logger.info("Se van a procesar %d archivo(s) PDF a %d DPI.", len(pdfs), args.dpi)
    logger.info("Los resultados se guardarán en: %s", output_dir)

    successes = 0
    photos_dir = None if args.sin_fotos else (args.fotos or PROJECT_ROOT / PHOTOS_SUBFOLDER_NAME)
    failures = 0
    for pdf_path in pdfs:
        logger.info("Procesando: %s", pdf_path)
        result = convert_pdf(
            pdf_path,
            output_dir=output_dir,
            dpi=args.dpi,
            generate_dwg=not args.no_dwg,
            min_length_mm=args.min_length_mm,
            mode=args.modo,
            rotation=args.rotar,
            ignore_bottom_fraction=args.ignorar_inferior,
            clean_only=args.solo_limpio,
            wall_thickness_mm=args.grosor_muro,
            read_text=not args.sin_texto,
            keep_dxf=args.conservar_dxf,
            trace_visible=args.calco_visible,
            photos_dir=photos_dir,
        )
        if result.success:
            successes += 1
            for output in result.outputs:
                logger.info("  -> PLANO LISTO: %s", output)
            if result.summary:
                logger.info(
                    "     Contiene: %s.",
                    ", ".join(f"{count} {name}" for name, count in result.summary.items() if count),
                )
        else:
            failures += 1
            logger.error("  -> FALLÓ '%s': %s", pdf_path.name, result.error)

    logger.info("Listo: %d exitoso(s), %d con error, de %d total.", successes, failures, len(pdfs))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
