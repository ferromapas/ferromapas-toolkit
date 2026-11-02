"""folders.yaml -> <Style> de KML y asignación de estilos por prefijo de ruta."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

from ferromapas.model import Folder, Placemark
from ferromapas.tree import _unique_slug, slugify

DEFAULT_STYLE = {
    "color": "#757575",
    "line_width": 2.5,
    "icon": "http://maps.google.com/mapfiles/kml/shapes/shaded_dot.png",
    "icon_scale": 0.4,
    "label_scale": 0.7,
    "polygon_opacity": 0.35,
}
DEFAULT_ID = "default"
STYLE_KEYS = set(DEFAULT_STYLE)
NODE_KEYS = ("styles", "depth", "id")
VALID_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")


class StylesError(Exception):
    """folders.yaml inválido."""


@dataclass
class Styles:
    default: dict = field(default_factory=lambda: dict(DEFAULT_STYLE))
    by_prefix: dict[str, dict] = field(default_factory=dict)  # ya combinados con default
    depths: dict[str, int] = field(default_factory=dict)  # prefijo -> profundidad absoluta de directorios
    ids: dict[str, str] = field(default_factory=dict)  # prefijo -> id corto elegido en folders.yaml

    def prefix_for(self, slug_path: str) -> str | None:
        """Prefijo de estilo más largo que aplica a una ruta de slugs."""
        best = None
        for prefix in self.by_prefix:
            if (slug_path == prefix or slug_path.startswith(prefix + "/")) and (
                best is None or len(prefix) > len(best)
            ):
                best = prefix
        return best


def style_id(prefix: str | None, styles: Styles | None = None) -> str:
    """Id del <Style>: el `id` corto de folders.yaml si lo hay; si no, uno largo derivado del prefijo."""
    if prefix is None:
        return DEFAULT_ID
    if styles is not None and prefix in styles.ids:
        return styles.ids[prefix]
    return "s-" + prefix.replace("/", "--")


def load_styles(path: str | Path) -> Styles:
    """Carga folders.yaml; si no existe, usa solo el estilo por defecto."""
    path = Path(path)
    if not path.exists():
        return Styles()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    top = data.get("styles") or {}
    if not isinstance(top, dict) or set(top) - {"default"}:
        raise StylesError(
            f"{path}: 'styles' solo admite 'default'; los estilos por carpeta van en un árbol anidado bajo 'folders'"
        )
    default = {**DEFAULT_STYLE, **(top.get("default") or {})}
    _check_keys(default, f"{path}: default")
    styles = Styles(default)
    _load_folders(data.get("folders") or {}, [], styles, str(path))
    return styles


def _load_folders(nodes: dict, parents: list[str], styles: Styles, where: str) -> None:
    """Recorre el árbol de carpetas; cada clave es el nombre (o slug) de una carpeta.

    Un nodo puede tener `styles` (estilo para todo lo que está debajo), `id` (nombre corto
    del <Style> generado, requiere `styles`) y `depth` (cuántos niveles por debajo de esa
    carpeta se guardan como directorios). El resto de las claves son subcarpetas.
    """
    if not isinstance(nodes, dict):
        raise StylesError(f"{where}: se esperaba un mapa de carpetas")
    for key, node in nodes.items():
        path = [*parents, slugify(str(key))]
        prefix = "/".join(path)
        node = node or {}
        if not isinstance(node, dict):
            raise StylesError(f"{where}: {prefix}: se esperaba un mapa")
        if "styles" in node:
            override = node["styles"] or {}
            _check_keys(override, f"{where}: {prefix}")
            styles.by_prefix[prefix] = {**styles.default, **override}
        if "id" in node:
            _load_id(node["id"], prefix, styles, where)
        if "depth" in node:
            if not isinstance(node["depth"], int) or isinstance(node["depth"], bool) or node["depth"] < 0:
                raise StylesError(f"{where}: {prefix}: depth debe ser un entero >= 0")
            styles.depths[prefix] = len(path) + node["depth"]
        children = {k: v for k, v in node.items() if k not in NODE_KEYS}
        _load_folders(children, path, styles, where)


def _load_id(value: object, prefix: str, styles: Styles, where: str) -> None:
    if prefix not in styles.by_prefix:
        raise StylesError(f"{where}: {prefix}: 'id' requiere 'styles'")
    if not isinstance(value, str) or not VALID_ID.fullmatch(value):
        raise StylesError(f"{where}: {prefix}: id inválido {value!r} (letras, números, '_', '-' y '.', sin espacios)")
    if value == DEFAULT_ID or value in styles.ids.values():
        raise StylesError(f"{where}: {prefix}: el id {value!r} ya está en uso")
    styles.ids[prefix] = value


def _check_keys(style: dict, where: str) -> None:
    unknown = set(style) - STYLE_KEYS
    if unknown:
        raise StylesError(f"{where}: claves desconocidas {sorted(unknown)}")


def kml_color(color: str, opacity: float = 1.0) -> str:
    """'#RRGGBB' -> 'aabbggrr', el formato de KML."""
    text = color.lstrip("#")
    if len(text) != 6:
        raise StylesError(f"color inválido: {color!r} (se espera #RRGGBB)")
    try:
        int(text, 16)
    except ValueError:
        raise StylesError(f"color inválido: {color!r} (se espera #RRGGBB)") from None
    rr, gg, bb = text[0:2], text[2:4], text[4:6]
    return f"{round(opacity * 255):02x}{bb}{gg}{rr}".lower()


def _number(value: float) -> str:
    return f"{value:g}"


def style_xml(sid: str, style: dict, level: int = 2) -> list[str]:
    """Un <Style> con IconStyle, LabelStyle, LineStyle y PolyStyle."""
    pad = "  " * level
    solid = kml_color(style["color"])
    fill = kml_color(style["color"], style["polygon_opacity"])
    return [
        f'{pad}<Style id="{escape(sid)}">',
        f"{pad}  <IconStyle>",
        f"{pad}    <color>{solid}</color>",
        f"{pad}    <scale>{_number(style['icon_scale'])}</scale>",
        f"{pad}    <Icon><href>{escape(style['icon'])}</href></Icon>",
        f"{pad}  </IconStyle>",
        f"{pad}  <LabelStyle>",
        f"{pad}    <color>{solid}</color>",
        f"{pad}    <scale>{_number(style['label_scale'])}</scale>",
        f"{pad}  </LabelStyle>",
        f"{pad}  <LineStyle>",
        f"{pad}    <color>{solid}</color>",
        f"{pad}    <width>{_number(style['line_width'])}</width>",
        f"{pad}  </LineStyle>",
        f"{pad}  <PolyStyle>",
        f"{pad}    <color>{fill}</color>",
        f"{pad}  </PolyStyle>",
        f"{pad}</Style>",
    ]


def assign_styles(root: Folder, styles: Styles) -> dict[int, str]:
    """{id(placemark): id de estilo}, según el prefijo de slugs de su carpeta."""
    result: dict[int, str] = {}

    def walk(folder: Folder, slug_path: str) -> None:
        used: set[str] = set()
        for child in folder.children:
            if isinstance(child, Placemark):
                result[id(child)] = style_id(styles.prefix_for(slug_path), styles)
                continue
            slug = child.slug if child.slug is not None else _unique_slug(child.name, used)
            used.add(slug)
            walk(child, f"{slug_path}/{slug}" if slug_path else slug)

    walk(root, "")
    return result


def all_style_xml(styles: Styles) -> list[str]:
    lines = style_xml(DEFAULT_ID, styles.default)
    for prefix in sorted(styles.by_prefix):
        lines += style_xml(style_id(prefix, styles), styles.by_prefix[prefix])
    return lines
