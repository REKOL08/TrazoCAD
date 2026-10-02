from pathlib import Path

import pytest

from src.utils import ConversionError, find_pdfs, validate_pdf


def test_validate_pdf_rechaza_archivo_inexistente(tmp_path: Path) -> None:
    with pytest.raises(ConversionError, match="no existe"):
        validate_pdf(tmp_path / "no_existe.pdf")


def test_validate_pdf_rechaza_extension_incorrecta(tmp_path: Path) -> None:
    archivo = tmp_path / "plano.txt"
    archivo.write_text("contenido")
    with pytest.raises(ConversionError, match="extensión"):
        validate_pdf(archivo)


def test_validate_pdf_rechaza_archivo_vacio(tmp_path: Path) -> None:
    archivo = tmp_path / "plano.pdf"
    archivo.touch()
    with pytest.raises(ConversionError, match="vacío"):
        validate_pdf(archivo)


def test_validate_pdf_rechaza_encabezado_invalido(tmp_path: Path) -> None:
    archivo = tmp_path / "plano.pdf"
    archivo.write_bytes(b"esto no es un pdf")
    with pytest.raises(ConversionError, match="no parece un PDF"):
        validate_pdf(archivo)


def test_validate_pdf_acepta_pdf_valido(tmp_path: Path) -> None:
    archivo = tmp_path / "plano.pdf"
    archivo.write_bytes(b"%PDF-1.4\n%%EOF")
    validate_pdf(archivo)  # no debe lanzar


def test_find_pdfs_expande_carpeta(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "b.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "c.txt").write_text("no es pdf")

    encontrados = find_pdfs([tmp_path])

    nombres = sorted(p.name for p in encontrados)
    assert nombres == ["a.pdf", "b.pdf"]


def test_find_pdfs_sin_duplicados(tmp_path: Path) -> None:
    pdf = tmp_path / "plano.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    encontrados = find_pdfs([pdf, tmp_path])

    assert len(encontrados) == 1
