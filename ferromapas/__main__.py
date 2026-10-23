"""CLI de ferromapas: split | build | validate | compare | fmt."""

import argparse
import sys

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


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ferromapas",
        description="Versiona en git el mapa ferroviario de Ferromapas.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="comando", required=True)
    for name, help_text in COMMANDS.items():
        sub = subparsers.add_parser(name, help=help_text, description=help_text)
        sub.set_defaults(func=_not_implemented)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
