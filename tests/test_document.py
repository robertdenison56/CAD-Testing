from roaddraft.document.document import Document
from roaddraft.document.entities import Line, Text, entity_from_dict


def test_new_document_defaults():
    doc = Document.new("Test Project")
    assert doc.meta["project_name"] == "Test Project"
    assert doc.meta["model_units"] == "us_survey_ft"
    assert "0" in doc.layers
    assert "STANDARD" in doc.text_styles
    assert "NORTH_ARROW" in doc.blocks
    assert doc.settings["current_layer"] == "0"


def test_id_generation_deterministic():
    doc = Document.new()
    assert doc.new_id("line") == "LN-001"
    assert doc.new_id("line") == "LN-002"
    assert doc.new_id("text") == "TX-001"
    # counters survive round-trip so replays/continues never collide
    doc2 = Document.from_dict(doc.to_dict())
    assert doc2.new_id("line") == "LN-003"


def test_round_trip_serialization():
    doc = Document.new("RT")
    doc.model_entities["LN-001"] = Line(id="LN-001", start=[0, 0], end=[10, 5])
    doc.model_entities["TX-001"] = Text(id="TX-001", position=[5, 5],
                                        content="STA 10+00", height=8.0)
    d = doc.to_dict()
    doc2 = Document.from_dict(d)
    assert doc2.to_dict() == d


def test_entity_from_dict_rejects_unknown_type():
    try:
        entity_from_dict({"type": "spline"})
        assert False, "should have raised"
    except ValueError as ex:
        assert "spline" in str(ex)


def test_find_entity_and_spaces():
    doc = Document.new()
    doc.model_entities["LN-001"] = Line(id="LN-001", start=[0, 0], end=[1, 1])
    space, entity = doc.find_entity("LN-001")
    assert space == "model" and entity.id == "LN-001"
    assert doc.find_entity("LN-999") is None
    assert doc.resolve_space("model") is not None
    assert doc.resolve_space("nope") is None
