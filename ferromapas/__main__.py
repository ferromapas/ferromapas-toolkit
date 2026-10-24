"""CLI de ferromapas: split | build | validate | compare | fmt | tree | kmz2kml | kml2kmz."""

import argparse
import sys
from pathlib import Path

from ferromapas.build import build_kml, write_kml, write_kmz
from ferromapas.compare import compare, load_source
from ferromapas.config import load_config
from ferromapas.convert import kml_to_kmz, kmz_to_kml
from ferromapas.reader import ReadError, read
from ferromapas.styles import StylesError, load_styles
from ferromapas.tree import SplitError, TreeError, load_tree, split, tree_view
from ferromapas.validate import validate

COMMANDS = {
    "split": "Convierte un KMZ/KML en el árbol de archivos de src/",
    "build": "Arma el KMZ a partir de src/",
    "validate": "Valida el contenido de src/",
    "compare": "Compara dos fuentes (.kmz, .kml o directorio src)",
    "fmt": "Normaliza src/ en el lugar",
    "tree": "Muestra el árbol de archivos de src/",
    "kmz2kml": "Convierte un .kmz en un .kml (extrae el doc.kml)",
    "kml2kmz": "Convierte un .kml en un .kmz",
}


def _split(args: argparse.Namespace) -> int:
    try:
        root, report = read(args.input)
        count = split(root, args.src, load_config(args.config), force=args.force)
    except (ReadError, SplitError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(report.summary())
    print(f"Se escribieron {count} archivos en {args.src}")
    return 0


def _build(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
        root, warnings = load_tree(args.src)
        kml = build_kml(root, load_styles(args.styles))
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
        count = split(root, args.src, load_config(args.config), force=True)
    except (ReadError, TreeError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"Aviso: {warning}", file=sys.stderr)
    print(f"Se normalizaron {count} archivos en {args.src}")
    return 0


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ferromapas",
        description="Versiona en git el mapa ferroviario de Ferromapas.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="comando", required=True)
    for name, help_text in COMMANDS.items():
        sub = subparsers.add_parser(name, help=help_text, description=help_text)
        if name == "split":
            sub.add_argument("input", help="archivo .kmz o .kml de origen")
            sub.add_argument("--src", default="src", help="directorio de salida (por defecto: src)")
            sub.add_argument("--config", default="ferromapas.yaml", help="archivo de configuración")
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
            sub.set_defaults(func=_fmt)
        if name == "build":
            sub.add_argument("--src", default="src", help="directorio de origen (por defecto: src)")
            sub.add_argument("--config", default="ferromapas.yaml", help="archivo de configuración")
            sub.add_argument("--styles", default="styles.yaml", help="archivo de estilos")
            sub.add_argument("-o", "--output", help="archivo de salida (por defecto: el de ferromapas.yaml)")
            sub.add_argument("--kml", action="store_true", help="generar un KML plano en vez de un KMZ")
            sub.set_defaults(func=_build)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
