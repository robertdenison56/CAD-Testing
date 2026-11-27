"""Rebuild alignments from a plan sheet's centerline linework, its station ticks and
its station numbers.

A Caltrans plan draws each alignment line heavy, ticks it every 100 ft, and letters
the ticks: the whole station at each 500 ft ("675", "55", "60"), otherwise the last
digit.  From that:

  * the heavy linework is chained and split into tangents and circular curves (each
    PDF path is one straight segment or one flattened arc);
  * the ticks along a chain, and the numbers beside them, give the station at every
    tick, and so the direction of stationing and the station at the chain's start;
  * a '"NAME" LINE' (or '"NAME"') label alongside names the alignment;
  * a bearing lettered along a tangent ('N17°31'07"E ...') gives the sheet's view
    twist, so the rebuilt model reads true bearings.

Everything here is in sheet inches; fit() returns elements in sheet inches, which the
builder carries into the model through the sheet's transform.
"""
import math
import re

NUMBER = re.compile(r"^\d{1,4}$")
NAME = re.compile(r'^"([A-Za-z0-9\-]+)"(\s*LINE)?$')
BEARING = re.compile(r"([NS])\s*(\d{1,2})[°^](\d{1,2})['’](\d{1,2}(?:\.\d+)?)[\"”]\s*([EW])")


def dist_seg(p, a, b):
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy), t


def fit_circle(pts):
    n = len(pts)
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    suu = svv = suv = suuu = svvv = suvv = svuu = 0.0
    for x, y in pts:
        u, v = x - mx, y - my
        suu += u * u; svv += v * v; suv += u * v
        suuu += u * u * u; svvv += v * v * v; suvv += u * v * v; svuu += v * u * u
    det = suu * svv - suv * suv
    if abs(det) < 1e-12:
        return None
    b1 = 0.5 * (suuu + suvv)
    b2 = 0.5 * (svvv + svuu)
    uc = (b1 * svv - b2 * suv) / det
    vc = (b2 * suu - b1 * suv) / det
    cx, cy = uc + mx, vc + my
    r = sum(math.hypot(x - cx, y - cy) for x, y in pts) / n
    res = max(abs(math.hypot(x - cx, y - cy) - r) for x, y in pts)
    return cx, cy, r, res


def straightness(pts):
    a, b = pts[0], pts[-1]
    return max((dist_seg(p, a, b)[0] for p in pts[1:-1]), default=0.0)


class Chain:
    def __init__(self, parts):
        self.parts = parts            # [(path id, [points])] in order, end to end
    @property
    def pts(self):
        out = []
        for _, p in self.parts:
            out += p if not out else p[1:]
        return out
    def length(self):
        p = self.pts
        return sum(math.dist(a, b) for a, b in zip(p, p[1:]))
    def reverse(self):
        self.parts = [(i, list(reversed(p))) for i, p in reversed(self.parts)]
    def locate(self, q):
        """(distance from the chain, along-chain position, unit tangent there)"""
        best = None
        run = 0.0
        p = self.pts
        for a, b in zip(p, p[1:]):
            L = math.dist(a, b)
            d, t = dist_seg(q, a, b)
            if best is None or d < best[0]:
                u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L else (1.0, 0.0)
                best = (d, run + t * L, u)
            run += L
        return best


def chains_of(paths, tol=0.012):
    """Join paths end to end into chains."""
    parts = [(p["id"], list(map(tuple, p["pts"]))) for p in paths]
    chains = []
    while parts:
        cur = [parts.pop(0)]
        grown = True
        while grown:
            grown = False
            head, tail = cur[0][1][0], cur[-1][1][-1]
            for i, (pid, pts) in enumerate(parts):
                if math.dist(pts[0], tail) < tol:
                    cur.append((pid, pts)); parts.pop(i); grown = True; break
                if math.dist(pts[-1], tail) < tol:
                    cur.append((pid, pts[::-1])); parts.pop(i); grown = True; break
                if math.dist(pts[-1], head) < tol:
                    cur.insert(0, (pid, pts)); parts.pop(i); grown = True; break
                if math.dist(pts[0], head) < tol:
                    cur.insert(0, (pid, pts[::-1])); parts.pop(i); grown = True; break
        chains.append(Chain(cur))
    return chains


