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
                # the next letter starts further along, and not past a word gap beyond
                # this one's advance (kerning can pull it well inside the advance)
                step = along(c) - along(p)
                d_across = abs(across(c) - across(p))
                same = d_across < 0.25 * p["size"] and 0.05 * p["size"] <= step <= p["adv"] + gap_k * p["size"] \
                    and abs(c["size"] - p["size"]) < 0.35 * p["size"]
                if not same:
                    out.append(cur); cur = []
            cur.append(c)
        if cur: out.append(cur)
    # a run of two or more spaces is a column gap: the text layer places what follows
    # with its own font's space widths, not the drawn lettering's, so split there and
    # let the piece be re-anchored on its strokes
    pieces = []
    for r in out:
        cur, spaces, split = [], 0, False
        for c in r:
            if not c["t"].strip():
                spaces += 1
                cur.append(c)
                continue
            if spaces >= 2 and any(x["t"].strip() for x in cur):
                pieces.append((cur, split)); cur, split = [], True
            spaces = 0
            cur.append(c)
        if cur:
            pieces.append((cur, split))
    res = []
    for r, split in pieces:
        text = "".join(c["t"] for c in r)
        if not text.strip():
            continue
        # strip leading/trailing spaces but keep position of first non-space
        i0 = next(i for i, c in enumerate(r) if c["t"].strip())
        i1 = max(i for i, c in enumerate(r) if c["t"].strip())
        r = r[i0:i1 + 1]
        a = math.radians(r[0]["rot"])
        end = (r[-1]["x"] + r[-1]["adv"] * math.cos(a), r[-1]["y"] + r[-1]["adv"] * math.sin(a))
        res.append({"split": split, "font": r[0].get("font"), "color": r[0].get("color"),
                    "nchars": len(r),
                    "text": "".join(c["t"] for c in r), "x": r[0]["x"], "y": r[0]["y"],
                    "rot": r[0]["rot"], "size": max(c["size"] for c in r), "end": end,
                    "chars": r})
    return res
