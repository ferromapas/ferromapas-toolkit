"""Comparación semántica entre dos fuentes (.kmz, .kml o directorio src)."""

from collections import Counter
from dataclasses import dataclass, field
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


def semantic_items(
    root: Folder, ignore_top_level: bool = False
) -> tuple[Counter[Item], Counter[FolderKey]]:
    """Multiconjuntos de placemarks y de carpetas, independientes del orden.

    Con `ignore_top_level`, el nombre de las carpetas de primer nivel no entra
    en las rutas (sirve para comparar versiones que lo renombraron).
    """
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

    # El nombre de la raíz no cuenta: suele ser el del archivo.
    if ignore_top_level:
        for child in root.children:
            if isinstance(child, Folder):
                walk(child, ())
            else:
                walk(Folder("", None, [child]), ())
    else:
        walk(root, ())
    return items, folders


@dataclass
class Diff:
    only_a: list[str]
    only_b: list[str]
    changed: list[str] = field(default_factory=list)  # mismo elemento, contenido distinto

    def __bool__(self) -> bool:
        return bool(self.only_a or self.only_b or self.changed)


def _path(path: tuple[str, ...]) -> str:
    return " / ".join(path) or "(raíz)"


def _short(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _vertices(coords: tuple[str, ...]) -> int:
    return sum(1 for c in coords if c != "|")  # "|" separa los anillos de un Polygon


def _describe_item(item: Item) -> str:
    path, name, _, kind, coords = item
    first = coords[0] if coords else "sin coordenadas"
    return f"{_path(path)} / {name!r} [{kind}, {_vertices(coords)} coord., {first}]"


def _description_change(old: str, new: str) -> str:
    return f"descripción: {_short(old)!r} → {_short(new)!r}"


def _item_changes(a: Item, b: Item) -> str:
    """Qué cambió entre dos placemarks de la misma ruta, nombre y tipo."""
    changes = []
    if a[2] != b[2]:
        changes.append(_description_change(a[2], b[2]))
    ca, cb = a[4], b[4]
    if ca != cb:
        na, nb = _vertices(ca), _vertices(cb)
        if na == nb == 1:
            changes.append(f"coordenada: {ca[0]} → {cb[0]}")
        elif na != nb:
            changes.append(f"vértices: {na} → {nb}")
        elif len(ca) == len(cb):
            different = sum(1 for x, y in zip(ca, cb) if x != y)
            changes.append(f"{different} de {na} vértices distintos")
        else:
            changes.append("anillos distintos")
    return "; ".join(changes)


def _pair(left: list, right: list, key) -> tuple[list[tuple], list, list]:
    """Empareja elementos de ambos lados con la misma clave; devuelve (pares, sobrantes_izq, sobrantes_der)."""
    pending: dict = {}
    for item in right:
        pending.setdefault(key(item), []).append(item)
    pairs, rest_left = [], []
    for item in left:
        candidates = pending.get(key(item))
        if candidates:
            pairs.append((item, candidates.pop(0)))
        else:
            rest_left.append(item)
    rest_right = [item for items in pending.values() for item in items]
    return pairs, rest_left, sorted(rest_right)


def compare(a: Folder, b: Folder, ignore_top_level: bool = False) -> Diff:
    """Diferencias entre dos modelos: elementos solo en uno, o presentes en ambos pero modificados."""
    items_a, folders_a = semantic_items(a, ignore_top_level)
    items_b, folders_b = semantic_items(b, ignore_top_level)
    changed: list[str] = []

    folder_pairs, only_folders_a, only_folders_b = _pair(
        sorted((folders_a - folders_b).elements()),
        sorted((folders_b - folders_a).elements()),
        key=lambda f: f[0],
    )
    for fa, fb in folder_pairs:
        changed.append(f"Carpeta: {_path(fa[0])}: {_description_change(fa[1], fb[1])}")

    item_pairs, only_items_a, only_items_b = _pair(
        sorted((items_a - items_b).elements()),
        sorted((items_b - items_a).elements()),
        key=lambda i: (i[0], i[1], i[3]),
    )
    for ia, ib in item_pairs:
        changed.append(f"{_path(ia[0])} / {ia[1]!r} [{ia[3]}]: {_item_changes(ia, ib)}")

    return Diff(
        [f"Carpeta: {_path(f[0])}" for f in only_folders_a] + [_describe_item(i) for i in only_items_a],
        [f"Carpeta: {_path(f[0])}" for f in only_folders_b] + [_describe_item(i) for i in only_items_b],
        changed,
    )
