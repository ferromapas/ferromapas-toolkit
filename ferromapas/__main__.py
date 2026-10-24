"""CLI de ferromapas: split | build | validate | compare | fmt."""

import argparse
import sys

from ferromapas.config import load_config
from ferromapas.reader import ReadError, read
from ferromapas.tree import SplitError, split

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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
