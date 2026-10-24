"""Escritor de KML normalizado y determinístico (PLAN.md §1, Normalización)."""

from xml.sax.saxutils import escape

from ferromapas.model import Coord, Folder, Geometry, LineString, Placemark, Point, Polygon

HEADER = '<?xml version="1.0" encoding="UTF-8"?>'
KML_OPEN = '<kml xmlns="http://www.opengis.net/kml/2.2">'
INDENT = "  "


def _number(value: float) -> str:
    text = f"{value:.6f}"
    return "0.000000" if text == "-0.000000" else text


def format_coord(coord: Coord) -> str:
    """lon,lat con 6 decimales."""
    return f"{_number(coord[0])},{_number(coord[1])}"


def folder_document(folder: Folder) -> str:
    """KML válido por sí mismo: <kml><Folder>…</Folder></kml>."""
    lines = [HEADER, KML_OPEN]
    _folder(folder, 1, lines)
    lines.append("</kml>")
    return "\n".join(lines) + "\n"


def _folder(folder: Folder, level: int, out: list[str]) -> None:
    pad = INDENT * level
    out.append(f"{pad}<Folder>")
    out.append(f"{pad}{INDENT}<name>{escape(folder.name)}</name>")
    if folder.description:
        out.append(f"{pad}{INDENT}<description>{escape(folder.description)}</description>")
    for child in folder.children:
        if isinstance(child, Folder):
            _folder(child, level + 1, out)
        else:
            _placemark(child, level + 1, out)
    out.append(f"{pad}</Folder>")


def _placemark(placemark: Placemark, level: int, out: list[str]) -> None:
    pad = INDENT * level
    out.append(f"{pad}<Placemark>")
    out.append(f"{pad}{INDENT}<name>{escape(placemark.name)}</name>")
    if placemark.description:
        out.append(f"{pad}{INDENT}<description>{escape(placemark.description)}</description>")
    _geometry(placemark.geometry, level + 1, out)
    out.append(f"{pad}</Placemark>")


def _coordinates(coords: list[Coord], level: int, out: list[str]) -> None:
    pad = INDENT * level
    out.append(f"{pad}<coordinates>")
    out.extend(f"{pad}{INDENT}{format_coord(c)}" for c in coords)
    out.append(f"{pad}</coordinates>")


def _ring(tag: str, coords: list[Coord], level: int, out: list[str]) -> None:
    pad = INDENT * level
    out.append(f"{pad}<{tag}>")
    out.append(f"{pad}{INDENT}<LinearRing>")
    _coordinates(coords, level + 2, out)
    out.append(f"{pad}{INDENT}</LinearRing>")
    out.append(f"{pad}</{tag}>")


def _geometry(geometry: Geometry, level: int, out: list[str]) -> None:
    pad = INDENT * level
    if isinstance(geometry, Point):
        out.append(f"{pad}<Point><coordinates>{format_coord(geometry.coord)}</coordinates></Point>")
    elif isinstance(geometry, LineString):
        out.append(f"{pad}<LineString>")
        _coordinates(geometry.coords, level + 1, out)
        out.append(f"{pad}</LineString>")
    elif isinstance(geometry, Polygon):
        out.append(f"{pad}<Polygon>")
        _ring("outerBoundaryIs", geometry.outer, level + 1, out)
        for inner in geometry.inners:
            _ring("innerBoundaryIs", inner, level + 1, out)
        out.append(f"{pad}</Polygon>")
    else:
        raise TypeError(f"geometría desconocida: {geometry!r}")
