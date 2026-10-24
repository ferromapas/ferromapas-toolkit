"""Comparación semántica entre dos fuentes (.kmz, .kml o directorio src)."""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ferromapas.model import Folder, LineString, Placemark, Point, Polygon
from ferromapas.reader import read
from ferromapas.tree import load_tree
from ferromapas.writer import format_coord

# (camino de carpetas, nombre, descripción, tipo, coordenadas a 6 decimales)
Item = tuple[tuple[str, ...], str, str, str, tuple[str, ...]]
# (camino de carpetas, descripción)
FolderKey = tuple[tuple[str, ...], str]


def load_source(path: str | Path) -> Folder:
    """Lee un .kmz, un .kml o un directorio src."""
    path = Path(path)
    if path.is_dir():
        return load_tree(path)[0]
    return read(path)[0]


def _coords(geometry) -> tuple[str, ...]:
    if isinstance(geometry, Point):
        return (format_coord(geometry.coord),)
    if isinstance(geometry, LineString):
        return tuple(format_coord(c) for c in geometry.coords)
    if isinstance(geometry, Polygon):
        rings = [geometry.outer, *geometry.inners]
        return tuple(x for ring in rings for x in [*(format_coord(c) for c in ring), "|"])
    raise TypeError(geometry)


def semantic_items(root: Folder) -> tuple[Counter[Item], Counter[FolderKey]]:
    """Multiconjuntos de placemarks y de carpetas, independientes del orden."""
    items: Counter[Item] = Counter()
    folders: Counter[FolderKey] = Counter()

    def walk(folder: Folder, path: tuple[str, ...]) -> None:
        folders[(path, folder.description or "")] += 1
        for child in folder.children:
            if isinstance(child, Folder):
                walk(child, (*path, child.name))
            else:
                g = child.geometry
                items[(path, child.name, child.description or "", type(g).__name__, _coords(g))] += 1

    walk(root, (root.name,))
    return items, folders


@dataclass
class Diff:
    only_a: list[str]
    only_b: list[str]

    def __bool__(self) -> bool:
        return bool(self.only_a or self.only_b)


def _describe_item(item: Item) -> str:
    path, name, _, kind, coords = item
    return f"{' / '.join(path)} / {name!r} [{kind}, {len(coords)} coord., {coords[0]}]"


def compare(a: Folder, b: Folder) -> Diff:
    """Diferencias entre dos modelos; cada línea indica en cuál de los dos está."""
    items_a, folders_a = semantic_items(a)
    items_b, folders_b = semantic_items(b)
    only_a = [f"Carpeta: {' / '.join(k[0])}" + (" (otra descripción)" if k[1] else "")
              for k in sorted((folders_a - folders_b).elements())]  # fmt: skip
    only_b = [f"Carpeta: {' / '.join(k[0])}" + (" (otra descripción)" if k[1] else "")
              for k in sorted((folders_b - folders_a).elements())]  # fmt: skip
    only_a += [_describe_item(i) for i in sorted((items_a - items_b).elements())]
    only_b += [_describe_item(i) for i in sorted((items_b - items_a).elements())]
    return Diff(only_a, only_b)
