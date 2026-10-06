"""Panel de avance de TrazoCAD: registra lo que se va haciendo y lo que se va generando.

La página `panel/index.html` lee `panel/estado.json` cada pocos segundos, así que se actualiza sola.

Uso:
    python panel/panel.py ahora "Probando el modelo de visión"      # lo que se hace en este momento
    python panel/panel.py evento "Modelo descargado" --estado hecho  # línea de tiempo (hecho | curso | error | info)
    python panel/panel.py dato "Puertas detectadas" "4 de 10"         # cifra para el tablero
    python panel/panel.py galeria                                     # vuelve a buscar imágenes nuevas
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = Path(__file__).resolve().parent / "estado.json"
LOG = Path(__file__).resolve().parent / "actividad.log"  # texto plano: se puede abrir en el editor y se refresca solo
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_EVENTS = 200
MAX_PER_GROUP = 24

# (título del grupo, carpeta a vigilar, patrón)
GROUPS = (
    ("Pruebas de visión", ROOT / "experimentos" / "resultados", "*"),
    ("Vistas previas de conversiones", ROOT / "Convertidos_DWG", "**/2_Vista_previa/*"),
)


def _load() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"ahora": {"texto": "Esperando…", "estado": "info"}, "eventos": [], "datos": {}, "galeria": []}


def _scan() -> list[dict]:
    groups = []
    for title, folder, pattern in GROUPS:
        if not folder.is_dir():
            continue
        files = [p for p in folder.glob(pattern) if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        items = [
            {
                "titulo": p.stem.replace("_", " "),
                "ruta": p.relative_to(ROOT).as_posix(),
                "mtime": int(p.stat().st_mtime),
            }
            for p in files[:MAX_PER_GROUP]
        ]
        if items:
            groups.append({"grupo": title, "items": items})
    return groups


def _save(state: dict) -> None:
    state["actualizado"] = time.strftime("%H:%M:%S")
    state["galeria"] = _scan()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def _log_line(kind: str, text: str, detail: str = "") -> None:
    mark = {"hecho": "[OK]   ", "error": "[ERROR]", "curso": "[...]  ", "info": "[info] "}.get(kind, "[info] ")
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%H:%M:%S')} {mark} {text}" + (f"  ({detail})" if detail else "") + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    ahora = sub.add_parser("ahora")
    ahora.add_argument("texto")
    ahora.add_argument("--estado", default="curso", choices=["curso", "hecho", "error", "info"])
    event = sub.add_parser("evento")
    event.add_argument("texto")
    event.add_argument("--estado", default="info", choices=["curso", "hecho", "error", "info"])
    event.add_argument("--detalle", default="")
    data = sub.add_parser("dato")
    data.add_argument("nombre")
    data.add_argument("valor")
    sub.add_parser("galeria")
    args = parser.parse_args()

    state = _load()
    now = time.strftime("%H:%M:%S")
    if args.cmd == "ahora":
        state["ahora"] = {"texto": args.texto, "estado": args.estado}
        _log_line(args.estado, "AHORA: " + args.texto)
    elif args.cmd == "evento":
        state["eventos"].insert(0, {"hora": now, "texto": args.texto, "estado": args.estado, "detalle": args.detalle})
        state["eventos"] = state["eventos"][:MAX_EVENTS]
        _log_line(args.estado, args.texto, args.detalle)
    elif args.cmd == "dato":
        state["datos"][args.nombre] = args.valor
        _log_line("info", f"{args.nombre}: {args.valor}")
    _save(state)


if __name__ == "__main__":
    main()
