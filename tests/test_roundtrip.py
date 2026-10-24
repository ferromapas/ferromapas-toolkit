"""Ida y vuelta: split -> build -> split no debe cambiar nada."""

from pathlib import Path

import pytest

from ferromapas.__main__ import main
from ferromapas.build import build_kml, write_kmz
from ferromapas.compare import compare, load_source, semantic_items
from ferromapas.config import Config
from ferromapas.model import Folder, Placemark, Point
from ferromapas.reader import read
from ferromapas.styles import load_styles
from ferromapas.tree import load_tree, split

FIXTURES = Path(__file__).parent / "fixtures"
STYLES = Path(__file__).parent.parent / "styles.yaml"
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
    assert any("'y'" in line and "-60.000000" in line for line in diff.only_a)
    assert any("'y'" in line and "-61.000000" in line for line in diff.only_b)
    assert not any("'x'" in line for line in diff.only_a + diff.only_b)


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
