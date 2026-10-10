"""Shared helpers: PDF-extract JSON -> full-size sheet inches, text runs, glyph masks."""
import gzip, json, math
from textruns import runs as _runs

class Sheet:
    def __init__(self, path, scale, offset):
        if isinstance(path, dict):
            self.D = path
        else:
            opener = gzip.open if str(path).endswith(".gz") else open
            with opener(path, "rt") as fh:
                self.D = json.load(fh)
        self.s = scale
        self.o = offset

    def P(self, p):
        return ((p[0] - self.o[0]) / self.s, (p[1] - self.o[1]) / self.s)

    def paths(self):
        out = []
        for i, p in enumerate(self.D["paths"]):
            for j, sub in enumerate(p["subs"]):
                pts = [self.P(q) for q in sub]
                out.append({"id": f"p{i}.{j}", "pts": pts, "lw": p["lw"],
                            "dash": tuple(p["dash"]) if p["dash"] else None,
                            "fill": p["fill"] and (p.get("fill_color") is None or p["fill_color"] < 0.5),
                            "mask": p["fill"] and (p.get("fill_color") or 0) >= 0.5,
                            "stroke": p["stroke"], "stroke_color": p.get("stroke_color")})
        return out

    def runs(self):
        good = [c for c in self.D["chars"] if c["size"] > 0.01 and -1 < c["x"] < 40 and -1 < c["y"] < 30]
        out = []
        for k, r in enumerate(_runs(good)):
            ox, oy = self.P((r["x"], r["y"]))
            ex, ey = self.P(r["end"])
            size = r["size"] / self.s
            out.append({"id": f"t{k}", "text": r["text"], "x": ox, "y": oy, "rot": r["rot"],
                        "size": size, "h": size * 1.12, "end": (ex, ey), "split": r.get("split", False),
                        "font": r.get("font"), "color": r.get("color")})
        return out

def run_box(r, pad_along=0.04, below=0.4, above=1.35):
    """Oriented box (origin, unit along, unit across, length, lo, hi) around a run."""
    a = math.radians(r["rot"]); ca, sa = math.cos(a), math.sin(a)
    L = (r["end"][0] - r["x"]) * ca + (r["end"][1] - r["y"]) * sa
    return (r["x"], r["y"], ca, sa, -pad_along, L + pad_along, -below * r["h"], above * r["h"])

def in_box(pts, box):
    ox, oy, ca, sa, a0, a1, c0, c1 = box
    for x, y in pts:
        al = (x - ox) * ca + (y - oy) * sa
        ac = -(x - ox) * sa + (y - oy) * ca
        if not (a0 <= al <= a1 and c0 <= ac <= c1):
            return False
    return True

def extent(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return max(max(xs) - min(xs), max(ys) - min(ys))

def is_glyph(path, boxes, hmax):
    if extent(path["pts"]) > hmax * 1.25:
        return False
    return any(in_box(path["pts"], b) for b in boxes)


class Grid:
    """A uniform grid over bounding boxes, for 'what is near here' without testing
    every path against every other."""
    def __init__(self, cell=0.5):
        self.cell = cell
        self.cells = {}

    def _keys(self, x0, y0, x1, y1):
        c = self.cell
        for i in range(int(x0 // c), int(x1 // c) + 1):
            for j in range(int(y0 // c), int(y1 // c) + 1):
                yield (i, j)

    def add(self, item, bbox):
        for k in self._keys(*bbox):
            self.cells.setdefault(k, []).append(item)

    def near(self, bbox, pad=0.0):
        x0, y0, x1, y1 = bbox
        seen, out = set(), []
        for k in self._keys(x0 - pad, y0 - pad, x1 + pad, y1 + pad):
            for it in self.cells.get(k, ()):
                if id(it) not in seen:
                    seen.add(id(it))
                    out.append(it)
        return out


def bbox_of(pts):
    xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def box_bbox(box):
    """Axis-aligned bounds of an oriented run box (run_box)."""
    ox, oy, ca, sa, a0, a1, c0, c1 = box
    pts = [(ox + a * ca - c * sa, oy + a * sa + c * ca) for a in (a0, a1) for c in (c0, c1)]
    return bbox_of(pts)