def _unit(a, b):
    L = math.dist(a, b)
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L else None


def dedupe(paths, tol=0.005):
    """One line drawn twice (often once each way) is kept once."""
    out, seen = [], []
    for p in paths:
        pts = p["pts"]
        if any(len(q) == len(pts) and (all(math.dist(a, b) < tol for a, b in zip(q, pts)) or
                                       all(math.dist(a, b) < tol for a, b in zip(q, pts[::-1])))
               for q in seen):
            continue
        seen.append(pts)
        out.append(p)
    return out


def split_reversals(chain):
    """A chain that turns sharply split where it turns: a spur drawn out and back, or
    two centerlines meeting at a corner.  (An alignment's angle points deflect a few
    degrees; nothing on one turns through 60.)"""
    parts = []
    for pid, pts in chain.parts:
        cur = [pts[0]]
        for i in range(1, len(pts) - 1):
            cur.append(pts[i])
            u, v = _unit(pts[i - 1], pts[i]), _unit(pts[i], pts[i + 1])
            if u and v and u[0] * v[0] + u[1] * v[1] < 0.5:
                parts.append((pid, cur))
                cur = [pts[i]]
        cur.append(pts[-1])
        parts.append((pid, cur))
    pieces, cur = [], []
    for pid, pts in parts:
        if plen(pts) < 0.01:
            continue
        if cur:
            u = _unit(cur[-1][1][-2], cur[-1][1][-1])
            v = _unit(pts[0], pts[1])
            if u and v and u[0] * v[0] + u[1] * v[1] < 0.5:
                pieces.append(Chain(cur))
                cur = []
        cur.append((pid, pts))
    if cur:
        pieces.append(Chain(cur))
    return pieces


