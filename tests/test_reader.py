import io
import zipfile
from pathlib import Path

import pytest

from ferromapas.model import Folder, LineString, Placemark, Point, Polygon
from ferromapas.reader import ReadError, read, read_bytes

FIXTURES = Path(__file__).parent / "fixtures"


def kml(body: str) -> bytes:
    return (
        '<kml xmlns="http://www.opengis.net/kml/2.2" '
        'xmlns:gx="http://www.google.com/kml/ext/2.2">'
        f"<Document><name>D</name>{body}</Document></kml>"
    ).encode()


def test_mini_structure():
    root, report = read(FIXTURES / "mini.kml")
    assert root.name == "Mini"
    assert [c.name for c in root.children] == [
        "Suelto inicial", "Ferrocarril X", "Suelto entre carpetas", "Vacía",
    ]  # fmt: skip
    ferro = root.children[1]
    assert ferro.description == "Línea\nprincipal"
    assert [c.name for c in ferro.children] == ["Ramal 1", "Terreno"]


def test_mini_geometries_and_normalization():
    root, _ = read(FIXTURES / "mini.kml")
    assert root.children[0].geometry == Point((-64.1, -31.4))  # sin altitud
    ramal = root.children[1].children[0]
    via, estacion, _ = ramal.children
    assert via.description is None  # solo espacios
    assert via.geometry == LineString([(-64.0, -31.0), (-64.5, -31.5), (-65.0, -32.0)])
    assert estacion.description == "Con datos"
    terreno = root.children[1].children[1]
    assert isinstance(terreno.geometry, Polygon)
    assert len(terreno.geometry.outer) == 5
    assert len(terreno.geometry.inners) == 1


def test_mini_report():
    _, report = read(FIXTURES / "mini.kml")
    assert (report.folders, report.points, report.linestrings, report.polygons) == (3, 4, 1, 1)
    assert len(report.warnings) == 1 and "zoologico" in report.warnings[0]
    for tag in ("Style", "StyleMap", "Schema", "LookAt", "styleUrl", "open", "visibility",
                "Snippet", "ExtendedData", "atom:author", "extrude", "tessellate",
                "altitudeMode", "gx:drawOrder"):  # fmt: skip
        assert report.discarded[tag] >= 1, tag
    assert "Descartado" in report.summary()


def test_schema_typed_elements_converted():
    root, report = read(FIXTURES / "mini21.kml")
    a, b = root.children[0].children
    assert a == Placemark("Estación A", "Texto previo\nNombre FEPSA: EST A", Point((-60.0, -37.0)))
    assert b.description == "Nombre FEPSA: EST B"
    assert report.converted == 2 and report.points == 2
    assert report.discarded["S_FEPSA.latitud"] == 1


def test_reads_kmz(tmp_path):
    kmz = tmp_path / "m.kmz"
    with zipfile.ZipFile(kmz, "w") as zf:
        zf.writestr("doc.kml", (FIXTURES / "mini.kml").read_bytes())
    root, _ = read(kmz)
    assert isinstance(root, Folder) and root.name == "Mini"


def test_crlf_normalized():
    root, _ = read_bytes(
        kml("<Placemark><name>P</name><description>a\r\nb</description>"
            "<Point><coordinates>-60,-30</coordinates></Point></Placemark>")
    )  # fmt: skip
    assert root.children[0].description == "a\nb"


@pytest.mark.parametrize(
    "body, message",
    [
        ("<GroundOverlay><name>g</name></GroundOverlay>", "GroundOverlay"),
        ("<NetworkLink/>", "NetworkLink"),
        ("<gx:Tour/>", "gx:Tour"),
        ("<Folder><name>F</name><Foo/></Folder>", "Foo"),
        ("<Placemark><name>P</name><MultiGeometry/></Placemark>", "MultiGeometry"),
        ("<Placemark><name>P</name><Model/></Placemark>", "Model"),
        ("<Placemark><name>P</name><gx:Track/></Placemark>", "gx:Track"),
        ("<Placemark><name>P</name><Bar/></Placemark>", "Bar"),
        ("<Placemark><name>P</name><Point><coordinates>-60,-30</coordinates></Point>"
         "<Point><coordinates>-61,-31</coordinates></Point></Placemark>", "más de una geometría"),
        ("<Placemark><name>P</name><Point><coordinates>-60</coordinates></Point></Placemark>",
         "coordenada inválida"),
        ("<Placemark><name>P</name><Point><coordinates>-60,-30</coordinates><Zap/></Point>"
         "</Placemark>", "Zap"),
    ],
)  # fmt: skip
def test_errors(body, message):
    with pytest.raises(ReadError, match=message):
        read_bytes(kml(body))


def test_error_includes_folder_path():
    with pytest.raises(ReadError, match=r"D / A / B"):
        read_bytes(kml("<Folder><name>A</name><Folder><name>B</name><Foo/></Folder></Folder>"))


def test_unknown_namespace_fails():
    data = b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document><x:Y xmlns:x="urn:z"/></Document></kml>'
    with pytest.raises(ReadError, match="namespace desconocido"):
        read_bytes(data)


def test_nested_document_becomes_folder():
    root, report = read_bytes(
        kml("<Folder><name>F</name><Document><name>Doc</name>"
            "<Placemark><name>P</name><Point><coordinates>-60,-30</coordinates></Point></Placemark>"
            "</Document></Folder>")
    )  # fmt: skip
    assert root.children[0].children[0].name == "Doc"
    assert (report.folders, report.nested_documents) == (1, 1)
    assert "<Document> anidado" in report.warnings[0]
