"""Conversión directa entre KMZ y KML, sin pasar por el modelo (no se pierde nada del KML)."""

from pathlib import Path
from xml.etree import ElementTree as ET

from ferromapas.build import write_kmz
from ferromapas.reader import ReadError, extract_kml


def kmz_to_kml(kmz: str | Path, kml: str | Path, force: bool = False) -> list[str]:
    """Extrae el doc.kml de un KMZ. Devuelve los demás archivos del KMZ, que no se copian."""
    kml = _check_output(kml, force)
    data, extra = extract_kml(kmz)
    kml.parent.mkdir(parents=True, exist_ok=True)
    kml.write_bytes(data)
    return extra


def kml_to_kmz(kml: str | Path, kmz: str | Path, force: bool = False) -> None:
    """Empaqueta un KML como doc.kml en un KMZ reproducible."""
    kmz = _check_output(kmz, force)
    data = Path(kml).read_bytes()
    try:
        ET.fromstring(data)
    except ET.ParseError as e:
        raise ReadError(f"{kml}: no es un KML válido: {e}") from None
    write_kmz(data, kmz)


def _check_output(path: str | Path, force: bool) -> Path:
    path = Path(path)
    if path.exists() and not force:
        raise FileExistsError(f"{path} ya existe; usá --force para pisarlo")
    return path
