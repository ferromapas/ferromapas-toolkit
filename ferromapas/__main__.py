"""CLI de ferromapas: split | build | validate | compare | changelog | fmt | tree | kmz2kml | kml2kmz."""

import argparse
import sys
from datetime import date
from pathlib import Path

from ferromapas.build import build_kml, write_kml, write_kmz
from ferromapas.changelog import ChangelogError, build_entry, diff_by_railway, write_entry
from ferromapas.compare import compare, load_source
from ferromapas.config import Config, load_config
from ferromapas.convert import kml_to_kmz, kmz_to_kml
from ferromapas.reader import ReadError, read
from ferromapas.styles import StylesError, load_styles
from ferromapas.tree import SplitError, TreeError, load_tree, normalize_top_folder, set_top_folder_version, split, tree_view
from ferromapas.validate import validate

COMMANDS = {
    "split": "Convierte un KMZ/KML en el árbol de archivos de src/",
    "build": "Arma el KMZ a partir de src/",
    "validate": "Valida el contenido de src/",
    "compare": "Compara dos fuentes (.kmz, .kml o directorio src)",
    "changelog": "Genera el registro de cambios (YAML) entre dos versiones, por ferrocarril",
    "fmt": "Normaliza src/ en el lugar",
    "tree": "Muestra el árbol de archivos de src/",
    "kmz2kml": "Convierte un .kmz en un .kml (extrae el doc.kml)",
    "kml2kmz": "Convierte un .kml en un .kmz",
}


def _config_with_depths(args: argparse.Namespace) -> Config:
    """Configuración con las profundidades que indica el árbol de folders.yaml (ganan sobre ferromapas.yaml)."""
    config = load_config(args.config)
    config.overrides.update(load_styles(args.folders).depths)
    return config


