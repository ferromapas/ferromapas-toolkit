"""Modelo en memoria del mapa: carpetas, placemarks y geometrías."""

from dataclasses import dataclass, field

Coord = tuple[float, float]  # (lon, lat), sin altitud


@dataclass
class Point:
    coord: Coord


@dataclass
class LineString:
    coords: list[Coord]


@dataclass
class Polygon:
    outer: list[Coord]
    inners: list[list[Coord]] = field(default_factory=list)


Geometry = Point | LineString | Polygon


@dataclass
class Placemark:
    name: str
    description: str | None
    geometry: Geometry


@dataclass
class Folder:
    name: str
    description: str | None = None
    children: list["Folder | Placemark"] = field(default_factory=list)
    # Nombre de archivo/directorio en src/ (solo si vino de un árbol); no cuenta para la igualdad.
    slug: str | None = field(default=None, compare=False, repr=False)
