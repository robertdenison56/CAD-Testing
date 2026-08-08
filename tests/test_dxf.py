import ezdxf

from tests.test_render import draft_small_project


def test_dxf_round_trip(tmp_path):
    s = draft_small_project(tmp_path)
    r = s.query("export_dxf", {"path": str(tmp_path / "out.dxf")})
    assert r["ok"]

    dxf = ezdxf.readfile(tmp_path / "out.dxf")

    layer_names = {layer.dxf.name for layer in dxf.layers}
    assert "CL" in layer_names
    cl = dxf.layers.get("CL")
    assert cl.dxf.color == 1  # red -> ACI 1
    assert cl.dxf.linetype == "CENTER"

    msp = dxf.modelspace()
    types = [e.dxftype() for e in msp]
    assert types.count("LINE") == 1
    assert types.count("ARC") == 1
    assert types.count("CIRCLE") == 1
    assert types.count("TEXT") == 1
    text = next(e for e in msp if e.dxftype() == "TEXT")
    assert text.dxf.text == "SR 100"

    assert "NORTH_ARROW" in [b.name for b in dxf.blocks]

    layout = dxf.layouts.get("C-101")
    layout_types = [e.dxftype() for e in layout]
    assert "VIEWPORT" in layout_types
    assert "INSERT" in layout_types  # north arrow
    assert "TEXT" in layout_types  # table + title block text in paper space


def test_dxf_viewport_scale(tmp_path):
    s = draft_small_project(tmp_path)
    s.query("export_dxf", {"path": str(tmp_path / "vp.dxf")})
    dxf = ezdxf.readfile(tmp_path / "vp.dxf")
    layout = dxf.layouts.get("C-101")
    vps = [e for e in layout if e.dxftype() == "VIEWPORT"]
    real = [v for v in vps if v.dxf.id != 1]  # skip the layout's main viewport
    assert real
    vp = real[0]
    assert abs(vp.dxf.width - 31) < 1e-6
    assert abs(vp.dxf.view_height - 18 * 50) < 1e-6  # height_in * feet_per_inch
