"""CLI de ferromapas: split | build | validate | compare | fmt."""

import argparse
import sys

from pathlib import Path

from ferromapas.build import build_kml, write_kml, write_kmz
from ferromapas.compare import compare, load_source
from ferromapas.config import load_config
from ferromapas.reader import ReadError, read
from ferromapas.styles import StylesError, load_styles
from ferromapas.tree import SplitError, TreeError, load_tree, split

COMMANDS = {
    "split": "Convierte un KMZ/KML en el árbol de archivos de src/",
    "build": "Arma el KMZ a partir de src/",
    "validate": "Valida el contenido de src/",
    "compare": "Compara dos fuentes (.kmz, .kml o directorio src)",
    "fmt": "Normaliza src/ en el lugar",
}


def _not_implemented(args: argparse.Namespace) -> int:
    print(f"El comando '{args.command}' todavía no está implementado.", file=sys.stderr)
    return 1


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
        diff = compare(load_source(args.a), load_source(args.b))
    except (ReadError, TreeError, OSError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if not diff:
        print("Sin diferencias.")
        return 0
    print(f"Solo en {args.a}: {len(diff.only_a)}")
    for line in diff.only_a:
        print(f"  - {line}")
    print(f"Solo en {args.b}: {len(diff.only_b)}")
    for line in diff.only_b:
        print(f"  + {line}")
    return 1


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
        sub.set_defaults(func=_not_implemented)
        if name == "split":
            sub.add_argument("input", help="archivo .kmz o .kml de origen")
            sub.add_argument("--src", default="src", help="directorio de salida (por defecto: src)")
            sub.add_argument("--config", default="ferromapas.yaml", help="archivo de configuración")
            sub.add_argument("--force", action="store_true", help="pisar src/ aunque tenga cambios sin commitear")
            sub.set_defaults(func=_split)
        if name == "compare":
            sub.add_argument("a", help=".kmz, .kml o directorio src")
            sub.add_argument("b", help=".kmz, .kml o directorio src")
            sub.set_defaults(func=_compare)
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
