import zipfile
from pathlib import Path

import pytest

from ferromapas.__main__ import main
from ferromapas.build import build_kml, write_kmz
from ferromapas.config import Config
from ferromapas.model import Folder, Placemark, Point
from ferromapas.reader import ReadError, read, read_bytes
from ferromapas.styles import Styles, StylesError, kml_color, load_styles
from ferromapas.tree import TreeError, load_tree, split

FIXTURES = Path(__file__).parent / "fixtures"


def pm(name):
    return Placemark(name, None, Point((-60.0, -30.0)))


def test_kml_color():
    assert kml_color("#6A1B9A") == "ff9a1b6a"
    assert kml_color("#757575", 0.35) == "59757575"
    with pytest.raises(StylesError):
        kml_color("rojo")


def test_load_tree_round_trip(tmp_path):
    root, _ = read(FIXTURES / "mini.kml")
    src = tmp_path / "src"
    split(root, src, Config())
    loaded, warnings = load_tree(src)
    assert warnings == []
    # el orden original se conserva
    assert [c.name for c in loaded.children] == [
        "Suelto inicial", "Ferrocarril X", "Suelto entre carpetas", "Vacía",
    ]  # fmt: skip
    assert loaded.slug == "" and loaded.children[1].slug == "ferrocarril-x"


def test_load_tree_unlisted_and_missing(tmp_path):
    root = Folder("D", None, [Folder("A", None, [Folder("B", None, [pm("p")])])])
    src = tmp_path / "src"
    split(root, src, Config(max_dir_depth=1))
    # archivo no listado: se agrega con aviso
    (src / "a" / "nuevo.kml").write_text((src / "a" / "b.kml").read_text())
    loaded, warnings = load_tree(src)
    assert [c.slug for c in loaded.children[0].children] == ["b", "nuevo"]
    assert len(warnings) == 1 and "nuevo.kml" in warnings[0]
    # listado pero inexistente: error
    (src / "a" / "b.kml").unlink()
    with pytest.raises(TreeError, match="b.kml"):
        load_tree(src)


def test_build_styles_by_prefix(tmp_path):
    styles_file = tmp_path / "folders.yaml"
    styles_file.write_text('folders:\n  A:\n    B: { styles: { color: "#FF0000" } }\n')
    root = Folder("D", None, [pm("suelto"), Folder("A", None, [Folder("B", None, [pm("x")]), Folder("C", None, [pm("y")])])])
    kml = build_kml(root, load_styles(styles_file))
    assert kml.count("<Style ") == 2
    assert '<Style id="default">' in kml and '<Style id="s-a--b">' in kml
    assert kml.index("<name>x</name>") < kml.index("#s-a--b") < kml.index("<name>y</name>")
    assert kml.count("#default") == 2  # suelto e y
    assert "<ns" not in kml
    reread, _ = read_bytes(kml.encode())
    assert reread.children[0].name == "suelto"


def test_build_is_valid_and_roundtrips_geometry():
    root, _ = read(FIXTURES / "mini.kml")
    reread, report = read_bytes(build_kml(root, Styles()).encode())
    assert reread == root
    assert report.discarded["tessellate"] == report.linestrings


def test_kmz_reproducible(tmp_path):
    kml = build_kml(Folder("D", None, [pm("p")]), Styles())
    a, b = tmp_path / "a.kmz", tmp_path / "b.kmz"
    write_kmz(kml, a)
    write_kmz(kml, b)
    assert a.read_bytes() == b.read_bytes()
    with zipfile.ZipFile(a) as zf:
        assert zf.namelist() == ["doc.kml"]
    assert read(a)[0].name == "D"


def test_unknown_style_key(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text("folders:\n  A: { styles: { colour: '#000000' } }\n")
    with pytest.raises(StylesError, match="colour"):
        load_styles(f)


def test_cli_build(tmp_path, capsys):
    src = tmp_path / "src"
    assert main(["split", str(FIXTURES / "mini.kml"), "--src", str(src)]) == 0
    out = tmp_path / "out" / "m.kmz"
    args = ["build", "--src", str(src), "--folders", str(tmp_path / "no.yaml"), "-o", str(out)]
    assert main(args) == 0 and out.exists()
    assert main([*args, "--kml"]) == 0 and out.with_suffix(".kml").exists()
    assert main(["build", "--src", str(tmp_path / "vacio")]) == 1
    assert "_document.yaml" in capsys.readouterr().err


def test_styles_tree_depths(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text(
        "folders:\n"
        "  Mapa:\n"
        "    Argentina:\n"
        "      Belgrano: { styles: { color: '#6A1B9A' }, depth: 2 }\n"
        "    Chile: { styles: { color: '#000000' } }\n"
    )
    styles = load_styles(f)
    assert styles.depths == {"mapa/argentina/belgrano": 5}
    assert set(styles.by_prefix) == {"mapa/argentina/belgrano", "mapa/chile"}


def test_old_flat_styles_rejected(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text("styles:\n  a: { color: '#000000' }\n")
    with pytest.raises(StylesError, match="folders"):
        load_styles(f)


def test_split_uses_depths_from_styles(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text("folders:\n  Mapa:\n    Belgrano: { depth: 2 }\n")
    src = tmp_path / "src"
    args = ["split", str(FIXTURES / "mini.kml"), "--src", str(src), "--folders", str(f), "--config", str(tmp_path / "no.yaml")]
    assert main(args) == 0


def test_cli_build_version(tmp_path):
    src = tmp_path / "src"
    root = Folder("D", None, [Folder("Ferromapas", None, [pm("x")])])
    split(root, src, Config())
    out = tmp_path / "m.kml"
    args = ["build", "--src", str(src), "--folders", str(tmp_path / "no.yaml"), "--version", "v1", "--kml", "-o", str(out)]
    assert main(args) == 0
    assert "<name>Ferromapas (v1)</name>" in out.read_text(encoding="utf-8")


def test_style_short_id(tmp_path):
    f = tmp_path / "folders.yaml"
    f.write_text('folders:\n  A:\n    B: { styles: { color: "#FF0000" }, id: bel }\n')
    root = Folder("D", None, [Folder("A", None, [Folder("B", None, [pm("x")])])])
    kml = build_kml(root, load_styles(f))
    assert '<Style id="bel">' in kml and "#bel</styleUrl>" in kml
    assert "s-a--b" not in kml


@pytest.mark.parametrize(
    "body",
    [
        "A: { id: x }",  # id sin styles
        'A: { styles: { color: "#FF0000" }, id: "con espacio" }',
        'A: { styles: { color: "#FF0000" }, id: default }',
        'A: { styles: { color: "#FF0000" }, id: x }\n  B: { styles: { color: "#00FF00" }, id: x }',
    ],
)
def test_style_id_invalid(tmp_path, body):
    f = tmp_path / "folders.yaml"
    f.write_text("folders:\n  " + body + "\n")
    with pytest.raises(StylesError):
        load_styles(f)
