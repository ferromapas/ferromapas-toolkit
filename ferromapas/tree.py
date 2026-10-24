"""Modelo <-> árbol de archivos en src/ (directorios, yaml y .kml)."""

import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

import yaml

from ferromapas.config import Config
from ferromapas.model import Folder, Placemark
from ferromapas.writer import folder_document

LOOSE = "_loose.kml"
FOLDER_YAML = "_folder.yaml"
DOCUMENT_YAML = "_document.yaml"
KNOWN_KEYS = ("name", "description", "children")
MAX_SLUG_LENGTH = 100


class SplitError(Exception):
    """No se pudo regenerar src/."""


class _Dumper(yaml.SafeDumper):
    pass


def _represent_str(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    # Las descripciones multilínea van como bloque literal `|`.
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _represent_str)


def slugify(name: str) -> str:
    """Slug ASCII: 'Río Tercero - Córdoba' -> 'rio-tercero-cordoba'."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:MAX_SLUG_LENGTH].strip("-")
    return text or "sin-nombre"


def _unique_slug(name: str, used: set[str]) -> str:
    base = slugify(name)
    slug, n = base, 2
    while slug in used:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def _is_directory(folder: Folder, slug_path: str, depth: int, config: Config) -> bool:
    """Directorio si depth <= tope y además tiene subcarpetas (PLAN.md §1)."""
    return depth <= config.depth_for(slug_path) and any(isinstance(c, Folder) for c in folder.children)


def render_tree(
    root: Folder, config: Config, extras: dict[str, dict] | None = None
) -> dict[str, str]:
    """Devuelve {ruta relativa a src/: contenido} sin tocar el disco.

    `extras` son las claves adicionales de _folder.yaml/_document.yaml previos,
    por ruta relativa, que se conservan.
    """
    files: dict[str, str] = {}
    _render_directory(root, "", "", 0, config, extras or {}, files)
    return files


def _render_directory(
    folder: Folder,
    rel_dir: str,
    slug_path: str,
    depth: int,
    config: Config,
    extras: dict[str, dict],
    files: dict[str, str],
) -> None:
    used: set[str] = set()
    entries: list[str] = []
    loose: list[Placemark] = []
    for child in folder.children:
        if isinstance(child, Placemark):
            if not loose:
                entries.append(LOOSE)  # todos los sueltos van juntos, en el lugar del primero
            loose.append(child)
            continue
        slug = _unique_slug(child.name, used)
        child_path = f"{slug_path}/{slug}" if slug_path else slug
        if _is_directory(child, child_path, depth + 1, config):
            entries.append(f"{slug}/")
            _render_directory(child, f"{rel_dir}{slug}/", child_path, depth + 1, config, extras, files)
        else:
            entries.append(f"{slug}.kml")
            files[f"{rel_dir}{slug}.kml"] = folder_document(child)
    if loose:
        files[f"{rel_dir}{LOOSE}"] = folder_document(Folder(folder.name, None, list(loose)))

    meta: dict = {"name": folder.name}
    if folder.description:
        meta["description"] = folder.description
    meta["children"] = entries
    yaml_name = DOCUMENT_YAML if depth == 0 else FOLDER_YAML
    meta.update(extras.get(f"{rel_dir}{yaml_name}", {}))
    files[f"{rel_dir}{yaml_name}"] = yaml.dump(
        meta, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=1_000_000
    )


def read_extras(src: Path) -> dict[str, dict]:
    """Claves de yaml distintas de name/description/children, por ruta relativa."""
    extras: dict[str, dict] = {}
    if not src.is_dir():
        return extras
    for path in sorted(src.rglob("*.yaml")):
        if path.name not in (FOLDER_YAML, DOCUMENT_YAML):
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        extra = {k: v for k, v in data.items() if k not in KNOWN_KEYS}
        if extra:
            extras[path.relative_to(src).as_posix()] = extra
    return extras


def _check_clean(src: Path) -> None:
    """Se niega a seguir si hay cambios sin commitear en src/ (ver --force)."""
    cwd = src.parent if src.parent.is_dir() else Path.cwd()
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", src.name],
            cwd=cwd, capture_output=True, text=True,
        )  # fmt: skip
    except FileNotFoundError:
        return
    if result.returncode == 0 and result.stdout.strip():
        raise SplitError(
            f"hay cambios sin commitear en {src}; hacé commit o usá --force:\n{result.stdout.rstrip()}"
        )


def split(root: Folder, src: str | Path, config: Config, force: bool = False) -> int:
    """Borra y regenera src/. Devuelve la cantidad de archivos escritos."""
    src = Path(src)
    if not force:
        _check_clean(src)
    files = render_tree(root, config, read_extras(src))
    if src.exists():
        shutil.rmtree(src)
    for rel, content in files.items():
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
    return len(files)
