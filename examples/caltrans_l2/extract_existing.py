"""Digitise the existing-ground linework off the published plan sheet.

The roadway design on sheet L-2 is rebuilt from its own design data (see
sr70_geometry), but the survey underneath it -- contours, the cut/fill catch
line, the UPRR, the right of way -- carries no design data anywhere, so it is
read out of the published PDF's vector content and written into the model file
as ordinary survey linework, which is where it belongs.

Writes existing.json, beside the builders in roaddraft.probes.l2: the survey linework as {layer: [polyline, ...]} plus the
contour elevation labels, all in model-space feet.

    python extract_existing.py --pdf <plan.pdf> [--out existing.json]
"""
import argparse
import json
import math
import re
import zlib
from pathlib import Path

from roaddraft.probes import l2                                  # noqa: E402
from roaddraft.probes.l2 import sheet_content as SHEET          # noqa: E402
from roaddraft.probes.l2 import sr70_geometry as G              # noqa: E402

#: the build reads the survey from beside the builders, in the package
EXISTING = Path(l2.__file__).parent / "existing.json"

TOKEN = re.compile(r'/[^\s/\[\]<>(){}]+|<<|>>|\[|\]|-?\d*\.?\d+|[A-Za-z\'"*]+')
PT_PER_IN = 72.0
PAGE = (1584.0, 2448.0)          # PDF user space; the page displays rotated 270


# ----------------------------------------------------------------- pdf paths
def _strip_strings(s):
    out, i, n = [], 0, len(s)
    while i < n:
        ch = s[i]
        if ch == '(':
            depth, i = 1, i + 1
            while i < n and depth:
                if s[i] == '\\':
                    i += 2
                    continue
                depth += {'(': 1, ')': -1}.get(s[i], 0)
                i += 1
            out.append(' ')
        elif ch == '<' and i + 1 < n and s[i + 1] != '<':
            j = s.find('>', i)
            i = n if j < 0 else j + 1
            out.append(' ')
        else:
            out.append(ch)
            i += 1
    return ''.join(out)


def _mul(a, b):
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]]


def _apply(t, x, y):
    return (t[0] * x + t[2] * y + t[4], t[1] * x + t[3] * y + t[5])


def _bezier(p0, p1, p2, p3, n=8):
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        out.append((u * u * u * p0[0] + 3 * u * u * t * p1[0]
                    + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                    u * u * u * p0[1] + 3 * u * u * t * p1[1]
                    + 3 * u * t * t * p2[1] + t * t * t * p3[1]))
    return out


