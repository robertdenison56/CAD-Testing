# MAIN ST / CROSS AVE — a signal-ready intersection

A design-model file for a four-leg intersection at 90 degrees, drafted from
design data rather than from coordinates.

```bash
python examples/intersection/build_intersection.py
```

Output: `examples/output/Main-Cross-Intersection.model.rdraft` — 2 alignments,
~330 entities on 11 layers, drafted for 1" = 40'.

## What it draws

| | MAIN ST (E–W) | CROSS AVE (N–S) |
|---|---|---|
| through lanes | **3 each way** @ 12' | **2 each way** @ 12' |
| striped median | 16' (8' each side of the alignment) | 16' |
| curb face | 44' from CL | 32' from CL |
| curb face at a right-turn lane | 56' | 44' |
| curb and gutter | 6', face to back | 6' |
| stationing | 10+00 – 26+00, intersection at 18+00 | 20+00 – 34+00, intersection at 27+00 |

Every one of the four approaches gets both turn lanes:

* a **left-turn pocket** taken out of the median — 12' wide, so it crosses the
  alignment to 4' LT and leaves the standard 4' painted separation against the
  opposing through lanes. Opposing pockets sit on opposite legs, which is what
  lets both of them use the same median;
* a **right-turn lane** taken out of the curb line, which moves the curb out by
  one lane and leaves the old curb offset behind as the lane line.

Both are **300' of full-width storage behind a 120' bay taper** (12' in 120' is
the standard 10:1), measured back from the curb return.

The corners are **50' curb returns** on the curb face with the 6' curb and
gutter carried around them on a concentric 44' arc, and **eight curb ramps** —
one on each leg of each corner, 4' wide across the 6' curb and gutter with
1:10 flared sides and a detectable warning surface at the gutter.

## How it is drafted

Nothing in the file is a typed coordinate.

* Lane lines, median edges, curb faces and back-of-curb runs are **constant
  offsets of an alignment**, drawn leg by leg with `draw_offset station_range`
  so each one stops clear of the intersection and picks up again on the far
  leg. Each piece stays anchored to the alignment and the offset it came from.
* Bay tapers, pocket edges and curb-line tapers are placed at a **station and
  offset** on the alignment they belong to.
* Curb returns are fitted between the two curb lines they join: the centre sits
  one radius inside each, so the tangent points and the arc fall out of the
  geometry. Every arc end meets its curb line to 0.000 ft.
* Curb ramps are one **block** inserted eight times, each rotated to the
  outward normal of the curb it sits on (verified square to within 0°).
* The 12' lane, 16' median, 6' curb, 300' storage, 120' taper and 50' radius
  are **dimensioned**, so those numbers are measured off the drawing rather
  than lettered onto it.

Change a number in `intersection_design.py` and the whole intersection moves
with it — lane count, lane width, median width, storage, taper, radius, curb
width are each one constant.

## Reading it back

```python
s.query("station_to_xy", {"alignment": "MAIN-ST", "station": "17+54", "offset": -4})
s.query("find_entities", {"anchor": {"alignment": "MAIN-ST", "kind": "offset",
                                     "offset": [-56, -44]}})
```

## Not included

Crosswalks, limit lines, signal equipment, lane-use arrows and a profile. The
striping stops a limit-line setback clear of the crossings, so there is room
for them; say the word and they go in.
