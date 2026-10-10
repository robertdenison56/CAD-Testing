"""Extract a one-page plan sheet PDF to JSON: every stroked/filled path, flattened to
polylines in full-size paper inches (origin bottom-left of the displayed page), with its
line width, dash pattern and fill; and every character of the text layer with its
baseline origin, size and rotation.  Run with the system python3 (pdfplumber)."""
import json, math, sys
import pdfplumber

def bez(p0, p1, p2, p3, n=10):
    out = []
    for i in range(1, n + 1):
        t = i / n; u = 1 - t
        out.append((u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0],
                    u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1]))
    return out

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
                if not subs: continue
                dash = o.get("dash")
                paths.append({
                    "subs": [[conv(p) for p in s] for s in subs],
                    "lw": round(float(o.get("linewidth") or 0) * full_scale, 3),
                    "dash": [round(v * full_scale, 3) for v in dash[0]] if dash and dash[0] else None,
                    "stroke": bool(o.get("stroke")), "fill": bool(o.get("fill")),
                    "kind": kind})
        chars = []
        for ch in pg.chars:
            a, b, c, d, e, f = ch["matrix"]
            chars.append({"t": ch["text"], "x": round(e * k, 5), "y": round(f * k, 5),
                          "size": round(math.hypot(c, d) * k, 5),
                          "rot": round(math.degrees(math.atan2(b, a)), 3),
                          "adv": round(ch["adv"] * math.hypot(a, b) * k, 5)})
    json.dump({"source": pdf_path, "page_in": [float(pg.width) * k, H * k],
               "full_scale": full_scale, "paths": paths, "chars": chars},
              open(out_path, "w"))
    print(f"{len(paths)} paths, {len(chars)} chars -> {out_path}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 1.0)
