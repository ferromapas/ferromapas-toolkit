"""Build: src/ -> KML/KMZ con estilos."""

import zipfile
from pathlib import Path

from ferromapas.model import Folder
from ferromapas.styles import Styles, all_style_xml, assign_styles
from ferromapas.writer import styled_document

# Fecha fija para que el KMZ sea reproducible.
ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def build_kml(root: Folder, styles: Styles) -> str:
    """Documento KML completo con los estilos aplicados por prefijo."""
    style_ids = assign_styles(root, styles)
    return styled_document(root, all_style_xml(styles), lambda pm: style_ids[id(pm)])


def write_kmz(kml: str, output: str | Path) -> None:
    """Empaqueta el KML como doc.kml dentro de un ZIP determinístico."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    info = zipfile.ZipInfo("doc.kml", ZIP_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    with zipfile.ZipFile(output, "w") as zf:
        zf.writestr(info, kml.encode("utf-8"))


def write_kml(kml: str, output: str | Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(kml.encode("utf-8"))
