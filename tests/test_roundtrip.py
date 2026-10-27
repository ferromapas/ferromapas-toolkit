"""Ida y vuelta: split -> build -> split no debe cambiar nada."""

from pathlib import Path

import pytest

from ferromapas.__main__ import main
from ferromapas.build import build_kml, write_kmz
from ferromapas.compare import compare, load_source, semantic_items
from ferromapas.config import Config
from ferromapas.model import Folder, LineString, Placemark, Point
from ferromapas.reader import read
from ferromapas.styles import load_styles
from ferromapas.tree import load_tree, split

FIXTURES = Path(__file__).parent / "fixtures"
STYLES = Path(__file__).parent.parent / "folders.yaml"
CONFIGS = [Config(), Config(max_dir_depth=1), Config(max_dir_depth=9), Config(overrides={"mini": 0})]


def snapshot(src: Path) -> dict[str, bytes]:
    return {p.relative_to(src).as_posix(): p.read_bytes() for p in sorted(src.rglob("*")) if p.is_file()}


@pytest.mark.parametrize("fixture", ["mini.kml", "mini21.kml"])
@pytest.mark.parametrize("config", CONFIGS)
def test_idempotent(tmp_path, fixture, config):
    root, _ = read(FIXTURES / fixture)
    src1, src2 = tmp_path / "src1", tmp_path / "src2"
    split(root, src1, config, force=True)
    kmz = tmp_path / "out.kmz"
    write_kmz(build_kml(load_tree(src1)[0], load_styles(STYLES)), kmz)
    split(read(kmz)[0], src2, config, force=True)
    assert snapshot(src1) == snapshot(src2)
    assert snapshot(src1)


@pytest.mark.parametrize("fixture", ["mini.kml", "mini21.kml"])
def test_semantic_equality(tmp_path, fixture):
    root, _ = read(FIXTURES / fixture)
    src = tmp_path / "src"
    split(root, src, Config(), force=True)
    kmz = tmp_path / "out.kmz"
    write_kmz(build_kml(load_tree(src)[0], load_styles(STYLES)), kmz)
    assert not compare(root, read(kmz)[0])
    assert not compare(root, load_source(src))
    assert semantic_items(root) == semantic_items(load_source(kmz))


def test_compare_detects_differences():
    def pm(name, lon=-60.0):
        return Placemark(name, None, Point((lon, -30.0)))

    a = Folder("D", None, [Folder("F", None, [pm("x"), pm("y")]), Folder("G")])
    b = Folder("D", None, [Folder("F", None, [pm("x"), pm("y", -61.0)]), Folder("H")])
    diff = compare(a, b)
    assert any("G" in line and line.startswith("Carpeta") for line in diff.only_a)
    assert any("H" in line and line.startswith("Carpeta") for line in diff.only_b)
    assert diff.changed == [
        "F / 'y' [Point]: coordenada: -60.000000,-30.000000 → -61.000000,-30.000000"
    ]
    assert not any("'y'" in line or "'x'" in line for line in diff.only_a + diff.only_b)


def test_compare_ignores_order_and_precision():
    a = Folder("D", None, [Placemark("p", None, Point((-60.0000001, -30.0))), Folder("F")])
    b = Folder("D", None, [Folder("F"), Placemark("p", None, Point((-60.0, -30.0)))])
    assert not compare(a, b)


def test_cli_compare(tmp_path, capsys):
    src = tmp_path / "src"
    mini = str(FIXTURES / "mini.kml")
    assert main(["split", mini, "--src", str(src), "--force"]) == 0
    assert main(["compare", mini, str(src)]) == 0
    assert "Sin diferencias" in capsys.readouterr().out
    assert main(["compare", mini, str(FIXTURES / "mini21.kml")]) == 1
    assert "Solo en" in capsys.readouterr().out


def test_fmt_normalizes_in_place(tmp_path, capsys):
    src = tmp_path / "src"
    assert main(["split", str(FIXTURES / "mini.kml"), "--src", str(src), "--force"]) == 0
    expected = snapshot(src)
    # desnormalizar: reindentar un .kml y agregar un archivo sin listar
    target = next(p for p in src.rglob("*.kml") if p.name != "_loose.kml")
    target.write_text(target.read_text().replace("\n  ", "\n      "))
    assert snapshot(src) != expected
    assert main(["fmt", "--src", str(src), "--config", str(tmp_path / "no.yaml")]) == 0
    assert snapshot(src) == expected
    assert main(["fmt", "--src", str(tmp_path / "nada")]) == 1


def test_compare_describes_empty_linestring():
    empty = Folder("D", None, [Placemark("vacía", None, LineString([]))])
    diff = compare(empty, Folder("D"))
    assert diff.only_a and "0 coord." in diff.only_a[0]


def test_compare_ignores_root_name_and_labels_description_changes():
    a = Folder("viejo.kmz", None, [Folder("F", "uno"), Folder("G")])
    b = Folder("nuevo.kmz", None, [Folder("F", "dos"), Folder("G")])
    diff = compare(a, b)
    assert diff.changed == ["Carpeta: F: descripción: 'uno' → 'dos'"]
    assert not diff.only_a and not diff.only_b


def test_compare_ignore_top_level():
    def tree(top):
        return Folder("x.kmz", None, [Folder(top, None, [Folder("F", None, [Placemark("p", None, Point((-60.0, -30.0)))])])])

    assert compare(tree("1.0.0"), tree("Edición"))  # distinto nombre: todo difiere
    assert not compare(tree("1.0.0"), tree("Edición"), ignore_top_level=True)
    other = tree("Edición")
    other.children[0].children[0].children.clear()
    diff = compare(tree("1.0.0"), other, ignore_top_level=True)
    assert diff.only_a and "'p'" in diff.only_a[0] and not diff.only_b


def test_compare_reports_what_changed_in_a_placemark():
    def line(n, desc=None):
        return Placemark("vía", desc, LineString([(-60.0 - i / 10, -30.0) for i in range(n)]))

    a = Folder("D", None, [Folder("F", None, [line(5, "vieja")])])
    b = Folder("D", None, [Folder("F", None, [line(7, "nueva")])])
    diff = compare(a, b)
    assert not diff.only_a and not diff.only_b
    assert len(diff.changed) == 1
    for expected in ("F / 'vía' [LineString]", "descripción: 'vieja' → 'nueva'", "vértices: 5 → 7"):
        assert expected in diff.changed[0]


def test_cli_compare_separates_differences_with_blank_line(tmp_path, capsys):
    def write(name, lon):
        path = tmp_path / name
        path.write_text(
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>D</name><Folder><name>F</name>'
            f"<Placemark><name>p</name><Point><coordinates>{lon},-30</coordinates></Point></Placemark>"
            "<Placemark><name>q</name><Point><coordinates>-60,-30</coordinates></Point></Placemark>"
            "</Folder></Document></kml>"
        )
        return str(path)

    assert main(["compare", write("a.kml", -60), write("b.kml", -61)]) == 1
    assert "  ~ F / 'p' [Point]: coordenada: -60.000000,-30.000000 → -61.000000,-30.000000\n\n" in capsys.readouterr().out
