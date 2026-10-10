"""Find a published Caltrans sheet's border and the transform back to a full-size
34 x 22 sheet.

The PPM example PDFs are reduced prints: the drawing sits inside the page at some scale
and offset.  The Caltrans border's main frame (the heavy rectangle, 1.904 / 0.503 in from
the left / bottom of a 34 x 22 sheet, 33.497 / 21.497 at the far corner) is found among the
longest axis-aligned lines, and gives both.  An extracted point e maps to the full-size
sheet point (e - offset) / scale.
"""
import math

MAIN = (1.904, 0.503, 33.497, 21.497)          # RoadDraft's caltrans template main border
DEFAULT = (0.95445, (0.7602, 0.5002))          # what PPM-048 measured; most pages agree


def _segments(D, min_len):
    for p in D["paths"]:
        for sub in p["subs"]:
            for a, b in zip(sub, sub[1:]):
                L = math.dist(a, b)
                if L >= min_len:
                    yield a, b, p["lw"], L


def calibrate(D):
    """(scale, (ox, oy), how) for an extract (extract_pdf.py JSON)."""
    W, H = D["page_in"]
    hz, vt = [], []
    for a, b, lw, L in _segments(D, min(W, H) * 0.35):
        if abs(a[1] - b[1]) < 0.01:
            hz.append((min(a[0], b[0]), max(a[0], b[0]), (a[1] + b[1]) / 2, lw))
        elif abs(a[0] - b[0]) < 0.01:
            vt.append((min(a[1], b[1]), max(a[1], b[1]), (a[0] + b[0]) / 2, lw))
    best = None
    for lw in sorted({h[3] for h in hz} | {v[3] for v in vt}, reverse=True):
        H_ = [h for h in hz if h[3] == lw and h[1] - h[0] > W * 0.6]
        V_ = [v for v in vt if v[3] == lw and v[1] - v[0] > H * 0.6]
        if len(H_) < 2 or len(V_) < 2:
            continue
        y0, y1 = min(h[2] for h in H_), max(h[2] for h in H_)
        x0, x1 = min(v[2] for v in V_), max(v[2] for v in V_)
        sx = (x1 - x0) / (MAIN[2] - MAIN[0])
        sy = (y1 - y0) / (MAIN[3] - MAIN[1])
        if abs(sx - sy) / sx < 0.01 and 0.5 < sx < 2.5:
            s = (sx + sy) / 2
            best = (s, (x0 - MAIN[0] * s, y0 - MAIN[1] * s), f"border lw {lw}")
            break
    if best is None:
        return DEFAULT[0], DEFAULT[1], "default (no border found)"
    return best
