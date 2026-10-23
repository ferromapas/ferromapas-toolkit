"""CLI de ferromapas: split | build | validate | compare | fmt."""

import argparse
import sys

COMANDOS = {
    "split": "Convierte un KMZ/KML en el árbol de archivos de src/",
    "build": "Arma el KMZ a partir de src/",
    "validate": "Valida el contenido de src/",
    "compare": "Compara dos fuentes (.kmz, .kml o directorio src)",
    "fmt": "Normaliza src/ en el lugar",
}


def _no_implementado(args: argparse.Namespace) -> int:
    print(f"El comando '{args.comando}' todavía no está implementado.", file=sys.stderr)
    return 1


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ferromapas",
        description="Versiona en git el mapa ferroviario de Ferromapas.",
    )
    subparsers = parser.add_subparsers(dest="comando", metavar="comando", required=True)
    for nombre, ayuda in COMANDOS.items():
        sub = subparsers.add_parser(nombre, help=ayuda, description=ayuda)
        sub.set_defaults(funcion=_no_implementado)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = crear_parser().parse_args(argv)
    return args.funcion(args)


if __name__ == "__main__":
    sys.exit(main())
