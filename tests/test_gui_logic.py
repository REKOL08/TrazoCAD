from pathlib import Path

from src.gui_logic import Options, build_command, collect_pdfs, friendly_event


def _linea(nivel: str, mensaje: str) -> str:
    return f"2026-10-05 17:42:47 [{nivel}] {mensaje}"


def test_comando_por_defecto_solo_lleva_el_pdf() -> None:
    comando = build_command("py", Path("main.py"), Path("a.pdf"), Options())

    assert comando == ["py", "main.py", "a.pdf"]


def test_las_fichas_apagadas_o_encendidas_se_traducen_a_banderas() -> None:
    opciones = Options(use_photos=False, read_text=False, show_scan_fill=True, keep_dxf=True, rotation="90")

    comando = build_command("py", Path("main.py"), Path("a.pdf"), opciones)

    assert {"--sin-texto", "--calco-visible", "--conservar-dxf", "--sin-fotos"} <= set(comando)
    assert comando[comando.index("--rotar") + 1] == "90"


def test_la_carpeta_de_fotos_elegida_se_pasa_al_convertidor() -> None:
    comando = build_command("py", Path("main.py"), Path("a.pdf"), Options(photos_dir=Path("mis_fotos")))

    assert comando[comando.index("--fotos") + 1] == "mis_fotos"
    assert "--sin-fotos" not in comando


def test_collect_pdfs_separa_pdf_carpetas_y_otros(tmp_path: Path) -> None:
    (tmp_path / "uno.pdf").write_bytes(b"%PDF")
    (tmp_path / "foto.jpg").write_bytes(b"x")
    carpeta = tmp_path / "lote"
    carpeta.mkdir()
    (carpeta / "dos.PDF").write_bytes(b"%PDF")
    vacia = tmp_path / "vacia"
    vacia.mkdir()

    pdfs, ignorados = collect_pdfs([tmp_path / "uno.pdf", tmp_path / "foto.jpg", carpeta, vacia])

    assert [p.name for p in pdfs] == ["uno.pdf", "dos.PDF"]
    assert sorted(p.name for p in ignorados) == ["foto.jpg", "vacia"]


def test_cada_etapa_se_cuenta_una_sola_vez() -> None:
    vistos: set[str] = set()
    linea = _linea("INFO", "Muros: 96 caras (de 129 segmentos). Ejes: 19. Arcos: 11.")

    primero = friendly_event(linea, vistos)
    segundo = friendly_event(linea, vistos)

    assert primero is not None and "Muros" in primero.text
    assert segundo is None


def test_el_plano_listo_y_el_resumen_se_reconocen() -> None:
    vistos: set[str] = set()

    listo = friendly_event(_linea("INFO", "  -> PLANO LISTO: C:/x/plano.dwg"), vistos)
    resumen = friendly_event(_linea("INFO", "     Contiene: 96 muros, 19 ejes."), vistos)

    assert listo is not None and listo.kind == "done" and listo.text == "C:/x/plano.dwg"
    assert resumen is not None and resumen.kind == "summary" and resumen.text == "96 muros, 19 ejes"


def test_el_aviso_de_baja_resolucion_sale_una_vez_y_los_errores_pasan() -> None:
    vistos: set[str] = set()
    aviso = _linea("WARNING", "'a.pdf': el escaneo del PDF tiene solo 150 dpi reales. Los textos...")

    assert "150 dpi" in friendly_event(aviso, vistos).text
    assert friendly_event(aviso, vistos) is None
    error = friendly_event(_linea("ERROR", "El PDF está protegido"), vistos)
    assert error is not None and error.kind == "error"


def test_lineas_ajenas_al_registro_se_ignoran() -> None:
    assert friendly_event("Traceback (most recent call last):", set()) is None
