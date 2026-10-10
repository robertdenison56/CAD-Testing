"""Extract a one-page plan sheet PDF to JSON: every stroked/filled path, flattened to
polylines in full-size paper inches (origin bottom-left of the displayed page), with its
line width, dash pattern and fill; and every character of the text layer with its
baseline origin, size and rotation.  Run with the system python3 (pdfplumber).

Linework drawn inside a clipping path (a hatch pattern clipped to its area) is clipped
here; pdfminer itself ignores clipping (pdfclip.py)."""
import json, math, sys
from pathlib import Path
import pdfplumber
sys.path.insert(0, str(Path(__file__).parent))
import pdfclip
pdfclip.install()

def bez(p0, p1, p2, p3, n=10):
    out = []
    for i in range(1, n + 1):
        t = i / n; u = 1 - t
        out.append((u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0],
                    u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1]))
    return out

def _gray(c):
    """A colour as one gray level, 0 black .. 1 white (None when there is none)."""
    if c is None:
        return None
    if isinstance(c, (int, float)):
        return round(float(c), 3)
    c = [float(v) for v in c if isinstance(v, (int, float))]
    if len(c) == 1:
        return round(c[0], 3)
    if len(c) == 3:
        return round(0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2], 3)
    if len(c) == 4:
        return round((1 - c[3]) * (1 - (c[0] + c[1] + c[2]) / 3), 3)
    return None


def clipped(subs, clip, W, H):
    """Polylines (pdfplumber's top-down coordinates) cut to their clip regions.  A
    region about the size of the page clips nothing worth the work."""
    for region in clip:
        xs = [x for poly in region for x, _ in poly]
        ys = [y for poly in region for _, y in poly]
        if (max(xs) - min(xs)) * (max(ys) - min(ys)) > 0.3 * W * H:
            continue
        polys = [[(x, H - y) for x, y in poly] for poly in region]
        subs = [piece for s in subs for piece in pdfclip.clip_polyline(s, polys)]
    return subs


def main(pdf_path, out_path, full_scale):
    with pdfplumber.open(pdf_path) as pdf:
        pg = pdf.pages[0]
        H = float(pg.height)
        k = full_scale / 72.0
        conv = lambda p: (round(p[0] * k, 5), round((H - p[1]) * k, 5))
        paths = []
        for kind in ("line", "curve", "rect"):
            for o in pg.objects.get(kind, []):
                subs, cur, start = [], [], None
                path = o.get("path") or []
                if kind == "rect" and not path:
                    x0, x1, t, b = o["x0"], o["x1"], o["top"], o["bottom"]
                    path = [("m", (x0, t)), ("l", (x1, t)), ("l", (x1, b)), ("l", (x0, b)), ("h",)]
                for op in path:
                    c = op[0]
                    if c == "m":
                        if len(cur) > 1: subs.append(cur)
                        cur = [op[1]]; start = op[1]
                    elif c == "l":
                        cur.append(op[1])
                    elif c == "c":
                        p1, p2, p3 = op[1], op[2], op[3]
                        cur.extend(bez(cur[-1], p1, p2, p3))
                    elif c in ("v", "y"):
                        pts = op[1:]
                        if c == "v": cur.extend(bez(cur[-1], cur[-1], pts[0], pts[1]))
                        else: cur.extend(bez(cur[-1], pts[0], pts[1], pts[1]))
                    elif c == "h":
                        if cur and start: cur.append(start)
                if len(cur) > 1: subs.append(cur)
                if o.get("clip") and not o.get("fill"):
                    subs = clipped(subs, o["clip"], pg.width, H)
                if not subs: continue
                dash = o.get("dash")
                paths.append({
                    "subs": [[conv(p) for p in s] for s in subs],
                    "lw": round(float(o.get("linewidth") or 0) * full_scale, 3),
                    "dash": [round(v * full_scale, 3) for v in dash[0]] if dash and dash[0] else None,
                    "stroke": bool(o.get("stroke")), "fill": bool(o.get("fill")),
                    "fill_color": _gray(o.get("non_stroking_color")),
                    "stroke_color": _gray(o.get("stroking_color")),
                    "kind": kind})
        # A character's matrix leaves out the Tf font size where a PDF sets the size with
        # Tf and an unscaled Tm; the reported size puts it back for upright text.  Off-axis
        # text has no reported size to trust, but its advance is the glyph's width in ems
        # times the font size: the width in ems, learned from the same character set
        # upright, gives the size back.  (One font is often set both ways on a page, so
        # a per-font factor is no good.)
        import statistics
        facs, allf, wem, wem_font = {}, [], {}, {}
        for ch in pg.chars:
            a, b, c, d, e, f = ch["matrix"]
            hcd = math.hypot(c, d)
            if hcd > 1e-6 and abs(b) < 1e-3 * max(abs(a), 1e-9) and abs(c) < 1e-3 * max(abs(d), 1e-9) \
                    and 0 < ch["size"] < 200:
                fs = ch["size"] / hcd
                facs.setdefault(ch["fontname"], []).append(fs)
                allf.append(fs)
                if ch["adv"] > 0 and ch["text"].strip():
                    wem.setdefault((ch["fontname"], ch["text"]), []).append(ch["adv"] / fs)
                    wem_font.setdefault(ch["fontname"], []).append(ch["adv"] / fs)
        med_all = statistics.median(allf) if allf else 1.0
        med = {k: statistics.median(v) for k, v in facs.items()}
        wem = {k: statistics.median(v) for k, v in wem.items()}
        wem_font = {k: statistics.median(v) for k, v in wem_font.items()}
        wem_all = statistics.median(wem_font.values()) if wem_font else 0.6
        chars = []
        for ch in pg.chars:
            a, b, c, d, e, f = ch["matrix"]
            hcd = math.hypot(c, d)
            upright = hcd > 1e-6 and abs(b) < 1e-3 * max(abs(a), 1e-9) and abs(c) < 1e-3 * max(abs(d), 1e-9)
            quarter = hcd > 1e-6 and abs(a) < 1e-3 * max(abs(b), 1e-9) and abs(d) < 1e-3 * max(abs(c), 1e-9)
            if quarter and 0 < ch["x1"] - ch["x0"] < 200:
                fac = (ch["x1"] - ch["x0"]) / hcd     # turned 90°: the box's width is the em
            elif upright and 0 < ch["size"] < 200:
                fac = ch["size"] / hcd
            elif ch["adv"] > 0 and ch["text"].strip():
                w = wem.get((ch["fontname"], ch["text"])) or wem_font.get(ch["fontname"]) or wem_all
                fac = ch["adv"] / w
            else:
                fac = med.get(ch["fontname"], med_all)
            chars.append({"t": ch["text"], "x": round(e * k, 5), "y": round(f * k, 5),
                          "size": round(hcd * fac * k, 5),
                          "rot": round(math.degrees(math.atan2(b, a)), 3),
                          "adv": round(ch["adv"] * math.hypot(a, b) * k, 5),
                          "font": ch["fontname"].split("+")[-1],
                          "color": _gray(ch.get("non_stroking_color"))})
    json.dump({"source": pdf_path, "page_in": [float(pg.width) * k, H * k],
               "full_scale": full_scale, "paths": paths, "chars": chars},
              open(out_path, "w"))
    print(f"{len(paths)} paths, {len(chars)} chars -> {out_path}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 1.0)
