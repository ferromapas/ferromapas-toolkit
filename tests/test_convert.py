import zipfile
from pathlib import Path

from ferromapas.__main__ import main
from ferromapas.reader import read

FIXTURES = Path(__file__).parent / "fixtures"
MINI = FIXTURES / "mini.kml"


def test_kml_to_kmz_and_back_is_lossless(tmp_path, capsys):
    kmz = tmp_path / "m.kmz"
    assert main(["kml2kmz", str(MINI), "-o", str(kmz)]) == 0
    with zipfile.ZipFile(kmz) as zf:
        assert zf.namelist() == ["doc.kml"]
    back = tmp_path / "m2.kml"
    assert main(["kmz2kml", str(kmz), "-o", str(back)]) == 0
    assert back.read_bytes() == MINI.read_bytes()  # incluye estilos y todo lo que no se versiona
    assert read(kmz)[0] == read(MINI)[0]


def test_default_output_name_and_reproducible(tmp_path):
    src = tmp_path / "a.kml"
    src.write_bytes(MINI.read_bytes())
    assert main(["kml2kmz", str(src)]) == 0
    first = (tmp_path / "a.kmz").read_bytes()
    assert main(["kml2kmz", str(src), "--force"]) == 0
    assert (tmp_path / "a.kmz").read_bytes() == first


def test_refuses_to_overwrite(tmp_path, capsys):
    out = tmp_path / "x.kmz"
    out.write_bytes(b"previo")
    assert main(["kml2kmz", str(MINI), "-o", str(out)]) == 1
    assert "ya existe" in capsys.readouterr().err
    assert out.read_bytes() == b"previo"
    assert main(["kml2kmz", str(MINI), "-o", str(out), "--force"]) == 0


def test_kmz_extra_files_warned(tmp_path, capsys):
    kmz = tmp_path / "e.kmz"
    with zipfile.ZipFile(kmz, "w") as zf:
        zf.writestr("doc.kml", MINI.read_bytes())
        zf.writestr("files/icono.png", b"png")
    assert main(["kmz2kml", str(kmz)]) == 0
    assert "files/icono.png" in capsys.readouterr().err


def test_invalid_inputs(tmp_path, capsys):
    bad = tmp_path / "bad.kml"
    bad.write_text("<kml>")
    assert main(["kml2kmz", str(bad)]) == 1
    notzip = tmp_path / "n.kmz"
    notzip.write_text("no soy un zip")
    assert main(["kmz2kml", str(notzip)]) == 1
    assert main(["kmz2kml", str(tmp_path / "nada.kmz")]) == 1
    err = capsys.readouterr().err
    assert "no es un KML válido" in err and "ZIP corrupto" in err
