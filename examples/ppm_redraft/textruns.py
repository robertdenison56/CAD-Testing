"""Group text-layer characters into runs (words/lines) along their baseline."""
import math

def runs(chars, gap_k=0.9):
    """chars: dicts with t, x, y, size, rot, adv. Returns runs with text, origin,
    rotation, size, end point."""
    by_rot = {}
    for c in chars:
        if not c["t"].strip():
            c = dict(c)  # keep spaces as separators
        key = round(c["rot"])
        by_rot.setdefault(key, []).append(c)
    out = []
    for key, bucket in by_rot.items():
        ang = math.radians(sum(c["rot"] for c in bucket) / len(bucket))
        ca, sa = math.cos(ang), math.sin(ang)
        # order by line (across) then along
        def across(c): return -c["x"] * sa + c["y"] * ca
        def along(c): return c["x"] * ca + c["y"] * sa
        bucket.sort(key=lambda c: (round(across(c) / 0.02), along(c)))
        cur = []
        for c in bucket:
            if cur:
                p = cur[-1]
                d_along = along(c) - (along(p) + p["adv"])
                d_across = abs(across(c) - across(p))
                same = d_across < 0.25 * p["size"] and -0.3 * p["size"] <= d_along <= gap_k * p["size"] \
                    and abs(c["size"] - p["size"]) < 0.2 * p["size"]
                if not same:
                    out.append(cur); cur = []
            cur.append(c)
        if cur: out.append(cur)
    res = []
    for r in out:
        text = "".join(c["t"] for c in r)
        if not text.strip():
            continue
        # strip leading/trailing spaces but keep position of first non-space
        i0 = next(i for i, c in enumerate(r) if c["t"].strip())
        i1 = max(i for i, c in enumerate(r) if c["t"].strip())
        r = r[i0:i1 + 1]
        a = math.radians(r[0]["rot"])
        end = (r[-1]["x"] + r[-1]["adv"] * math.cos(a), r[-1]["y"] + r[-1]["adv"] * math.sin(a))
        res.append({"text": "".join(c["t"] for c in r), "x": r[0]["x"], "y": r[0]["y"],
                    "rot": r[0]["rot"], "size": max(c["size"] for c in r), "end": end,
                    "chars": r})
    return res
