"""Registro de cambios entre dos versiones del mapa, agrupado por ferrocarril."""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from ferromapas.compare import _item_changes, _pair, _description_change, semantic_items
from ferromapas.model import Folder

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
GENERAL = "(general)"  # elementos que no cuelgan de ningún ferrocarril


class ChangelogError(Exception):
    pass


@dataclass
class RailwayChanges:
    name: str
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


def _railway(path: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    """Ferrocarril (país / ferrocarril) y ruta restante dentro de él.

    Con `ignore_top_level`, la ruta empieza en el país.
    """
    if len(path) < 2:
        return (path[0] if path else GENERAL), ()
    return f"{path[0]} / {path[1]}", path[2:]


def _label(rest: tuple[str, ...], name: str) -> str:
    return " / ".join((*rest, name)) if name else " / ".join(rest)


def diff_by_railway(old: Folder, new: Folder) -> list[RailwayChanges]:
    """Diferencias entre dos modelos, agrupadas por ferrocarril y ordenadas por nombre.

    Un renombre o un movimiento aparece como eliminado + agregado: los placemarks
    no tienen identificador propio (ver PLAN.md).
    """
    items_old, folders_old = semantic_items(old, ignore_top_level=True)
    items_new, folders_new = semantic_items(new, ignore_top_level=True)
    groups: dict[str, RailwayChanges] = {}

    def group(path: tuple[str, ...]) -> tuple[RailwayChanges, tuple[str, ...]]:
        name, rest = _railway(path)
        return groups.setdefault(name, RailwayChanges(name)), rest

    folder_pairs, folders_removed, folders_added = _pair(
        sorted((folders_old - folders_new).elements()),
        sorted((folders_new - folders_old).elements()),
        key=lambda f: f[0],
    )
    for fa, fb in folder_pairs:
        g, rest = group(fa[0])
        where = _label(rest, "") or "(ferrocarril)"
        g.changed.append(f"Carpeta {where}: {_description_change(fa[1], fb[1])}")
    for f in folders_removed:
        g, rest = group(f[0])
        if rest:  # la carpeta del ferrocarril en sí se informa por sus elementos
            g.removed.append(f"Carpeta {_label(rest, '')}")
    for f in folders_added:
        g, rest = group(f[0])
        if rest:
            g.added.append(f"Carpeta {_label(rest, '')}")

    item_pairs, items_removed, items_added = _pair(
        sorted((items_old - items_new).elements()),
        sorted((items_new - items_old).elements()),
        key=lambda i: (i[0], i[1], i[3]),
    )
    for ia, ib in item_pairs:
        g, rest = group(ia[0])
        g.changed.append(f"{_label(rest, ia[1])}: {_item_changes(ia, ib)}")
    for item in items_removed:
        g, rest = group(item[0])
        g.removed.append(_label(rest, item[1]))
    for item in items_added:
        g, rest = group(item[0])
        g.added.append(_label(rest, item[1]))

    result = [g for _, g in sorted(groups.items()) if g.added or g.changed or g.removed]
    for g in result:
        g.added.sort()
        g.changed.sort()
        g.removed.sort()
    return result


def build_entry(version: str, when: date, railways: list[RailwayChanges], notes: str = "") -> dict:
    """Entrada del registro (lo que se serializa a YAML)."""
    return {
        "version": version,
        "date": when,
        "notes": notes,
        "summary": {
            "added": sum(len(r.added) for r in railways),
            "changed": sum(len(r.changed) for r in railways),
            "removed": sum(len(r.removed) for r in railways),
        },
        "railways": [
            {"name": r.name, "added": r.added, "changed": r.changed, "removed": r.removed} for r in railways
        ],
    }


class _Dumper(yaml.SafeDumper):
    pass


def _str_representer(dumper: yaml.SafeDumper, value: str):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str_representer)


def dump_entry(entry: dict) -> str:
    return yaml.dump(entry, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=120)


def write_entry(out_dir: str | Path, entry: dict, force: bool = False) -> Path:
    """Escribe `<version>.yaml`. Si ya existe, conserva sus notas y lo pisa solo con `force`."""
    version = entry["version"]
    if not VERSION_RE.match(version):
        raise ChangelogError(f"versión inválida {version!r}: se espera X.Y.Z")
    path = Path(out_dir) / f"{version}.yaml"
    if path.exists():
        if not force:
            raise ChangelogError(f"{path} ya existe (usá --force para regenerarlo; se conservan las notas)")
        previous = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entry = {**entry, "notes": previous.get("notes", entry["notes"])}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_entry(entry), encoding="utf-8")
    return path
