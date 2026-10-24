"""Validación de src/: errores (rompen el build o el formato) y avisos."""

from dataclasses import dataclass, field
from pathlib import Path

from ferromapas.model import Folder, LineString, Placemark, Point, Polygon
from ferromapas.reader import ReadError, read_bytes
from ferromapas.tree import TreeError, load_tree
from ferromapas.writer import folder_document

LON_RANGE = (-80.0, -50.0)
LAT_RANGE = (-60.0, -15.0)
MIN_LINE_VERTICES = 2
MIN_RING_VERTICES = 4


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def exit_code(self, strict: bool = False) -> int:
        return 1 if self.errors or (strict and self.warnings) else 0


def validate(src: str | Path) -> ValidationReport:
    src = Path(src)
    report = ValidationReport()
    if not src.is_dir():
        report.errors.append(f"{src}: no existe el directorio")
        return report
    _check_normalized(src, report)
    try:
        root, load_warnings = load_tree(src)
    except (TreeError, ReadError) as e:
        report.errors.append(str(e))
        return report
    report.warnings += load_warnings
    _check_folder(root, (), report)
    return report


def _check_normalized(src: Path, report: ValidationReport) -> None:
    """Cada .kml debe ser idéntico a lo que escribiría el programa."""
    for path in sorted(src.rglob("*.kml")):
        rel = path.relative_to(src).as_posix()
        data = path.read_bytes()
        try:
            folder, _ = read_bytes(data)
        except (ReadError, ValueError) as e:  # ValueError incluye errores de parseo XML
            report.errors.append(f"{rel}: no se pudo leer: {e}")
            continue
        if folder_document(folder).encode("utf-8") != data:
            report.errors.append(f"{rel}: no está normalizado (correr `ferromapas fmt`)")


def _check_folder(folder: Folder, parent: tuple[str, ...], report: ValidationReport) -> None:
    path = (*parent, folder.name)
    where = " / ".join(path)
    if not folder.children:
        report.warnings.append(f"{where}: carpeta vacía")
    for child in folder.children:
        if isinstance(child, Folder):
            _check_folder(child, path, report)
        else:
            _check_placemark(child, where, report)


def _coords(placemark: Placemark):
    g = placemark.geometry
    if isinstance(g, Point):
        return [g.coord]
    if isinstance(g, LineString):
        return g.coords
    return [c for ring in (g.outer, *g.inners) for c in ring]


def _check_placemark(placemark: Placemark, where: str, report: ValidationReport) -> None:
    label = f"{where} / {placemark.name!r}"
    g = placemark.geometry
    if not placemark.name:
        report.warnings.append(f"{where}: placemark sin nombre")
    for lon, lat in _coords(placemark):
        if not (LON_RANGE[0] <= lon <= LON_RANGE[1] and LAT_RANGE[0] <= lat <= LAT_RANGE[1]):
            report.errors.append(f"{label}: coordenada fuera de la caja ({lon}, {lat})")
            break  # una sola vez por placemark
    if isinstance(g, LineString) and len(g.coords) < MIN_LINE_VERTICES:
        report.warnings.append(f"{label}: LineString con {len(g.coords)} vértice(s)")
    if isinstance(g, Polygon):
        for ring in (g.outer, *g.inners):
            if len(ring) < MIN_RING_VERTICES:
                report.warnings.append(f"{label}: anillo con {len(ring)} vértices")