def _split(args: argparse.Namespace) -> int:
    try:
        root, report = read(args.input)
        normalize_top_folder(root)
        count = split(root, args.src, _config_with_depths(args), force=args.force)
    except (ReadError, SplitError, StylesError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(report.summary())
    print(f"Se escribieron {count} archivos en {args.src}")
    return 0


def _build(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
        root, warnings = load_tree(args.src)
        if args.version:
            set_top_folder_version(root, args.version)
        kml = build_kml(root, load_styles(args.folders))
        if args.kml:
            output = Path(args.output or config.output).with_suffix(".kml")
            write_kml(kml, output)
        else:
            output = Path(args.output or config.output)
            write_kmz(kml, output)
    except (ReadError, TreeError, StylesError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"Aviso: {warning}", file=sys.stderr)
    print(f"Se generó {output}")
    return 0


def _compare(args: argparse.Namespace) -> int:
    try:
        diff = compare(load_source(args.a), load_source(args.b), args.ignore_top_level)
    except (ReadError, TreeError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if not diff:
        print("Sin diferencias.")
        return 0
    print(f"Modificados: {len(diff.changed)}")
    for line in diff.changed:
        print(f"  ~ {line}\n")
    print(f"Solo en {args.a}: {len(diff.only_a)}")
    for line in diff.only_a:
        print(f"  - {line}\n")
    print(f"Solo en {args.b}: {len(diff.only_b)}")
    for line in diff.only_b:
        print(f"  + {line}\n")
    return 1


def _changelog(args: argparse.Namespace) -> int:
    try:
        when = date.fromisoformat(args.date) if args.date else date.today()
        railways = diff_by_railway(load_source(args.old), load_source(args.new))
        path = write_entry(args.out, build_entry(args.version, when, railways), args.force)
    except (ReadError, TreeError, ChangelogError, ValueError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(f"Se escribió {path} ({len(railways)} ferrocarriles con cambios)")
    return 0


def _tree(args: argparse.Namespace) -> int:
    try:
        lines = tree_view(args.src, args.depth, args.names)
    except (ReadError, TreeError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


def _convert(args: argparse.Namespace) -> int:
    to_kml = args.command == "kmz2kml"
    output = Path(args.output) if args.output else Path(args.input).with_suffix(".kml" if to_kml else ".kmz")
    try:
        if to_kml:
            extra = kmz_to_kml(args.input, output, args.force)
        else:
            kml_to_kmz(args.input, output, args.force)
            extra = []
    except (ReadError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    for name in extra:
        print(f"Aviso: el KMZ contiene {name}, que no se copia al KML", file=sys.stderr)
    print(f"Se generó {output}")
    return 0


def _validate(args: argparse.Namespace) -> int:
    report = validate(args.src)
    for error in report.errors:
        print(f"Error: {error}")
    for warning in report.warnings:
        print(f"Aviso: {warning}")
    print(f"{len(report.errors)} errores, {len(report.warnings)} avisos")
    return report.exit_code(args.strict)


def _fmt(args: argparse.Namespace) -> int:
    try:
        root, warnings = load_tree(args.src)
        normalize_top_folder(root)
        count = split(root, args.src, _config_with_depths(args), force=True)
    except (ReadError, TreeError, StylesError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"Aviso: {warning}", file=sys.stderr)
    print(f"Se normalizaron {count} archivos en {args.src}")
    return 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ferromapas-toolkit",
        description="Versiona en git el mapa ferroviario de Ferromapas.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="comando", required=True)
    for name, help_text in COMMANDS.items():
        sub = subparsers.add_parser(name, help=help_text, description=help_text)
        if name == "split":
            sub.add_argument("input", help="archivo .kmz o .kml de origen")
            sub.add_argument("--src", default="src", help="directorio de salida (por defecto: src)")
            sub.add_argument("--config", default="ferromapas.yaml", help="archivo de configuración")
            sub.add_argument("--folders", default="folders.yaml", help="archivo de carpetas (estilos y profundidades)")
            sub.add_argument("--force", action="store_true", help="pisar src/ aunque tenga cambios sin commitear")
            sub.set_defaults(func=_split)
        if name == "compare":
            sub.add_argument("a", help=".kmz, .kml o directorio src")
            sub.add_argument("b", help=".kmz, .kml o directorio src")
            sub.add_argument(
                "--ignore-top-level",
                action="store_true",
                help="ignora el nombre de la carpeta de primer nivel (para versiones que la renombraron)",
            )
            sub.set_defaults(func=_compare)
        if name == "changelog":
            sub.add_argument("old", help="versión anterior: .kmz, .kml o directorio src")
            sub.add_argument("new", help="versión nueva: .kmz, .kml o directorio src")
            sub.add_argument("--version", required=True, help="número de la versión nueva (X.Y.Z)")
            sub.add_argument("--date", help="fecha AAAA-MM-DD (por defecto: hoy)")
            sub.add_argument("--out", default="changelog", help="directorio de salida (por defecto: changelog)")
            sub.add_argument("--force", action="store_true", help="regenerar si ya existe (conserva las notas)")
            sub.set_defaults(func=_changelog)
        if name == "validate":
            sub.add_argument("--src", default="src", help="directorio a validar (por defecto: src)")
            sub.add_argument("--strict", action="store_true", help="los avisos también fallan")
            sub.set_defaults(func=_validate)
        if name == "tree":
            sub.add_argument("--src", default="src", help="directorio a mostrar (por defecto: src)")
            sub.add_argument("--depth", type=int, help="niveles de directorios a desplegar (la raíz es 0)")
            sub.add_argument("--names", action="store_true", help="muestra también el nombre real de cada carpeta")
            sub.set_defaults(func=_tree)
        if name in ("kmz2kml", "kml2kmz"):
            sub.add_argument("input", help="archivo de origen")
            sub.add_argument("-o", "--output", help="archivo de salida (por defecto: el de origen con la otra extensión)")
            sub.add_argument("--force", action="store_true", help="pisar el archivo de salida si existe")
            sub.set_defaults(func=_convert)
        if name == "fmt":
            sub.add_argument("--src", default="src", help="directorio a normalizar (por defecto: src)")
            sub.add_argument("--config", default="ferromapas.yaml", help="archivo de configuración")
            sub.add_argument("--folders", default="folders.yaml", help="archivo de carpetas (estilos y profundidades)")
            sub.set_defaults(func=_fmt)
        if name == "build":
            sub.add_argument("--src", default="src", help="directorio de origen (por defecto: src)")
            sub.add_argument("--config", default="ferromapas.yaml", help="archivo de configuración")
            sub.add_argument("--folders", default="folders.yaml", help="archivo de carpetas (estilos y profundidades)")
            sub.add_argument("-o", "--output", help="archivo de salida (por defecto: el de ferromapas.yaml)")
            sub.add_argument("--version", help='texto de versión: la carpeta principal queda "Ferromapas (TEXTO)"')
            sub.add_argument("--kml", action="store_true", help="generar un KML plano en vez de un KMZ")
            sub.set_defaults(func=_build)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
