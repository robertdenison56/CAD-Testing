import json

import pytest

from roaddraft.api.session import Session
from roaddraft.document import fileformat
from roaddraft.document.fileformat import DocumentFormatError


def drawing(project_name="Untitled"):
    s = Session(project_name=project_name)
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [9, 9]})
    return s


# ------------------------------------------------------------- save paths


def test_save_round_trips_through_the_application_extension(tmp_path):
    s = drawing("SaveMe")
    path = tmp_path / "project.rdraft"
    assert s.query("save_document", {"path": str(path)})["ok"]
    assert Session.load(path).doc.to_dict() == s.doc.to_dict()


def test_interchange_extension_still_saves_and_loads(tmp_path):
    s = drawing()
    path = tmp_path / "project.rdoc.json"
    assert s.query("save_document", {"path": str(path)})["ok"]
    assert path.exists()                       # written where it was asked for
    assert Session.load(path).doc.to_dict() == s.doc.to_dict()


def test_a_path_with_no_extension_gains_the_application_one(tmp_path):
    s = drawing()
    r = s.query("save_document", {"path": str(tmp_path / "project")})
    assert r["ok"] and r["path"].endswith(".rdraft")
    assert (tmp_path / "project.rdraft").exists()


def test_dotted_qualifiers_survive_normalization():
    # with_suffix would eat ".sheets"; the extension is appended instead
    assert fileformat.normalize_path("SR-100.sheets").name == "SR-100.sheets.rdraft"
    assert fileformat.normalize_path("SR-100.rdoc.json").name == "SR-100.rdoc.json"
    assert fileformat.normalize_path("SR-100.rdraft").name == "SR-100.rdraft"


def test_save_creates_missing_parent_folders(tmp_path):
    s = drawing()
    path = tmp_path / "nested" / "deeper" / "project.rdraft"
    assert s.query("save_document", {"path": str(path)})["ok"]
    assert path.exists()


# ---------------------------------------------------- content, not extension


def test_a_renamed_document_still_opens(tmp_path):
    s = drawing()
    s.query("save_document", {"path": str(tmp_path / "project.rdraft")})
    renamed = (tmp_path / "project.rdraft").rename(tmp_path / "no-extension-at-all")
    assert Session.load(renamed).doc.to_dict() == s.doc.to_dict()


def test_the_two_extensions_hold_the_same_bytes(tmp_path):
    s = drawing()
    s.query("save_document", {"path": str(tmp_path / "a.rdraft")})
    s.query("save_document", {"path": str(tmp_path / "a.rdoc.json")})
    assert (tmp_path / "a.rdraft").read_bytes() == (tmp_path / "a.rdoc.json").read_bytes()


# ------------------------------------------------------------------ refusals


def test_stray_json_is_refused_rather_than_opened_blank(tmp_path):
    # Document.from_dict defaults every field, so without this check a stray
    # JSON object would open as an empty drawing and look like data loss.
    path = tmp_path / "package.json"
    path.write_text(json.dumps({"name": "not-a-drawing", "version": "1.0.0"}))
    with pytest.raises(DocumentFormatError, match="no schema_version"):
        Session.load(path)


def test_malformed_json_is_refused(tmp_path):
    path = tmp_path / "broken.rdraft"
    path.write_text("{not json")
    with pytest.raises(DocumentFormatError, match="not readable JSON"):
        Session.load(path)


def test_a_non_json_file_is_refused(tmp_path):
    path = tmp_path / "notes.rdraft"
    path.write_text("just some text")
    with pytest.raises(DocumentFormatError, match="not a RoadDraft document"):
        Session.load(path)


def test_a_container_file_is_named_as_such(tmp_path):
    # the zip shape this format is headed for: refused clearly, not as junk
    path = tmp_path / "future.rdraft"
    path.write_bytes(b"PK\x03\x04" + b"\x00" * 20)
    with pytest.raises(DocumentFormatError, match="container-format"):
        Session.load(path)


def test_a_missing_file_still_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        Session.load(tmp_path / "nope.rdraft")


# ---------------------------------------------------------------- references


def test_a_reference_resolves_across_both_extensions(tmp_path):
    # a .rdoc.json host pointing at a .rdraft basefile, by relative path
    base = drawing("Survey Base")
    base.query("save_document", {"path": str(tmp_path / "survey.rdraft")})

    host = Session(out_dir=str(tmp_path))
    host.query("save_document", {"path": str(tmp_path / "host.rdoc.json")})
    assert host.execute("attach_reference",
                        {"name": "SURVEY", "path": "survey.rdraft",
                         "space": "model"})["ok"]
    host.query("save_document", {"path": str(tmp_path / "host.rdoc.json")})

    reopened = Session.load(tmp_path / "host.rdoc.json")
    refs = reopened.query("list_references")["references"]
    assert refs[0]["entities"] == 1 and not refs[0].get("error")