def read_paths(pdf_path):
    """Every stroked/filled path in the page, in PDF user space, with the
    line width and dash pattern it was drawn with."""
    data = Path(pdf_path).read_bytes()
    m = re.search(rb'stream\r?\n', data)
    body = zlib.decompress(data[m.end():data.find(b'endstream', m.end())])
    toks = TOKEN.findall(_strip_strings(body.decode('latin-1')))

    def num(t):
        try:
            return float(t)
        except ValueError:
            return None

    ctm, stack = [1, 0, 0, 1, 0, 0], []
    lw, lw_stack = 1.0, []
    dash, dash_stack = None, []
    ops, paths = [], []
    cur, sub, start, cp = [], [], None, None

    def trailing(k):
        acc = []
        for t in reversed(ops):
            v = num(t)
            if v is None:
                break
            acc.append(v)
            if len(acc) == k:
                break
        return list(reversed(acc)) if len(acc) == k else None

    for t in toks:
        if num(t) is not None or t[0] in '/[]<' or t == '>>':
            ops.append(t)
            continue
        o = t
        if o == 'q':
            stack.append(ctm[:]); lw_stack.append(lw); dash_stack.append(dash)
        elif o == 'Q' and stack:
            ctm, lw, dash = stack.pop(), lw_stack.pop(), dash_stack.pop()
        elif o == 'cm':
            a = trailing(6)
            if a:
                ctm = _mul(a, ctm)
        elif o == 'w':
            a = trailing(1)
            if a:
                lw = a[0]
        elif o == 'd':
            try:
                j = len(ops) - 2
                assert ops[j] == ']'
                k = j
                while ops[k] != '[':
                    k -= 1
                arr = [num(x) for x in ops[k + 1:j]]
                dash = tuple(arr) if arr else None
            except Exception:
                dash = None
        elif o == 'm':
            a = trailing(2)
            if a:
                if sub:
                    cur.append(sub)
                sub = [_apply(ctm, *a)]
                cp = start = tuple(a)
        elif o == 'l':
            a = trailing(2)
            if a and cp:
                sub.append(_apply(ctm, *a))
                cp = tuple(a)
        elif o in ('c', 'v', 'y'):
            a = trailing(6 if o == 'c' else 4)
            if a and cp:
                if o == 'c':
                    p1, p2, p3 = (a[0], a[1]), (a[2], a[3]), (a[4], a[5])
                elif o == 'v':
                    p1, p2, p3 = cp, (a[0], a[1]), (a[2], a[3])
                else:
                    p1 = p2 = p3 = (a[0], a[1])
                    p3 = (a[2], a[3])
                for p in _bezier(cp, p1, p2, p3):
                    sub.append(_apply(ctm, *p))
                cp = p3
        elif o == 'h':
            if sub and start:
                sub.append(_apply(ctm, *start))
                cp = start
        elif o == 're':
            a = trailing(4)
            if a:
                if sub:
                    cur.append(sub); sub = []
                x, y, w, h = a
                cur.append([_apply(ctm, x, y), _apply(ctm, x + w, y),
                            _apply(ctm, x + w, y + h), _apply(ctm, x, y + h),
                            _apply(ctm, x, y)])
        elif o in ('S', 's', 'f', 'F', 'f*', 'B', 'B*', 'b', 'b*', 'n'):
            if sub:
                cur.append(sub); sub = []
            if cur and o != 'n':
                scale = math.hypot(ctm[0], ctm[1])
                paths.append({'pts': cur, 'lw': round(lw * scale, 2),
                              'dash': dash is not None, 'fill': o[0] in 'fFbB'})
            cur = []
        ops = []
    return paths


TEXT_RUN = re.compile(
    r'BT\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*'
    r'Tm\s*/\S+\s+[\d.]+\s+Tf\s*\((.*?)\)\s*Tj\s*ET', re.S)


def read_glyphs(pdf_path):
    """Every glyph on the page: (paper x, paper y, height in, rotation deg,
    character).  This producer writes one BT/ET block per glyph with a full
    text matrix, so placement comes straight out of it.  The matrix carries
    the glyph's own advance width in 'a', so the type size is |(c, d)| and the
    baseline angle is atan2(b, a); the page displays turned 270 degrees, which
    adds a quarter turn on the way to paper coordinates."""
    data = Path(pdf_path).read_bytes()
    m = re.search(rb'stream\r?\n', data)
    body = zlib.decompress(data[m.end():data.find(b'endstream', m.end())])
    out = []
    for g in TEXT_RUN.finditer(body.decode('latin-1')):
        a, b, c, d, e, f = (float(g.group(i)) for i in range(1, 7))
        char = g.group(7).replace('\\(', '(').replace('\\)', ')').replace('\\\\', '\\')
        if not char.strip():
            continue
        x, y = to_paper((e, f))
        size = math.hypot(c, d) / PT_PER_IN
        rotation = 90.0 + math.degrees(math.atan2(b, a))
        if rotation > 180.0:
            rotation -= 360.0
        out.append((x, y, size, rotation, char))
    # the plan letters its labels twice, once over the white panel that breaks
    # the contour and once again on top; keep one of each
    seen, unique = set(), []
    for g in out:
        key = (round(g[0], 3), round(g[1], 3), g[4])
        if key in seen:
            continue
        seen.add(key)
        unique.append(g)
    return unique


