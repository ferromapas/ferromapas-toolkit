import subprocess

import pytest

from ferromapas.__main__ import main
from ferromapas.config import Config
from ferromapas.model import Folder, LineString, Placemark, Point
from ferromapas.reader import read, read_bytes
from ferromapas.tree import SplitError, render_tree, slugify, split
from ferromapas.writer import folder_document, format_coord
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def pm(name, lon=-60.0):
    return Placemark(name, None, Point((lon, -30.0)))


def test_slugify():
    assert slugify("Río Tercero - Córdoba") == "rio-tercero-cordoba"
    assert slugify("Ñandú (ex) #2") == "nandu-ex-2"
    assert slugify("???") == "sin-nombre"


def test_format_coord():
    assert format_coord((-64.1, -31.4)) == "-64.100000,-31.400000"
    assert format_coord((-0.0000001, 0.0)) == "0.000000,0.000000"


def test_writer_is_deterministic_and_round_trips():
    root, _ = read(FIXTURES / "mini.kml")
    ferro = root.children[1]
    text = folder_document(ferro)
    assert text == folder_document(ferro)
    assert text.endswith("</kml>\n") and "\r" not in text
    reread, _ = read_bytes(text.encode())
    assert reread == Folder(ferro.name, ferro.description, ferro.children)


def test_writer_format():
    folder = Folder("A & B", "x < y", [Placemark("L", None, LineString([(-60, -30), (-61.5, -31)]))])
    assert folder_document(folder) == (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        "  <Folder>\n"
        "    <name>A &amp; B</name>\n"
        "    <description>x &lt; y</description>\n"
        "    <Placemark>\n"
        "      <name>L</name>\n"
        "      <LineString>\n"
        "        <coordinates>\n"
        "          -60.000000,-30.000000\n"
        "          -61.500000,-31.000000\n"
        "        </coordinates>\n"
        "      </LineString>\n"
        "    </Placemark>\n"
        "  </Folder>\n"
        "</kml>\n"
    )


def sample_tree():
    dup = lambda: Folder("Río Tercero - Córdoba", None, [pm("e")])  # noqa: E731
    return Folder("Doc", None, [
        pm("suelto 1"),
        Folder("Mapa", "Descripción\nmultilínea", [
            Folder("Ferrocarril A", None, [
                Folder("Tramo 1", None, [pm("x")]),
                dup(),
                dup(),
            ]),
            Folder("Ferrocarril B", None, [
                Folder("Línea", None, [Folder("Ramal", None, [pm("y")])]),
            ]),
        ]),
        pm("suelto 2"),
    ])  # fmt: skip


def test_render_tree_layout():
    config = Config(max_dir_depth=2, overrides={"mapa/ferrocarril-b": 3})
    files = render_tree(sample_tree(), config)
    assert sorted(files) == [
        "_document.yaml", "_loose.kml", "mapa/_folder.yaml",
        "mapa/ferrocarril-a/_folder.yaml",
        "mapa/ferrocarril-a/rio-tercero-cordoba-2.kml",
        "mapa/ferrocarril-a/rio-tercero-cordoba.kml",
        "mapa/ferrocarril-a/tramo-1.kml",
        "mapa/ferrocarril-b/_folder.yaml",
        "mapa/ferrocarril-b/linea/_folder.yaml",
        "mapa/ferrocarril-b/linea/ramal.kml",
    ]  # fmt: skip
    assert files["_document.yaml"] == "name: Doc\nchildren:\n- _loose.kml\n- mapa/\n"
    assert files["mapa/_folder.yaml"] == (
        "name: Mapa\ndescription: |-\n  Descripción\n  multilínea\nchildren:\n- ferrocarril-a/\n- ferrocarril-b/\n"
    )
    assert "suelto 2" in files["_loose.kml"] and "suelto 1" in files["_loose.kml"]


def test_extras_preserved(tmp_path):
    src = tmp_path / "src"
    (src / "mapa").mkdir(parents=True)
    (src / "mapa" / "_folder.yaml").write_text("name: Mapa\ncode: M1\nchildren: []\n")
    root = Folder("Doc", None, [Folder("Mapa", None, [Folder("X", None, [pm("p")])])])
    split(root, src, Config(), force=True)
    assert (src / "mapa" / "_folder.yaml").read_text().endswith("code: M1\n")


def test_split_replaces_src_and_is_stable(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "viejo.txt").write_text("x")
    root, _ = read(FIXTURES / "mini.kml")
    split(root, src, Config(), force=True)
    first = {p: p.read_bytes() for p in src.rglob("*") if p.is_file()}
    assert not (src / "viejo.txt").exists() and first
    split(root, src, Config(), force=True)
    assert first == {p: p.read_bytes() for p in src.rglob("*") if p.is_file()}


def test_refuses_dirty_src(tmp_path):
    git = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x")
    with pytest.raises(SplitError, match="sin commitear"):
        split(Folder("D"), src, Config())
    split(Folder("D"), src, Config(), force=True)
    assert (src / "_document.yaml").exists()


def test_cli_split(tmp_path, capsys):
    src = tmp_path / "out"
    code = main(["split", str(FIXTURES / "mini.kml"), "--src", str(src), "--config", str(tmp_path / "no.yaml")])
    assert code == 0
    assert (src / "_document.yaml").exists()
    assert "Se escribieron" in capsys.readouterr().out


def test_cli_split_read_error(tmp_path, capsys):
    bad = tmp_path / "bad.kml"
    bad.write_text('<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Foo/></Document></kml>')
    assert main(["split", str(bad), "--src", str(tmp_path / "o")]) == 1
    assert "Foo" in capsys.readouterr().err


def test_tree_view(tmp_path, capsys):
    root = Folder("Doc", None, [pm("suelto"), Folder("Mapa", None, [Folder("Ramal", None, [pm("a"), pm("b")])])])
    src = tmp_path / "src"
    split(root, src, Config(max_dir_depth=1), force=True)
    assert main(["tree", "--src", str(src)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == [
        f"{src}/",
        "├── _loose.kml  (1 placemarks)",
        "└── mapa/",
        "    └── ramal.kml  (2 placemarks)",
    ]
    assert main(["tree", "--src", str(src), "--depth", "0"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "└── mapa/"
    assert main(["tree", "--src", str(src), "--names"]) == 0
    out = capsys.readouterr().out
    assert "mapa/  # Mapa" in out and "ramal.kml  (2 placemarks)  # Ramal" in out
    assert main(["tree", "--src", str(tmp_path / "nada")]) == 1


def test_normalize_top_folder():
    from ferromapas.tree import normalize_top_folder

    root = Folder("Ferromapas (en Edición).kmz", None, [Folder("Ferromapas (en Edición)", None, []), Folder("Otra", None, [])])
    normalize_top_folder(root)
    assert root.name == "Ferromapas"
    assert [c.name for c in root.children] == ["Ferromapas", "Otra"]
