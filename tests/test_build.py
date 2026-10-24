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
    split(root, src, Config(), force=True)
    loaded, warnings = load_tree(src)
    assert warnings == []
    # los sueltos se juntan en el lugar del primero
    assert [c.name for c in loaded.children] == [
        "Suelto inicial", "Suelto entre carpetas", "Ferrocarril X", "Vacía",
    ]  # fmt: skip
    assert loaded.slug == "" and loaded.children[2].slug == "ferrocarril-x"


def test_load_tree_unlisted_and_missing(tmp_path):
    root = Folder("D", None, [Folder("A", None, [Folder("B", None, [pm("p")])])])
    src = tmp_path / "src"
    split(root, src, Config(max_dir_depth=1), force=True)
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
    styles_file = tmp_path / "styles.yaml"
    styles_file.write_text('styles:\n  a/b: { color: "#FF0000" }\n')
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
    f.write_text("styles:\n  a: { colour: '#000000' }\n")
    with pytest.raises(StylesError, match="colour"):
        load_styles(f)


def test_cli_build(tmp_path, capsys):
    src = tmp_path / "src"
    assert main(["split", str(FIXTURES / "mini.kml"), "--src", str(src), "--force"]) == 0
    out = tmp_path / "out" / "m.kmz"
    args = ["build", "--src", str(src), "--styles", str(tmp_path / "no.yaml"), "-o", str(out)]
    assert main(args) == 0 and out.exists()
    assert main([*args, "--kml"]) == 0 and out.with_suffix(".kml").exists()
    assert main(["build", "--src", str(tmp_path / "vacio")]) == 1
    assert "_document.yaml" in capsys.readouterr().err
