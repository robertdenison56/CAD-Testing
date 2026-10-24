from roaddraft.api.session import Session


def draft_small_project(tmp_path):
    s = Session(project_name="RenderTest", out_dir=str(tmp_path))
    s.execute("create_layer", {"name": "CL", "color": "red", "linetype": "center"})
    s.execute("draw_line", {"space": "model", "start": [1000, 1000],
                            "end": [1600, 1000], "layer": "CL"})
    s.execute("draw_arc", {"space": "model", "center": [1600, 1800],
                           "radius": 800, "start_angle_deg": -90,
                           "end_angle_deg": -60, "layer": "CL"})
    s.execute("draw_circle", {"space": "model", "center": [1300, 980],
                              "radius": 20})
    s.execute("place_text", {"space": "model", "position": [1300, 1040],
                             "content": "SR 100", "height": 12,
                             "halign": "center"})
    s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    s.execute("create_viewport", {"sheet": "C-101", "center_paper": [17, 11.6],
                                  "width_in": 31, "height_in": 18,
                                  "model_center": [1500, 1200],
                                  "feet_per_inch": 50})
    s.execute("fill_title_block", {"sheet": "C-101", "fields": {
        "project": "RENDER TEST", "sheet_title": "PLAN", "sheet_number": "C-101",
        "total_sheets": "1", "scale": "1\" = 50'", "date": "2026-08-02"}})
    s.execute("insert_block", {"space": "C-101", "block_name": "NORTH_ARROW",
                               "position": [31.5, 19.5]})
    s.execute("place_table", {"space": "C-101", "position": [26, 8],
                              "title": "CURVE DATA",
                              "columns": [{"header": "CURVE", "width": 1.0},
                                          {"header": "R", "width": 1.4}],
                              "rows": [["C-1", "800.00'"]]})
    return s


def test_render_sheet_png(tmp_path):
    s = draft_small_project(tmp_path)
    r = s.query("render_sheet", {"sheet": "C-101", "dpi": 80})
    assert r["ok"]
    assert r["path"].endswith("C-101.png")
    assert r["size_bytes"] > 10000


def test_render_sheet_base64(tmp_path):
    s = draft_small_project(tmp_path)
    r = s.query("render_sheet", {"sheet": "C-101", "dpi": 60,
                                 "include_base64": True})
    assert r["ok"] and r["base64"].startswith("iVBOR")  # PNG magic in base64


def test_render_model_png(tmp_path):
    s = draft_small_project(tmp_path)
    r = s.query("render_model", {"dpi": 80})
    assert r["ok"] and r["size_bytes"] > 5000
    assert r["bounds"][0] < 1000  # extents include margin


def test_export_pdf(tmp_path):
    s = draft_small_project(tmp_path)
    r = s.query("export_pdf", {})
    assert r["ok"] and r["path"].endswith(".pdf") and r["size_bytes"] > 2000


def test_export_pdf_no_sheets_fails_cleanly(tmp_path):
    s = Session(out_dir=str(tmp_path))
    r = s.query("export_pdf", {})
    assert not r["ok"] and "create_sheet" in r["error"]["hint"]


def test_render_at_the_lowest_dpi_letters_tiny_text_instead_of_crashing(tmp_path):
    """A model view of a long project shrinks its lettering to the 1 pt floor,
    which at 30 dpi is under half a pixel: matplotlib raised 'Could not set the
    fontsize (invalid ppem value)' (pilot work, 2026-10-19). Text is now held
    at a pixel or more for the dpi it is saved at."""
    from roaddraft.render import mpl as mpl_render

    s = Session(project_name="LowDpi", out_dir=str(tmp_path))
    s.execute("draw_line", {"space": "model", "start": [0, 0], "end": [20000, 0]})
    s.execute("place_text", {"space": "model", "position": [100, 10],
                             "content": "TINY", "height": 0.1})
    s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    s.execute("place_text", {"space": "C-101", "position": [5, 5],
                             "content": "TINY", "height": 0.001})
    for dpi in (30, 45):
        r = s.query("render_model", {"dpi": dpi})
        assert r["ok"], r
        r = s.query("render_sheet", {"sheet": "C-101", "dpi": dpi})
        assert r["ok"], r

    # the floor is a pixel at the dpi asked for, and nothing moves from 72 up
    fig, _bounds = mpl_render.model_figure(s.doc)
    sizes = [t.get_fontsize() for t in fig.texts + fig.axes[0].texts]
    assert sizes == [1.0]
    mpl_render.hold_text_legible(fig, 150)
    assert [t.get_fontsize() for t in fig.axes[0].texts] == [1.0]
    mpl_render.hold_text_legible(fig, 30)
    assert [t.get_fontsize() for t in fig.axes[0].texts] == [2.4]
    mpl_render.plt.close(fig)
