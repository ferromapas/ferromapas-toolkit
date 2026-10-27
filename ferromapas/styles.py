"""folders.yaml -> <Style> de KML y asignación de estilos por prefijo de ruta."""

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


class StylesError(Exception):
    """folders.yaml inválido."""


@dataclass
class Styles:
    default: dict = field(default_factory=lambda: dict(DEFAULT_STYLE))
    by_prefix: dict[str, dict] = field(default_factory=dict)  # ya combinados con default
    depths: dict[str, int] = field(default_factory=dict)  # prefijo -> profundidad absoluta de directorios

    def prefix_for(self, slug_path: str) -> str | None:
        """Prefijo de estilo más largo que aplica a una ruta de slugs."""
        best = None
        for prefix in self.by_prefix:
            if (slug_path == prefix or slug_path.startswith(prefix + "/")) and (
                best is None or len(prefix) > len(best)
            ):
                best = prefix
        return best


def style_id(prefix: str | None) -> str:
    return DEFAULT_ID if prefix is None else "s-" + prefix.replace("/", "--")


def load_styles(path: str | Path) -> Styles:
    """Carga folders.yaml; si no existe, usa solo el estilo por defecto."""
    path = Path(path)
    if not path.exists():
        return Styles()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "styles" in data:
        raise StylesError(f"{path}: 'styles' ya no existe; usá un árbol de carpetas anidadas bajo 'folders'")
    default = {**DEFAULT_STYLE, **(data.get("default") or {})}
    _check_keys(default, f"{path}: default")
    styles = Styles(default)
    _load_folders(data.get("folders") or {}, [], styles, str(path))
    return styles


def _load_folders(nodes: dict, parents: list[str], styles: Styles, where: str) -> None:
    """Recorre el árbol de carpetas; cada clave es el nombre (o slug) de una carpeta.

    Un nodo puede tener `styles` (estilo para todo lo que está debajo) y `depth` (cuántos
    niveles por debajo de esa carpeta se guardan como directorios). El resto de las claves
    son subcarpetas.
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
        if "depth" in node:
            if not isinstance(node["depth"], int) or isinstance(node["depth"], bool) or node["depth"] < 0:
                raise StylesError(f"{where}: {prefix}: depth debe ser un entero >= 0")
            styles.depths[prefix] = len(path) + node["depth"]
        children = {k: v for k, v in node.items() if k not in ("styles", "depth")}
        _load_folders(children, path, styles, where)


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
                result[id(child)] = style_id(styles.prefix_for(slug_path))
                continue
            slug = child.slug if child.slug is not None else _unique_slug(child.name, used)
            used.add(slug)
            walk(child, f"{slug_path}/{slug}" if slug_path else slug)

    walk(root, "")
    return result


def all_style_xml(styles: Styles) -> list[str]:
    lines = style_xml(DEFAULT_ID, styles.default)
    for prefix in sorted(styles.by_prefix):
        lines += style_xml(style_id(prefix), styles.by_prefix[prefix])
    return lines
