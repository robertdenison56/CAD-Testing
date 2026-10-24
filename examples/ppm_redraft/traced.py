"""Lettering the published PDF draws as linework, found among a plan's leftover strokes.

Most lettering on the sample sheets has a text layer: its strokes are matched to the
strings and dropped (``match_glyphs``), and the strings are lettered again.  Some has
none -- a font outlined to paths, a CAD plot's stroke font, the dotted "DITCH" of an
existing ditch -- and its strokes reach the leftover routing like any other line, so
they end up in a base file on a roadway or topography layer: a bearing, a road name or
an elevation that reads as linework (pilot work, 2026-10-19: stripping an alignment's
annotation left its bearing behind as strokes).

``mark`` finds them: clusters of small strokes, each about a letter in size, close
together in a band a letter or two tall and a few letters long, drawn in more than one
direction.  It sets ``traced`` on their paths and leaves their routing alone, so they stay
in the file they went to and the build draws them on that file's trace layer
(``V-ANNO-TRACE`` and kin): plotted as before, but known for what they are.  It does not
read them: turning strokes into text would take OCR.

What it must not take: hatching and dash runs (one direction), rows of symbols spaced
apart (rail ties, fence marks, poles), a symbol on its own (a monument, a tree), and
island dot patterns.  ``trace_exclude`` boxes in a sheet's config keep a region out.
"""
import math
from collections import defaultdict

#: an entity no bigger than a letter, paper inches
MAX_STROKE_IN = 0.25
#: letters of a word sit this close, paper inches; a word found then takes in the
#: strokes on its own band up to GAP_ALONG_IN along it (lettering spaced wide)
GAP_IN = 0.06
GAP_ALONG_IN = 0.12
#: a word: a band at most this tall (a line or two of lettering) ...
MAX_BAND_IN = 0.35
MIN_BAND_IN = 0.035
#: ... at least this long, and this much longer than it is tall
MIN_LENGTH_IN = 0.12
MIN_ASPECT = 1.3
MAX_STROKES = 150
#: direction bins (degrees, on the band's own axis) a word's strokes fill
BIN_DEG = 30


