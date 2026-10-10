"""Clipping paths for pdfplumber: pdfminer ignores W / W*, so a path drawn inside a
clip (a hatch pattern clipped to its boundary) comes out unclipped.  install() makes
the interpreter keep the clip stack and tags every painted object with the clip
polygons in force (device space, PDF points, origin bottom left), as obj["clip"]."""
import pdfminer.converter as C
import pdfminer.pdfinterp as I
import pdfplumber.page as P
from pdfminer.utils import apply_matrix_pt

_done = False


def _flatten(path, ctm):
    polys, cur, start = [], [], None
    for op in path:
        c = op[0]
        if c == "m":
            if len(cur) > 2:
                polys.append(cur)
            cur = [apply_matrix_pt(ctm, op[1:3])]
            start = cur[0]
        elif c == "l":
            cur.append(apply_matrix_pt(ctm, op[1:3]))
        elif c in ("c", "v", "y"):
            pts = [op[i:i + 2] for i in range(1, len(op), 2)]
            p0 = cur[-1] if cur else apply_matrix_pt(ctm, pts[0])
            q = [apply_matrix_pt(ctm, p) for p in pts]
            if c == "c":
                p1, p2, p3 = q
            elif c == "v":
                p1, p2, p3 = p0, q[0], q[1]
            else:
                p1, p2, p3 = q[0], q[1], q[1]
            for k in range(1, 9):
                t = k / 8; u = 1 - t
                cur.append((u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                            u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]))
        elif c == "h" and cur and start:
            pass
    if len(cur) > 2:
        polys.append(cur)
    return [tuple(map(tuple, p)) for p in polys]


def install():
    global _done
    if _done:
        return
    _done = True
    P.ALL_ATTRS.add("clip")
    Interp = I.PDFPageInterpreter

    orig_init = Interp.init_state
    def init_state(self, ctm):
        orig_init(self, ctm)
        self._clip = getattr(self, "_parent_clip", ())
        self._clipstack = []
        self._pending = None
        self.device._interp = self
    Interp.init_state = init_state

    orig_dup = Interp.dup
    def dup(self):
        child = orig_dup(self)
        child._parent_clip = getattr(self, "_clip", ())
        return child
    Interp.dup = dup

    orig_Do = Interp.do_Do
    def do_Do(self, xobjid):
        saved = getattr(self.device, "_interp", None)
        try:
            orig_Do(self, xobjid)
        finally:
            self.device._interp = saved
    Interp.do_Do = do_Do

    orig_q, orig_Q = Interp.do_q, Interp.do_Q
    def do_q(self):
        self._clipstack.append(self._clip)
        orig_q(self)
    def do_Q(self):
        if self._clipstack:
            self._clip = self._clipstack.pop()
        orig_Q(self)
    Interp.do_q, Interp.do_Q = do_q, do_Q

    def do_W(self):
        self._pending = _flatten(self.curpath, self.ctm)
    Interp.do_W = do_W
    Interp.do_W_a = do_W

    def wrap(name):
        orig = getattr(Interp, name)
        def op(self, *a):
            r = orig(self, *a)
            if self._pending:
                self._clip = self._clip + (tuple(self._pending),)
            self._pending = None
            return r
        setattr(Interp, name, op)
    for name in ("do_n", "do_S", "do_s", "do_f", "do_F", "do_f_a", "do_B", "do_B_a", "do_b", "do_b_a"):
        wrap(name)

    orig_pp = C.PDFLayoutAnalyzer.paint_path
    def paint_path(self, gstate, stroke, fill, evenodd, path):
        objs = self.cur_item._objs
        n = len(objs)
        orig_pp(self, gstate, stroke, fill, evenodd, path)
        interp = getattr(self, "_interp", None)
        clip = getattr(interp, "_clip", ()) if interp is not None else ()
        if clip:
            for o in objs[n:]:
                o.clip = clip
    C.PDFLayoutAnalyzer.paint_path = paint_path


# ------------------------------------------------------------- clipping a polyline
def _inside(pt, polys):
    """Even-odd over every polygon of a clip region."""
    x, y = pt
    n = 0
    for poly in polys:
        m = len(poly)
        for i in range(m):
            (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % m]
            if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                n += 1
    return n % 2 == 1


def _cuts(a, b, polys):
    """Fractions along a-b where it crosses a region edge."""
    ts = []
    dx, dy = b[0] - a[0], b[1] - a[1]
    for poly in polys:
        m = len(poly)
        for i in range(m):
            p, q = poly[i], poly[(i + 1) % m]
            ex, ey = q[0] - p[0], q[1] - p[1]
            den = dx * ey - dy * ex
            if abs(den) < 1e-12:
                continue
            t = ((p[0] - a[0]) * ey - (p[1] - a[1]) * ex) / den
            u = ((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / den
            if 1e-9 < t < 1 - 1e-9 and -1e-9 <= u <= 1 + 1e-9:
                ts.append(t)
    return sorted(ts)


def clip_polyline(pts, polys):
    """The parts of a polyline inside a clip region: a list of polylines."""
    out, cur = [], []
    for a, b in zip(pts, pts[1:]):
        ts = [0.0] + _cuts(a, b, polys) + [1.0]
        for t0, t1 in zip(ts, ts[1:]):
            if t1 - t0 < 1e-9:
                continue
            p0 = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
            p1 = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
            mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
            if _inside(mid, polys):
                if not cur:
                    cur = [p0]
                cur.append(p1)
            elif cur:
                out.append(cur)
                cur = []
    if cur:
        out.append(cur)
    return [c for c in out if len(c) > 1]