def group_runs(glyphs, gap=0.06):
    """Chain glyphs that share a baseline into words."""
    runs = []
    for key in sorted({round(g[3] / 2.0) for g in glyphs}):
        bucket = [g for g in glyphs if round(g[3] / 2.0) == key]
        ang = math.radians(sum(g[3] for g in bucket) / len(bucket))
        ca, sa = math.cos(ang), math.sin(ang)
        bucket.sort(key=lambda g: (round(-g[0] * sa + g[1] * ca, 2),
                                   g[0] * ca + g[1] * sa))
        cur = []
        for g in bucket:
            if cur:
                p = cur[-1]
                along = (g[0] - p[0]) * ca + (g[1] - p[1]) * sa
                across = -(g[0] - p[0]) * sa + (g[1] - p[1]) * ca
                if not (-0.01 <= along <= p[2] * 1.5 + gap and abs(across) < 0.02):
                    runs.append(cur)
                    cur = []
            cur.append(g)
        if cur:
            runs.append(cur)
    return [(r[0][0], r[0][1], r[0][2], r[0][3], "".join(g[4] for g in r))
            for r in runs]


# ------------------------------------------------------- geometry utilities
def to_paper(pt):
    """PDF user space -> sheet inches, origin at the sheet's bottom-left."""
    x, y = pt
    return ((PAGE[1] - y) / PT_PER_IN, x / PT_PER_IN)


def simplify(pts, tol):
    """Douglas-Peucker."""
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        ax, ay = pts[i]
        bx, by = pts[j]
        dx, dy = bx - ax, by - ay
        seg = math.hypot(dx, dy)
        best, bi = -1.0, None
        for k in range(i + 1, j):
            px, py = pts[k]
            if seg < 1e-12:
                d = math.hypot(px - ax, py - ay)
            else:
                d = abs(dy * px - dx * py + bx * ay - by * ax) / seg
            if d > best:
                best, bi = d, k
        if best > tol:
            keep[bi] = True
            stack.append((i, bi))
            stack.append((bi, j))
    return [p for p, k in zip(pts, keep) if k]


def centerline_paper(samples=400):
    """Dense sample of the rebuilt centerline, in sheet inches."""
    pis = G.control_points()
    del pis
    from roaddraft import Session
    s = Session(project_name="probe")
    s.execute("create_alignment", {"name": G.ALIGNMENT,
                                   "begin_station": G.BEGIN_STA,
                                   "pis": G.control_points()})
    out = []
    for i in range(samples + 1):
        sta = G.BEGIN_STA + (G.END_STA - G.BEGIN_STA) * i / samples
        q = s.query("station_to_xy", {"alignment": G.ALIGNMENT, "station": sta})
        out.append(G.model_to_paper(q["point"]))
    return out


def offsets_from(cl, pts):
    """(min |offset|, max |offset|, mean signed offset) of a point list from a
    polyline, in sheet inches; signed negative to the left of the direction of
    travel (north of "SR70" LINE), positive to the right."""
    lo, hi, signed = 1e9, -1e9, 0.0
    for px, py in pts:
        best, bi = 1e9, 0
        for i, (cx, cy) in enumerate(cl):
            d = (px - cx) ** 2 + (py - cy) ** 2
            if d < best:
                best, bi = d, i
        d = math.sqrt(best)
        lo, hi = min(lo, d), max(hi, d)
        j = min(bi, len(cl) - 2)
        tx, ty = cl[j + 1][0] - cl[j][0], cl[j + 1][1] - cl[j][1]
        cross = tx * (py - cl[j][1]) - ty * (px - cl[j][0])
        signed += d if cross < 0 else -d
    return lo, hi, signed / len(pts)


# --------------------------------------------------------------- classifier
PLAN = G.BORDER
TITLE_BLOCK = (27.6, 18.4, 34.0, 22.0)      # the stamp and the Dist/County grid


def _axis_aligned(pts):
    return all(abs(pts[i][0] - pts[i + 1][0]) < 1e-6
               or abs(pts[i][1] - pts[i + 1][1]) < 1e-6
               for i in range(len(pts) - 1))