def _extent(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return max(max(xs) - min(xs), max(ys) - min(ys))


def _bbox(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _closed(pts):
    return len(pts) > 3 and math.dist(pts[0], pts[-1]) < 0.004


def _clusters(cands):
    cell = 0.5
    grid = defaultdict(list)
    for i, p in enumerate(cands):
        b = p["_tb"]
        for gx in range(int(b[0] // cell), int(b[2] // cell) + 1):
            for gy in range(int(b[1] // cell), int(b[3] // cell) + 1):
                grid[(gx, gy)].append(i)
    seen, out = set(), []
    for i in range(len(cands)):
        if i in seen:
            continue
        seen.add(i)
        group, frontier = [i], [i]
        while frontier:
            q = cands[frontier.pop()]["_tb"]
            for gx in range(int((q[0] - GAP_IN) // cell), int((q[2] + GAP_IN) // cell) + 1):
                for gy in range(int((q[1] - GAP_IN) // cell), int((q[3] + GAP_IN) // cell) + 1):
                    for o in grid.get((gx, gy), ()):
                        if o in seen:
                            continue
                        b = cands[o]["_tb"]
                        if max(b[0], q[0]) - min(b[2], q[2]) < GAP_IN and \
                                max(b[1], q[1]) - min(b[3], q[3]) < GAP_IN:
                            seen.add(o); group.append(o); frontier.append(o)
        out.append([cands[k] for k in group])
    return out


def _thickness(pts, a):
    ca, sa = math.cos(a), math.sin(a)
    across = [-x * sa + y * ca for x, y in pts]
    return max(across) - min(across)


def _axis(pts):
    """The band's direction (radians): the one its points are thinnest across, as a
    line of lettering is across its baseline. (A principal axis tilts with the
    accents and apostrophes riding high on a short word.)"""
    best = min(range(0, 180, 2), key=lambda d: _thickness(pts, math.radians(d)))
    fine = min((best + k / 4.0 for k in range(-8, 9)),
               key=lambda d: _thickness(pts, math.radians(d)))
    return math.radians(fine)


def _straight(pts) -> bool:
    a, b = pts[0], pts[-1]
    L = math.dist(a, b)
    if L < 1e-6:
        return False
    return all(abs((q[0] - a[0]) * (b[1] - a[1]) - (q[1] - a[1]) * (b[0] - a[0])) / L < 0.004
               for q in pts)


def _crosses(group) -> set:
    """Strokes that pair up as an X -- two straight strokes of a length crossing
    near both their middles: a fence mark or a monument, not a letter (a lettered X
    stands among other letters, which keep the word)."""
    lines = [p for p in group if _straight(p["pts"])]
    out = set()
    for i, p in enumerate(lines):
        a, b = p["pts"][0], p["pts"][-1]
        for q in lines[i + 1:]:
            c, d = q["pts"][0], q["pts"][-1]
            l1, l2 = math.dist(a, b), math.dist(c, d)
            if min(l1, l2) < 0.7 * max(l1, l2):
                continue
            ang = abs(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])
                                   - math.atan2(d[1] - c[1], d[0] - c[0]))) % 180
            if not 50 <= ang <= 130:
                continue
            m1 = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            m2 = ((c[0] + d[0]) / 2, (c[1] + d[1]) / 2)
            if math.dist(m1, m2) < 0.2 * min(l1, l2):
                out.add(id(p)); out.add(id(q))
    return out


def _round_loop(pts) -> bool:
    """A closed loop as wide as it is tall: a circle symbol (a shrub, a pole), where a
    lettered O or 0 is taller than it is wide."""
    if not _closed(pts):
        return False
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    return min(w, h) > 0 and max(w, h) / min(w, h) < 1.15


def is_lettering(group):
    """Does a cluster of small strokes read as a word?"""
    if not 3 <= len(group) <= MAX_STROKES:
        return False
    tiny_closed = sum(1 for p in group if _closed(p["pts"]) and _extent(p["pts"]) < 0.06)
    if tiny_closed > 0.8 * len(group):
        return False                                  # an island dot pattern
    if sum(1 for p in group if _round_loop(p["pts"])) >= 0.5 * len(group):
        return False                                  # a row of circle symbols
    crossed = _crosses(group)
    letters = [p for p in group if id(p) not in crossed]
    if len(letters) < 3 or len(crossed) >= 4:
        return False                                  # X marks along a line
    pts = [q for p in group for q in p["pts"]]
    a = _axis(pts)
    ca, sa = math.cos(a), math.sin(a)
    along = [x * ca + y * sa for x, y in pts]
    across = [-x * sa + y * ca for x, y in pts]
    length, band = max(along) - min(along), max(across) - min(across)
    if not (MIN_BAND_IN <= band <= MAX_BAND_IN and length >= MIN_LENGTH_IN
            and length >= MIN_ASPECT * band):
        return False
    # each stroke is a letter's: none runs on along the band much past a letter's
    # width (a line piece between fence marks, a stretch of a curve)
    spans = []
    for p in group:
        al = [x * ca + y * sa for x, y in p["pts"]]
        if max(al) - min(al) > 1.5 * band:
            return False
        acr = [-x * sa + y * ca for x, y in p["pts"]]
        spans.append((min(al), max(al), max(acr) - min(acr) >= 0.5 * band))
    # and the letters stand side by side along it: at least two places where the
    # strokes do not overlap, each with a stroke a letter tall (a symbol's strokes
    # sit over one another; a tick beside a dash is one tall stroke)
    units = []
    for lo, hi, tall in sorted(spans):
        if units and lo < units[-1][1] - 0.3 * min(hi - lo, units[-1][1] - units[-1][0]):
            units[-1][1] = max(units[-1][1], hi)
            units[-1][2] = units[-1][2] or tall
        else:
            units.append([lo, hi, tall])
    if sum(1 for u in units if u[2]) < 2:
        return False
    # the strokes run in more than one direction: letters have uprights and
    # crossbars or curves; hatching, dashes and tick rows run one way
    weight = defaultdict(float)
    total = 0.0
    for p in letters:
        for u, v in zip(p["pts"], p["pts"][1:]):
            d = math.dist(u, v)
            if d < 1e-6:
                continue
            ang = (math.degrees(math.atan2(v[1] - u[1], v[0] - u[0])) - math.degrees(a)) % 180
            weight[int(((ang + BIN_DEG / 2) % 180) // BIN_DEG)] += d
            total += d
    if total <= 0 or sum(1 for w in weight.values() if w >= 0.1 * total) < 2 \
            or max(weight.values()) > 0.75 * total:
        return False                                  # one way: hatching, a tick row
    # and they stand a letter tall: a good share reach most of the way across the band
    tall = 0
    for p in letters:
        acr = [-x * sa + y * ca for x, y in p["pts"]]
        if max(acr) - min(acr) >= 0.5 * band:
            tall += 1
    return tall >= 0.3 * len(letters)


def mark(paths, keep=lambda p: True, exclude=()):
    """Set ``traced`` on every leftover path (``dest`` None, ``keep(p)``) that is part
    of lettering drawn as strokes; returns how many words were found."""
    def excluded(p):
        return any(all(b[0] <= x <= b[2] and b[1] <= y <= b[3] for x, y in p["pts"])
                   for b in exclude)

    cands = []
    for p in paths:
        if p["dest"] is not None or len(p["pts"]) < 2 or not keep(p) or excluded(p):
            continue
        ext = _extent(p["pts"])
        if 0.004 <= ext <= MAX_STROKE_IN:
            p["_tb"] = _bbox(p["pts"])
            cands.append(p)
    words = []
    for group in _clusters(cands):
        if is_lettering(group):
            words.append(group)
            for p in group:
                p["traced"] = True
    letters = [{"strokes": g, "bbox": (min(p["_tb"][0] for p in g), min(p["_tb"][1] for p in g),
                                        max(p["_tb"][2] for p in g), max(p["_tb"][3] for p in g))}
               for g in _clusters([p for p in cands if not p.get("traced")])]
    for group in words:
        _grow(group, letters)
    for p in cands:
        p.pop("_tb", None)
    return len(words)


def _grow(word, letters):
    """Take in the letters lettered on a word's own band, a little apart from it: a
    bearing spaced wide (N 01°05'14" W) is found a piece at a time. ``letters`` are
    the clusters of the strokes no word took (``{"strokes", "bbox"}``); one joins
    whole, or not at all."""
    pts = [q for p in word for q in p["pts"]]
    a = _axis(pts)
    ca, sa = math.cos(a), math.sin(a)
    across = [-x * sa + y * ca for x, y in pts]
    lo_c, hi_c = min(across), max(across)
    band = hi_c - lo_c
    along = [x * ca + y * sa for x, y in pts]
    lo_a, hi_a = min(along), max(along)
    wb = _bbox(pts)
    reach = GAP_ALONG_IN * 8 + band
    nearby = [L["strokes"] for L in letters
              if L["bbox"][0] < wb[2] + reach and L["bbox"][2] > wb[0] - reach
              and L["bbox"][1] < wb[3] + reach and L["bbox"][3] > wb[1] - reach]
    grew = True
    while grew:
        grew = False
        for g in nearby:
            if g[0].get("traced"):
                continue
            gp = [q for p in g for q in p["pts"]]
            al = [x * ca + y * sa for x, y in gp]
            ac = [-x * sa + y * ca for x, y in gp]
            on_band = min(ac) >= lo_c - 0.2 * band and max(ac) <= hi_c + 0.2 * band
            near = min(al) - hi_a < GAP_ALONG_IN and lo_a - max(al) < GAP_ALONG_IN
            # a letter, not a dash of the line the lettering sits in: a part of a
            # letter tall, and no wider than a letter or two
            letter = max(ac) - min(ac) >= 0.3 * band and max(al) - min(al) <= 2.5 * band \
                and all(max(x * ca + y * sa for x, y in p["pts"]) - min(x * ca + y * sa for x, y in p["pts"])
                        <= 1.5 * band for p in g)
            if on_band and near and letter:
                for p in g:
                    p["traced"] = True
                word.extend(g)
                lo_a, hi_a = min(lo_a, min(al)), max(hi_a, max(al))
                grew = True