def plen(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def elements_of(chain, max_r=4000.0):
    """Tangents and curves along a chain, sheet inches, joined end to end."""
    raw = []
    for _, pts in chain.parts:
        if len(pts) == 2 or straightness(pts) < 0.003:
            raw.append(["tangent", pts[0], pts[-1]])
            continue
        fc = fit_circle(pts)
        if fc and fc[3] < 0.006 and fc[2] < max_r:
            raw.append(["curve", pts[0], pts[-1], (fc[0], fc[1]), fc[2], pts[len(pts) // 2]])
        else:
            for a, b in zip(pts, pts[1:]):
                raw.append(["tangent", a, b])
    # merge collinear tangents and co-circular curves
    out = []
    for e in raw:
        if out and e[0] == out[-1][0] == "tangent":
            a, _b = out[-1][1], out[-1][2]
            if dist_seg(out[-1][2], a, e[2])[0] < 0.002:
                out[-1][2] = e[2]
                continue
        if out and e[0] == out[-1][0] == "curve":
            c0, r0 = out[-1][3], out[-1][4]
            if math.dist(c0, e[3]) < 0.01 * max(r0, 1) and abs(r0 - e[4]) < 0.003 * r0:
                out[-1][2] = e[2]
                continue
        out.append(e)
    return out


def arcs_from_chords(els, max_r=4000.0, tol=0.006):
    """A curve drawn as a run of short chords (five or more tangents that lie on one
    circle) read as the curve; two or three tangents meeting at slight angle points
    stay tangents.  For a line numbered from a config's readings, where
    the PDF flattens every arc to two-point segments."""
    out, i = [], 0
    while i < len(els):
        best = None
        if els[i][0] == "tangent":
            j = i
            while j + 1 < len(els) and els[j + 1][0] == "tangent":
                j += 1
                if j - i + 1 < 5:
                    continue
                pts = [els[i][1]] + [e[2] for e in els[i:j + 1]]
                fc = fit_circle(pts)
                if not fc or fc[3] > tol or fc[2] > max_r:
                    break
                # chords of one curve are short beside its radius and turn one way
                if max(math.dist(e[1], e[2]) for e in els[i:j + 1]) > 0.5 * fc[2]:
                    break
                best = (j, fc, pts)
        if best:
            j, fc, pts = best
            out.append(["curve", pts[0], pts[-1], (fc[0], fc[1]), fc[2], pts[len(pts) // 2]])
            i = j + 1
        else:
            out.append(els[i])
            i += 1
    return out


def well_formed(els):
    """An alignment runs one way: no closed curve, no element doubling back on the last."""
    prev = None
    for e in els:
        if math.dist(e[1], e[2]) < 0.02:
            return False
        if e[0] == "tangent":
            u = ((e[2][0] - e[1][0]), (e[2][1] - e[1][1]))
            n = math.hypot(*u)
            u = (u[0] / n, u[1] / n)
            if prev is not None and u[0] * prev[0] + u[1] * prev[1] < -0.5:
                return False
            prev = u
        else:
            prev = None
    return True


def ticks_along(chain, segs, spacing):
    """Station ticks on a chain: [(along, point, half_len)]"""
    found, halves = [], []
    pts = chain.pts
    x0 = min(p[0] for p in pts) - 0.3; x1 = max(p[0] for p in pts) + 0.3
    y0 = min(p[1] for p in pts) - 0.3; y1 = max(p[1] for p in pts) + 0.3
    for a, b in segs:
        if not (x0 <= a[0] <= x1 and y0 <= a[1] <= y1):
            continue
        L = math.dist(a, b)
        if not 0.035 < L < 0.24:
            continue
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        d, along, u = chain.locate(m)
        if d > L / 2 + 0.02:
            continue
        v = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        if abs(u[0] * v[0] + u[1] * v[1]) > 0.12:
            continue
        if d <= 0.02 and L > 0.07:
            found.append((along, m, L / 2))
            continue
        # a tick drawn as two halves, each from the line out to one side
        for e, o in ((a, b), (b, a)):
            de, ae, ue = chain.locate(e)
            if de < 0.01 and abs(d - L / 2) < 0.015:
                side = ue[0] * (o[1] - e[1]) - ue[1] * (o[0] - e[0])
                halves.append((ae, e, L, side > 0))
                break
    halves.sort()
    for h0, h1 in zip(halves, halves[1:]):     # both halves, one each side, or none
        if h1[0] - h0[0] < 0.02 and h0[3] != h1[3]:
            found.append((h0[0], h0[1], max(h0[2], h1[2])))
    found.sort()
    # keep ticks on the 100 ft rhythm
    if len(found) < 2:
        return found
    best = []
    for i, (a0, _, _) in enumerate(found):
        keep = [t for t in found if abs(((t[0] - a0) / spacing) - round((t[0] - a0) / spacing)) < 0.02]
        if len(keep) > len(best):
            best = keep
    return best


def label_ticks(ticks, runs, spacing):
    """Station (ft) at each tick from the numbers beside them, or None."""
    labelled = []
    for i, (along, m, half) in enumerate(ticks):
        near = None
        for r in runs:
            if not NUMBER.match(r["text"]):
                continue
            c = r["center"]
            d = math.dist(c, m)
            if 0.08 < d < 0.5 and (near is None or d < near[0]):
                near = (d, r)
        labelled.append(near[1] if near else None)
    if not ticks:
        return None
    a0 = ticks[0][0]
    ks = [round((t[0] - a0) / spacing) for t in ticks]
    best = None
    for direction in (1, -1):
        for i, r in enumerate(labelled):
            if r is None or len(r["text"]) < 2:
                continue
            h0 = int(r["text"]) - direction * ks[i]
            score = 0
            for k, rr in zip(ks, labelled):
                if rr is None:
                    continue
                h = h0 + direction * k
                t = rr["text"]
                if (len(t) >= 2 and int(t) == h) or (len(t) == 1 and h % 10 == int(t)):
                    score += 1
                else:
                    score -= 2
            if best is None or score > best[0]:
                best = (score, direction, h0)
    if best is None or best[0] < 2:
        return None
    _, direction, h0 = best
    return direction, [(h0 + direction * k) * 100.0 for k in ks], labelled


def hinted(ticks, hints, spacing):
    """Stations from a config's own reading of two ticks (``hints``: [{"name", "ticks":
    [[x, y, station ft], [x, y, station ft]]}], sheet inches), for a sheet that letters
    its station numbers as strokes: (direction, stations, name) or None."""
    a0 = ticks[0][0]
    ks = [round((t[0] - a0) / spacing) for t in ticks]
    for h in hints or ():
        got = []
        for x, y, sta in h["ticks"]:
            near = min(range(len(ticks)), key=lambda i: math.dist(ticks[i][1], (x, y)))
            if math.dist(ticks[near][1], (x, y)) > 0.15:
                break
            got.append((ks[near], float(sta)))
        if len(got) != 2 or got[0][0] == got[1][0]:
            continue
        (k1, s1), (k2, s2) = got
        direction = 1 if (s2 - s1) * (k2 - k1) > 0 else -1
        if abs(abs(s2 - s1) - 100.0 * abs(k2 - k1)) > 1.0:
            continue                  # the two readings do not fit the ticks between them
        return direction, [s1 + direction * (k - k1) * 100.0 for k in ks], h.get("name")
    return None


def fit(heavy_paths, short_segs, runs, fpi, min_len=3.0, hints=None):
    """Alignments found on the sheet: list of dicts (sheet inches), each with
    elements, begin station (ft), name, ticks and the labels used.  ``hints``
    (a config's ``stations``) number a line whose ticks no lettering numbers."""
    spacing = 100.0 / fpi
    for r in runs:
        a = math.radians(r["rot"])
        L = math.dist((r["x"], r["y"]), r["end"])
        r.setdefault("center", (r["x"] + math.cos(a) * L / 2 - math.sin(a) * r["h"] / 2,
                                r["y"] + math.sin(a) * L / 2 + math.cos(a) * r["h"] / 2))
    out = []
    pieces = [pc for ch in chains_of(dedupe(heavy_paths)) for pc in split_reversals(ch)]
    for ch in pieces:
        if ch.length() < min_len or math.dist(ch.pts[0], ch.pts[-1]) < 0.05:
            continue
        if not well_formed(elements_of(ch)):
            continue
        ticks = ticks_along(ch, short_segs, spacing)
        if len(ticks) < 2:
            continue
        lab = label_ticks(ticks, runs, spacing)
        told = None
        if lab is None:
            told = hinted(ticks, hints, spacing)
            if told is None:
                continue
            lab = (told[0], told[1], [None] * len(ticks))
        direction, stations, labels = lab
        if direction < 0:
            ch.reverse()
            ticks = sorted((ch.length() - a, m, h) for a, m, h in ticks)
            stations = list(reversed(stations))
            labels = list(reversed(labels))
        # station at the chain's start: least squares over the ticks
        begin = sum(s - a * fpi for (a, _, _), s in zip(ticks, stations)) / len(ticks)
        resid = max(abs(begin + a * fpi - s) for (a, _, _), s in zip(ticks, stations))
        if resid > 10.0 or ticks[-1][0] > ch.length() + 0.05:
            continue                  # the numbers do not belong to these ticks
        name = (0.0, told[2], True) if told and told[2] else None
        for r in ([] if name else runs):
            m = NAME.match(r["text"].strip())
            if not m:
                continue
            d, _, u = ch.locate(r["center"])
            if d < 0.6 and (name is None or (m.group(2) and not name[2]) or d < name[0]):
                name = (d, m.group(1), bool(m.group(2)))
        els = arcs_from_chords(elements_of(ch)) if told else elements_of(ch)
        out.append({"chain": ch, "paths": [pid for pid, _ in ch.parts], "elements": els,
                    "begin_station": begin, "fit_residual_ft": resid,
                    "name": name[1] if name else None, "name_dist": name[0] if name else None,
                    "hinted": bool(told),
                    "ticks": ticks, "stations": stations,
                    "labels": [r["id"] if r else None for r in labels]})
    return out


def twist_from_bearings(aligns, runs):
    """The sheet's view twist (degrees CCW) from bearings lettered along tangents."""
    cands = []
    for r in runs:
        m = BEARING.search(r["text"].replace(" ", ""))
        if not m:
            continue
        ns, d, mi, s, ew = m.groups()
        q = int(d) + int(mi) / 60 + float(s) / 3600
        az = {("N", "E"): q, ("S", "E"): 180 - q, ("S", "W"): 180 + q, ("N", "W"): 360 - q}[(ns, ew)]
        for al in aligns:
            for e in al["elements"]:
                if e[0] != "tangent":
                    continue
                dd, t = dist_seg(r["center"], e[1], e[2])
                if dd > 0.6 or not 0.0 < t < 1.0:
                    continue
                th = math.degrees(math.atan2(e[2][1] - e[1][1], e[2][0] - e[1][0]))
                if abs(((th - r["rot"]) + 90) % 180 - 90) > 4:
                    continue
                tw = th - (90.0 - az)
                cands.append((tw + 180.0) % 360.0 - 180.0)
    if not cands:
        return None
    cands.sort()
    return cands[len(cands) // 2]


def tidy(aligns, fpi):
    """Fits that are one alignment, made consistent.

    * A line drawn twice, or a piece of one: the shorter fit, lying along a longer
      one, goes.
    * A centerline broken where three lines meet (a curve's end, a ramp's nose):
      fits that meet end to start with the stationing running on are joined.
    * Two fits that took one label: the name stays with the nearer one.
    Returns (kept fits, dropped fits)."""
    dropped = []
    kept = []
    for al in sorted(aligns, key=lambda a: -a["chain"].length()):
        pts = al["chain"].pts
        sample = pts[::max(1, len(pts) // 12)] + [pts[-1]]
        if any(sum(k["chain"].locate(q)[0] < 0.06 for q in sample) >= 0.8 * len(sample) for k in kept):
            dropped.append(al)
            continue
        kept.append(al)
    joined = True
    while joined:
        joined = False
        for a in kept:
            end_pt = a["elements"][-1][2]
            end_sta = a["begin_station"] + a["chain"].length() * fpi
            for b in kept:
                if b is a or (a["name"] and b["name"] and a["name"] != b["name"]):
                    continue
                if math.dist(end_pt, b["elements"][0][1]) < 0.03 and abs(end_sta - b["begin_station"]) < 3.0:
                    La = a["chain"].length()
                    a["chain"] = Chain(a["chain"].parts + b["chain"].parts)
                    a["paths"] += b["paths"]
                    a["elements"] += b["elements"]
                    a["ticks"] += [(along + La, m, h) for along, m, h in b["ticks"]]
                    a["stations"] += b["stations"]
                    a["labels"] += b["labels"]
                    a["fit_residual_ft"] = max(a["fit_residual_ft"], b["fit_residual_ft"])
                    if not a["name"]:
                        a["name"], a["name_dist"] = b["name"], b["name_dist"]
                    kept.remove(b)
                    joined = True
                    break
            if joined:
                break
    by_name = {}
    for al in kept:
        if al["name"]:
            by_name.setdefault(al["name"], []).append(al)
    for same in by_name.values():
        for al in sorted(same, key=lambda a: a["name_dist"])[1:]:
            al["name"] = None
    return kept, dropped

