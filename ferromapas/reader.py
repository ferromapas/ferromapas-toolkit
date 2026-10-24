"""Lector de KML/KMZ: archivo de Google Earth o del repo -> modelo."""

import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from ferromapas.model import (
    Coord,
    Folder,
    Geometry,
    LineString,
    Placemark,
    Point,
    Polygon,
)

KML_NAMESPACES = {
    "http://www.opengis.net/kml/2.2",
    "http://earth.google.com/kml/2.2",
    "http://earth.google.com/kml/2.1",
    "http://earth.google.com/kml/2.0",
}
GX_NAMESPACE = "http://www.google.com/kml/ext/2.2"
ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"

# Se descartan en silencio (PLAN.md §1), pero se cuentan para el resumen.
DISCARDED_COMMON = {
    "Style", "StyleMap", "styleUrl", "open", "visibility", "LookAt", "Camera",
    "Snippet", "TimeStamp", "Region", "ExtendedData", "Schema",
}  # fmt: skip
DISCARDED_IN_GEOMETRY = {"altitudeMode", "tessellate", "extrude"}
# Descartados por prefijo de namespace (gx:*, atom:*).
DISCARDED_PREFIXES = ("gx:", "atom:")

GEOMETRY_TAGS = {"Point", "LineString", "Polygon"}
# Elementos de KML que están fuera del alcance: error con mensaje explícito.
UNSUPPORTED_TAGS = {
    "GroundOverlay", "ScreenOverlay", "PhotoOverlay", "NetworkLink",
    "MultiGeometry", "Model", "gx:Tour", "gx:Track", "gx:MultiTrack",
}  # fmt: skip

# Campos de los elementos tipados por Schema (estaciones FEPSA).
SCHEMA_FIELDS_DISCARDED = {"latitud", "longitud"}
SCHEMA_FIELD_APPENDED = "Est"
SCHEMA_APPENDED_LABEL = "Nombre FEPSA"


class ReadError(Exception):
    """Elemento KML no soportado o inválido; incluye la ruta de carpetas."""


@dataclass
class ReadReport:
    """Resumen de lo leído y de lo descartado."""

    folders: int = 0
    points: int = 0
    linestrings: int = 0
    polygons: int = 0
    converted: int = 0  # elementos tipados por Schema convertidos a Placemark
    discarded: Counter[str] = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Carpetas: {self.folders}",
            f"LineString: {self.linestrings}",
            f"Point: {self.points} (de los cuales {self.converted} convertidos de Schema)",
            f"Polygon: {self.polygons}",
        ]
        if self.discarded:
            lines.append("Descartado:")
            lines += [f"  {tag}: {n}" for tag, n in sorted(self.discarded.items())]
        lines += [f"Aviso: {w}" for w in self.warnings]
        return "\n".join(lines)


def read(path: str | Path) -> tuple[Folder, ReadReport]:
    """Lee un .kml o .kmz y devuelve la carpeta raíz (el Document) y el resumen."""
    path = Path(path)
    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            inner = "doc.kml" if "doc.kml" in names else next(
                (n for n in names if n.lower().endswith(".kml")), None
            )
            if inner is None:
                raise ReadError(f"{path}: el KMZ no contiene ningún .kml")
            data = zf.read(inner)
    else:
        data = path.read_bytes()
    return read_bytes(data)


def read_bytes(data: bytes) -> tuple[Folder, ReadReport]:
    """Lee el contenido de un KML ya cargado en memoria."""
    return _Reader().read(ET.fromstring(data))


def _tag(element: ET.Element) -> str:
    """Nombre local; `gx:`/`atom:` llevan prefijo. Namespace desconocido => error."""
    raw = element.tag
    if not raw.startswith("{"):
        return raw
    ns, _, local = raw[1:].partition("}")
    if ns in KML_NAMESPACES:
        return local
    if ns == GX_NAMESPACE:
        return f"gx:{local}"
    if ns == ATOM_NAMESPACE:
        return f"atom:{local}"
    raise ReadError(f"namespace desconocido: {ns} (elemento {local})")


def _text(element: ET.Element) -> str:
    return (element.text or "").replace("\r\n", "\n").replace("\r", "\n")


def _description(element: ET.Element) -> str | None:
    text = _text(element)
    return text if text.strip() else None


def _coords(element: ET.Element, where: str) -> list[Coord]:
    result = []
    for token in _text(element).split():
        parts = token.split(",")
        if len(parts) not in (2, 3):
            raise ReadError(f"{where}: coordenada inválida {token!r}")
        try:
            result.append((float(parts[0]), float(parts[1])))
        except ValueError:
            raise ReadError(f"{where}: coordenada inválida {token!r}") from None
    return result


