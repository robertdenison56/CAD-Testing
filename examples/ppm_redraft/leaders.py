"""Find callout leaders on a digitised plan sheet: thin chains that start at a text's
landing (or underline) and run to what the callout points at."""
import math


def plen(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def seg_dist(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def poly_dist(p, pts):
    if len(pts) == 1:
        return math.dist(p, pts[0])
    return min(seg_dist(p, a, b) for a, b in zip(pts, pts[1:]))


def closed(p):
    return len(p["pts"]) > 3 and math.dist(p["pts"][0], p["pts"][-1]) < 0.012


def landings(run, thin, under_extra=2.6, side_extra=0.9):
    """thin straight legs that underline the run or leave from its end at mid height:
    [(path, leg)]"""
    a = math.radians(run["rot"]); ca, sa = math.cos(a), math.sin(a)
    ox, oy = run["x"], run["y"]
    L = (run["end"][0] - ox) * ca + (run["end"][1] - oy) * sa
    h = run["h"]
    out = []
    for p in thin:
        if closed(p):
            continue
        for pts in (p["pts"][:2], p["pts"][-2:]):
            seg = math.dist(pts[0], pts[1])
            if seg < 0.03:
                continue
            al = [(x - ox) * ca + (y - oy) * sa for x, y in pts]
            ac = [-(x - ox) * sa + (y - oy) * ca for x, y in pts]
            if max(ac) - min(ac) > max(0.01, 0.006 * seg):
                continue
            y = sum(ac) / len(ac)
            under = (-0.09 <= y <= -0.005 and min(al) < L * 0.3 and max(al) > L * 0.7
                     and seg <= L + under_extra)
            near_end = (-0.05 < min(al) - L < 0.2) or (-0.05 < -max(al) < 0.2)
            side = 0.25 * h <= y <= 0.75 * h and near_end and seg <= L + side_extra
            if under or side:
                out.append((p, [tuple(pts[0]), tuple(pts[1])]))
                break
    return out


def component(start, leg, thin, others, tol=0.006, touch=0.008, branch=4.0, bend=0.4,
              thin_grid=None, other_grid=None):
    """Leader paths reachable from the landing path `start`, and where they stop.

    Paths join end to end.  Short bends may leave the landing leg part way along it,
    and short branches may meet a leader at one of their interior vertices (a leader
    that splits in two).  A point that touches other linework (or sits at the centre
    of a small marker circle) ends the walk -- unless a branch meets there."""
    markers = [p for p in others if closed(p) and max(math.dist(p["pts"][0], q) for q in p["pts"]) < 0.2]
    thin_ids = {p["id"] for p in thin}

    def touches(pt, skip):
        pool = other_grid.near((pt[0], pt[1], pt[0], pt[1]), touch) if other_grid else others
        for o in pool:
            if o["id"] in skip or o["id"] in thin_ids:
                continue
            xs = [q[0] for q in o["pts"]]; ys = [q[1] for q in o["pts"]]
            if not (min(xs) - touch <= pt[0] <= max(xs) + touch and
                    min(ys) - touch <= pt[1] <= max(ys) + touch):
                continue
            if poly_dist(pt, o["pts"]) < touch:
                return True
        for m in markers:
            cx = sum(q[0] for q in m["pts"]) / len(m["pts"])
            cy = sum(q[1] for q in m["pts"]) / len(m["pts"])
            if math.dist(pt, (cx, cy)) < 0.03:
                return True
        return False

    seen = {start["id"]: start}
    frontier = []
    lb = (min(leg[0][0], leg[1][0]), min(leg[0][1], leg[1][1]), max(leg[0][0], leg[1][0]), max(leg[0][1], leg[1][1]))
    for p in (thin_grid.near(lb, tol) if thin_grid else thin):
        if p["id"] in seen or closed(p) or plen(p["pts"]) > bend:
            continue
        for k in (0, -1):
            if seg_dist(p["pts"][k], leg[0], leg[1]) < tol:
                seen[p["id"]] = p
                frontier.append(p["pts"][-1] if k == 0 else p["pts"][0])
                break
    frontier += [start["pts"][0], start["pts"][-1]]
    while frontier:
        pt = frontier.pop()
        ends, verts = [], []
        pool = thin_grid.near((pt[0], pt[1], pt[0], pt[1]), tol) if thin_grid else thin
        for p in pool:
            if p["id"] in seen or closed(p):
                continue
            if math.dist(p["pts"][0], pt) < tol or math.dist(p["pts"][-1], pt) < tol:
                ends.append(p)
            elif plen(p["pts"]) <= branch and any(math.dist(v, pt) < tol for v in p["pts"][1:-1]):
                verts.append(p)
        if verts:
            for p in verts:
                seen[p["id"]] = p
                frontier += [p["pts"][0], p["pts"][-1]]
        elif touches(pt, set(seen)):
            continue
        else:
            for p in ends:
                seen[p["id"]] = p
                frontier.append(p["pts"][-1] if math.dist(p["pts"][0], pt) < tol else p["pts"][0])
    return list(seen.values())


def ends_of(paths, leg, text_mid, squiggle=0.13):
    """(text end, tips, decoration path ids).  Short leaf strokes at a leader's end (a
    squiggle or arrowhead) are decorations: the tip is where they meet the leader."""
    def degree(ps):
        """[[point, count]] of path ends, ends within 0.006 in counted together"""
        deg = []
        for p in ps:
            for q in (p["pts"][0], p["pts"][-1]):
                hit = next((d for d in deg if math.dist(d[0], q) < 0.006), None)
                if hit is None:
                    deg.append([tuple(q), 1])
                else:
                    hit[1] += 1
        return deg

    def count_at(deg, q):
        return next((d[1] for d in deg if math.dist(d[0], q) < 0.006), 0)
    ps = list(paths)
    deco = []
    for _ in range(3):
        deg = degree(ps)
        cut = []
        for p in ps:
            if len(ps) - len(cut) <= 1:
                break
            if plen(p["pts"]) < squiggle:
                a = count_at(deg, p["pts"][0]) == 1
                b = count_at(deg, p["pts"][-1]) == 1
                if a != b:
                    cut.append(p)
        if not cut:
            break
        deco += [p["id"] for p in cut]
        ps = [p for p in ps if p not in cut]
    deg = degree(ps)
    def on_other(q):
        return any(poly_dist(q, p["pts"]) < 0.006 for p in ps
                   if math.dist(q, p["pts"][0]) > 0.006 and math.dist(q, p["pts"][-1]) > 0.006)
    leaves = [q for q, n in deg if n == 1 and not on_other(q)]
    # the text end: an outer end of the landing leg that nothing else joins
    lp = [q for q in leg if any(math.dist(q, l) < 0.006 for l in leaves)]
    if lp:
        text_end = min(lp, key=lambda q: math.dist(q, text_mid))
    else:
        text_end = min(leg, key=lambda q: math.dist(q, text_mid))
    tips = []
    for q in leaves:
        if math.dist(q, text_end) < 0.006:
            continue
        if seg_dist(q, leg[0], leg[1]) < 0.006 and len(ps) > 1:
            continue          # on the landing: its far end past a branch, or a bend's root
        tips.append(q)
    return text_end, tips, deco
