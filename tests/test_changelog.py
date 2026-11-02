from datetime import date

import pytest
import yaml

from ferromapas.__main__ import main
from ferromapas.changelog import ChangelogError, build_entry, diff_by_railway, dump_entry, write_entry
from ferromapas.model import Folder, LineString, Placemark, Point
from ferromapas.writer import folder_document


def pm(name, lon=-60.0, description=None):
    return Placemark(name, description, Point((lon, -30.0)))


def world(*railways):
    """Document > Ferromapas > Ferrocarriles Argentinos > ferrocarriles."""
    country = Folder("Ferrocarriles Argentinos", None, list(railways))
    return Folder("Ferromapas", None, [Folder("Ferromapas", None, [country])])


def railway(name, *children):
    return Folder(name, None, list(children))


OLD = world(
    railway("Urquiza", pm("Lynch"), pm("Borrada"), Folder("Ramal", None, [pm("Vieja")])),
    railway("Belgrano", pm("Tucumán")),
)
NEW = world(
    railway("Urquiza", pm("Lynch", lon=-61.0), pm("Nueva"), Folder("Ramal", None, [pm("Vieja")])),
    railway("Belgrano", pm("Tucumán")),
)


def test_groups_changes_by_railway():
    result = diff_by_railway(OLD, NEW)
    assert [r.name for r in result] == ["Ferrocarriles Argentinos / Urquiza"]  # Belgrano no cambió
    urquiza = result[0]
    assert urquiza.added == ["Nueva"]
    assert urquiza.removed == ["Borrada"]
    assert urquiza.changed == ["Lynch: coordenada: -60.000000,-30.000000 → -61.000000,-30.000000"]


def test_subfolder_path_is_kept_in_labels():
    new = world(
        railway("Urquiza", pm("Lynch"), pm("Borrada"), Folder("Ramal", None, [pm("Vieja"), pm("Otra")])),
        railway("Belgrano", pm("Tucumán")),
    )
    (urquiza,) = diff_by_railway(OLD, new)
    assert urquiza.added == ["Ramal / Otra"]


def test_top_level_rename_is_ignored():
    renamed = world(*OLD.children[0].children[0].children)
    renamed.children[0].name = "Ferromapas (en Edición)"
    assert diff_by_railway(OLD, renamed) == []


def test_line_geometry_change_is_reported():
    a = world(railway("X", Placemark("Vía", None, LineString([(0.0, 0.0), (1.0, 1.0)]))))
    b = world(railway("X", Placemark("Vía", None, LineString([(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]))))
    (x,) = diff_by_railway(a, b)
    assert x.changed == ["Vía: vértices: 2 → 3"]


def test_entry_summary_and_deterministic_output():
    entry = build_entry("1.1.0", date(2026, 11, 2), diff_by_railway(OLD, NEW))
    assert entry["summary"] == {"added": 1, "changed": 1, "removed": 1}
    assert dump_entry(entry) == dump_entry(build_entry("1.1.0", date(2026, 11, 2), diff_by_railway(OLD, NEW)))
    loaded = yaml.safe_load(dump_entry(entry))
    assert loaded["version"] == "1.1.0" and loaded["date"] == date(2026, 11, 2)


def test_write_entry_preserves_notes_with_force(tmp_path):
    entry = build_entry("1.1.0", date(2026, 11, 2), diff_by_railway(OLD, NEW))
    path = write_entry(tmp_path, entry)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["notes"] = "Línea uno.\nLínea dos.\n"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ChangelogError):
        write_entry(tmp_path, entry)
    write_entry(tmp_path, entry, force=True)
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["notes"] == "Línea uno.\nLínea dos.\n"


def test_invalid_version_is_rejected(tmp_path):
    with pytest.raises(ChangelogError):
        write_entry(tmp_path, build_entry("v1", date(2026, 1, 1), []))


def test_cli_changelog(tmp_path, capsys):
    old, new = tmp_path / "old.kml", tmp_path / "new.kml"
    for path, root in ((old, OLD), (new, NEW)):
        top = root.children[0]
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>x</name>'
            + folder_document(top).split("<kml xmlns=\"http://www.opengis.net/kml/2.2\">", 1)[1].rsplit("</kml>", 1)[0]
            + "</Document></kml>",
            encoding="utf-8",
        )
    out = tmp_path / "out"
    assert main(["changelog", str(old), str(new), "--version", "1.1.0", "--date", "2026-11-02", "--out", str(out)]) == 0
    assert (out / "1.1.0.yaml").exists()
    assert main(["changelog", str(old), str(new), "--version", "1.1.0", "--out", str(out)]) == 1
    assert "ya existe" in capsys.readouterr().err