def _leader_tips(cl):
    """Where sheet L-2's callout leaders touch down, in sheet inches.  Their
    arrowheads are hatched with the same short strokes as the guard railing
    they point at, and they are sheet annotation, not roadway hardware."""
    from roaddraft import Session
    s = Session(project_name="probe")
    s.execute("create_alignment", {"name": G.ALIGNMENT,
                                   "begin_station": G.BEGIN_STA,
                                   "pis": G.control_points()})
    out = []
    for entry in SHEET.CALLOUTS:
        station, offset = entry[0], entry[1]
        q = s.query("station_to_xy", {"alignment": G.ALIGNMENT,
                                      "station": station, "offset": offset})
        out.append(G.model_to_paper(q["point"]))
    return out


def classify(lw, dashed, pts, cl, tips=(), filled=False):
    """Layer for one subpath, or None to leave it out of the model file.

    Anything axis-aligned on the sheet is drawing furniture -- the plan itself
    is turned 6.5 degrees, so none of the survey runs true to the paper.
    """
    if filled:
        return None          # the white panels the contour labels sit in
    if not all(PLAN[0] - .02 <= x <= PLAN[2] + .02
               and PLAN[1] - .02 <= y <= PLAN[3] + .02 for x, y in pts):
        return None                                     # border, bottom strip
    if any(TITLE_BLOCK[0] <= x and TITLE_BLOCK[1] <= y for x, y in pts):
        return None
    if _axis_aligned(pts):
        return None                                     # tables, title block
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    near, _far, signed = offsets_from(cl, pts)
    if dashed:
        if lw <= 0.5:
            return "E-RAIL" if signed < -6.0 else "E-TOPO-MINR"
        if lw <= 1.0:
            return "V-ROAD-CF"
        return "E-TOPO-MAJR"
    if lw <= 1.0 and length > 10.0 and 0.8 < near < 2.2:
        return "V-ROW"
    # Guard railing and MGS are drawn as hatched diamonds and triangles riding
    # the shoulder edge (20 ft Lt) and the 21 ft Rt barrier line.
    if lw <= 1.0 and length <= 0.30:
        mid = (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts))
        if any(math.dist(mid, t) < 0.11 for t in tips):
            return None
        ft = signed * 50.0
        if -24.0 <= ft <= -16.0 or 19.0 <= ft <= 29.0:
            return "V-BARR"
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", default=str(EXISTING))
    ap.add_argument("--tol", type=float, default=0.004,
                    help="simplify tolerance, sheet inches (0.004 in = 0.2 ft)")
    args = ap.parse_args(argv)

    raw = read_paths(args.pdf)
    cl = centerline_paper()
    tips = _leader_tips(cl)
    out, dropped = {}, 0
    for p in raw:
        for sp in p['pts']:
            if len(sp) < 2:
                continue
            pts = [to_paper(q) for q in sp]
            layer = classify(p['lw'], p['dash'], pts, cl, tips, p['fill'])
            if layer is None:
                dropped += 1
                continue
            pts = simplify(pts, args.tol)
            out.setdefault(layer, []).append(
                [[round(v, 3) for v in G.paper_to_model(q)] for q in pts])

    labels = []
    for x, y, height, rot, text in group_runs(read_glyphs(args.pdf)):
        if not (text.isdigit() and 1400 <= int(text) <= 1600):
            continue
        if not (PLAN[0] <= x <= PLAN[2] and PLAN[1] <= y <= PLAN[3]):
            continue
        labels.append({"elevation": int(text), "at": [round(v, 3) for v in
                                                      G.paper_to_model((x, y))],
                       "height_ft": round(height * G.FEET_PER_INCH, 2),
                       "rotation_deg": round(rot - G.TWIST_DEG, 3)})

    Path(args.out).write_text(json.dumps({"polylines": out, "contour_labels": labels}))
    for layer, polys in sorted(out.items()):
        v = sum(len(p) for p in polys)
        print(f"{layer:<14} {len(polys):>5} polylines  {v:>6} vertices")
    print(f"{'contours':<14} {len(labels):>5} elevation labels")
    print(f"{'(left out)':<14} {dropped:>5} subpaths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
