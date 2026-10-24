from pathlib import Path

from ferromapas.__main__ import main
from ferromapas.config import Config
from ferromapas.model import Folder, LineString, Placemark, Point, Polygon
from ferromapas.reader import read
from ferromapas.tree import split
from ferromapas.validate import validate

FIXTURES = Path(__file__).parent / "fixtures"


def make_src(tmp_path, root):
    src = tmp_path / "src"
    split(root, src, Config(max_dir_depth=1), force=True)
    return src


def pm(name, geometry=None):
    return Placemark(name, None, geometry or Point((-60.0, -30.0)))


def test_clean_tree(tmp_path):
    root = Folder("D", None, [Folder("A", None, [Folder("B", None, [pm("x")])])])
    report = validate(make_src(tmp_path, root))
    assert report.errors == [] and report.warnings == []
    assert report.exit_code(strict=True) == 0


def test_warnings(tmp_path):
    short_ring = Polygon([(-60, -30), (-61, -30), (-60, -30)])
    root = Folder("D", None, [Folder("A", None, [
        Folder("Vacía"),
        Folder("B", None, [pm("línea", LineString([(-60, -30)])), pm("", None), pm("poli", short_ring)]),
    ])])  # fmt: skip
    report = validate(make_src(tmp_path, root))
    assert report.errors == []
    text = "\n".join(report.warnings)
    for expected in ("carpeta vacía", "1 vértice", "sin nombre", "anillo con 3"):
        assert expected in text
    assert report.exit_code() == 0 and report.exit_code(strict=True) == 1


def test_out_of_box_coordinates(tmp_path):
    root = Folder("D", None, [Folder("A", None, [Folder("B", None, [pm("lejos", Point((10.0, 50.0)))])])])
    report = validate(make_src(tmp_path, root))
    assert len(report.errors) == 1 and "fuera de la caja" in report.errors[0]
    assert report.exit_code() == 1


def test_not_normalized(tmp_path):
    root, _ = read(FIXTURES / "mini.kml")
    src = make_src(tmp_path, root)
    assert validate(src).errors == []
    target = next(src.rglob("*.kml"))
    target.write_text(target.read_text().replace("\n  ", "\n    "))
    report = validate(src)
    assert any("no está normalizado" in e and target.name in e for e in report.errors)


def test_children_pointing_to_nothing(tmp_path):
    root = Folder("D", None, [Folder("A", None, [Folder("B", None, [pm("x")])])])
    src = make_src(tmp_path, root)
    next(src.rglob("b.kml")).unlink()
    report = validate(src)
    assert any("b.kml" in e for e in report.errors)


def test_missing_src(tmp_path):
    assert validate(tmp_path / "nada").errors


def test_cli_validate(tmp_path, capsys):
    root = Folder("D", None, [Folder("A", None, [Folder("Vacía"), Folder("B", None, [pm("x")])])])
    src = make_src(tmp_path, root)
    assert main(["validate", "--src", str(src)]) == 0
    assert main(["validate", "--src", str(src), "--strict"]) == 1
    assert "0 errores, 1 avisos" in capsys.readouterr().out