class _Reader:
    def __init__(self) -> None:
        self.report = ReadReport()
        self.schemas: set[str] = set()

    def read(self, kml: ET.Element) -> tuple[Folder, ReadReport]:
        if _tag(kml) != "kml":
            raise ReadError(f"el elemento raíz es <{_tag(kml)}>, se esperaba <kml>")
        # Los Schema con parent="Placemark" se necesitan antes de recorrer las carpetas.
        for el in kml.iter():
            if el.tag.rpartition("}")[2] == "Schema" and el.get("parent") == "Placemark":
                self.schemas.add(el.get("name", ""))
        containers = [e for e in kml if _tag(e) in ("Document", "Folder")]
        if len(containers) != 1:
            raise ReadError("el <kml> debe tener exactamente un Document o Folder")
        for e in kml:
            if e is not containers[0]:
                self._discard_or_fail(e, "<kml>")
        root = self._folder(containers[0], [], is_root=True)
        return root, self.report

    def _discard_or_fail(self, element: ET.Element, path: str) -> None:
        tag = _tag(element)
        if tag in UNSUPPORTED_TAGS:
            raise ReadError(f"{path}: elemento no soportado <{tag}>")
        if tag in DISCARDED_COMMON or tag.startswith(DISCARDED_PREFIXES):
            self.report.discarded[tag] += 1
        else:
            raise ReadError(f"{path}: elemento desconocido <{tag}>")

    def _folder(self, element: ET.Element, parent_path: list[str], is_root=False) -> Folder:
        name_el = element.find("{*}name")
        name = _text(name_el).strip() if name_el is not None else ""
        path_list = [*parent_path, name]
        path = " / ".join(path_list)
        if not is_root:
            self.report.folders += 1
        folder = Folder(name=name)
        for child in element:
            tag = _tag(child)
            if tag == "name":
                continue
            if tag == "description":
                folder.description = _description(child)
            elif tag == "Folder":
                folder.children.append(self._folder(child, path_list))
            elif tag == "Placemark":
                placemark = self._placemark(child, path)
                if placemark is not None:
                    folder.children.append(placemark)
            elif tag in self.schemas:
                folder.children.append(self._typed_placemark(child, tag, path))
            else:
                self._discard_or_fail(child, path)
        return folder

    def _placemark(self, element: ET.Element, path: str) -> Placemark | None:
        name = ""
        description = None
        geometries: list[Geometry] = []
        for child in element:
            tag = _tag(child)
            if tag == "name":
                name = _text(child).strip()
            elif tag == "description":
                description = _description(child)
            elif tag in GEOMETRY_TAGS:
                geometries.append(self._geometry(child, tag, f"{path} / {name}"))
            else:
                self._discard_or_fail(child, f"{path} / {name}")
        if not geometries:
            self.report.warnings.append(f"{path}: placemark {name!r} sin geometría, se descarta")
            return None
        if len(geometries) > 1:
            raise ReadError(f"{path} / {name}: placemark con más de una geometría")
        return Placemark(name, description, geometries[0])

    def _typed_placemark(self, element: ET.Element, schema: str, path: str) -> Placemark:
        """Convierte un elemento KML 2.1 tipado por Schema en un Placemark."""
        name = ""
        description = None
        appended = None
        geometries: list[Geometry] = []
        for child in element:
            tag = _tag(child)
            if tag == "name":
                name = _text(child).strip()
            elif tag == "description":
                description = _description(child)
            elif tag in GEOMETRY_TAGS:
                geometries.append(self._geometry(child, tag, f"{path} / {name}"))
            elif tag in SCHEMA_FIELDS_DISCARDED:
                self.report.discarded[f"{schema}.{tag}"] += 1
            elif tag == SCHEMA_FIELD_APPENDED:
                appended = _text(child).strip()
            else:
                self._discard_or_fail(child, f"{path} / {name}")
        if len(geometries) != 1:
            raise ReadError(f"{path} / {name}: {schema} debe tener exactamente una geometría")
        if appended:
            line = f"{SCHEMA_APPENDED_LABEL}: {appended}"
            description = f"{description.rstrip()}\n{line}" if description else line
        self.report.converted += 1
        return Placemark(name, description, geometries[0])

    def _geometry(self, element: ET.Element, tag: str, path: str) -> Geometry:
        where = f"{path} <{tag}>"
        coords: list[Coord] | None = None
        outer: list[Coord] | None = None
        inners: list[list[Coord]] = []
        for child in element:
            ctag = _tag(child)
            if ctag == "coordinates" and tag != "Polygon":
                coords = _coords(child, where)
            elif ctag == "outerBoundaryIs" and tag == "Polygon":
                outer = self._ring(child, where)
            elif ctag == "innerBoundaryIs" and tag == "Polygon":
                inners.append(self._ring(child, where))
            elif ctag in DISCARDED_IN_GEOMETRY or (
                ctag.startswith(DISCARDED_PREFIXES) and ctag not in UNSUPPORTED_TAGS
            ):
                self.report.discarded[ctag] += 1
            else:
                self._discard_or_fail_geometry(child, where)
        if tag == "Point":
            if not coords or len(coords) != 1:
                raise ReadError(f"{where}: un Point necesita exactamente una coordenada")
            self.report.points += 1
            return Point(coords[0])
        if tag == "LineString":
            if coords is None:
                raise ReadError(f"{where}: LineString sin coordenadas")
            self.report.linestrings += 1
            return LineString(coords)
        if outer is None:
            raise ReadError(f"{where}: Polygon sin outerBoundaryIs")
        self.report.polygons += 1
        return Polygon(outer, inners)

    def _ring(self, element: ET.Element, where: str) -> list[Coord]:
        rings = [c for c in element if _tag(c) == "LinearRing"]
        if len(rings) != 1 or len(element) != 1:
            raise ReadError(f"{where}: se esperaba un único LinearRing")
        ring = rings[0]
        coords: list[Coord] | None = None
        for child in ring:
            ctag = _tag(child)
            if ctag == "coordinates":
                coords = _coords(child, where)
            elif ctag in DISCARDED_IN_GEOMETRY or ctag.startswith(DISCARDED_PREFIXES):
                self.report.discarded[ctag] += 1
            else:
                self._discard_or_fail_geometry(child, where)
        if coords is None:
            raise ReadError(f"{where}: LinearRing sin coordenadas")
        return coords

    def _discard_or_fail_geometry(self, element: ET.Element, where: str) -> None:
        tag = _tag(element)
        if tag in UNSUPPORTED_TAGS:
            raise ReadError(f"{where}: elemento no soportado <{tag}>")
        raise ReadError(f"{where}: elemento desconocido <{tag}>")
