"""Configuración de ferromapas.yaml."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_OUTPUT = "dist/Ferromapas.kmz"
DEFAULT_MAX_DIR_DEPTH = 3


@dataclass
class Config:
    output: str = DEFAULT_OUTPUT
    max_dir_depth: int = DEFAULT_MAX_DIR_DEPTH
    overrides: dict[str, int] = field(default_factory=dict)

    def depth_for(self, slug_path: str) -> int:
        """Profundidad máxima de directorios para una ruta de slugs (gana el prefijo más largo)."""
        best = ""
        result = self.max_dir_depth
        for prefix, depth in self.overrides.items():
            if (slug_path == prefix or slug_path.startswith(prefix + "/")) and len(prefix) >= len(best):
                best, result = prefix, depth
        return result


def load_config(path: str | Path) -> Config:
    """Carga ferromapas.yaml; si no existe, usa los valores por defecto."""
    path = Path(path)
    if not path.exists():
        return Config()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    split = data.get("split") or {}
    return Config(
        output=data.get("output", DEFAULT_OUTPUT),
        max_dir_depth=int(split.get("max_dir_depth", DEFAULT_MAX_DIR_DEPTH)),
        overrides={str(k).strip("/"): int(v) for k, v in (split.get("overrides") or {}).items()},
    )
