# PPM-048 — Route 65 Layout, sheet L-4 (redraft)

Caltrans PPM example **"65 LAYOUT-4"**: 03-Pla-65, PM R11.9/R24.1, Route 65 Bypass. The sheet
shows the Industrial Avenue UC and OH bridges and the NB exit ramp to Industrial Avenue.
It is redrafted here as a RoadDraft file set named per the Caltrans CADD Users Manual.

Source: [`Sheets/Caltrans-PPM/…/PPM-048-Route-65-Layout-Example-65-LAYOUT-4.pdf`](../../../../Sheets/Caltrans-PPM/2-2.05-Layouts-Profiles-and-Superelevation-Diagrams/PPM-048-Route-65-Layout-Example-65-LAYOUT-4.pdf)

## Files

File names follow CADD Users Manual 2.2 and 3.8: the project number, then the file's code.
The sheet's title block gives the project number as "PROJECT NUMBER & PHASE 00000000001",
which is project `0000000000`, phase 1.

| File | Role | What it holds |
|---|---|---|
| `0000000000bb01.rdraft` | **BB01**, Master Topographic ("bb") | Existing features, drawn dotted: Union Pacific Railroad (`E-RAIL`), existing Industrial Avenue, curbs and fence (`E-TOPO`), and their names (`E-TOPO-TEXT`). 364 entities. |
| `0000000000aa01.rdraft` | **AA01**, Master Design, roadway ("aa") | The alignments `IND1`, `D13` and `IN4` as design data, with their centerlines, stationing, POT/POC/EC marks, names and bearings. Also the proposed roadway: edges, curbs, sidewalks, islands, bridges, approach slabs, barriers, fence, R/W and catch lines. 1,562 entities. References BB01, as the manual has the bb file referenced to the aa file. |
| — | **AA02**, drainage | **Not created.** This layout shows no drainage. |
| `0000000000ea004.rdraft` | Contract plan sheet **L-4** ("ea" = Layout, sheet 004) | Owns no design. It references AA01 and BB01 in model space, both clipped at the five match lines. Sheet `L-4` is ANSI D (34 × 22) with the Caltrans border, the title block filled from the sheet, and one 1" = 50' viewport (view twist −72.312°). Everything sheet-specific is placed in sheet view (249 entities): note, 33 callouts, match lines, curve data table, curve bubbles, widths, road names, travel arrows, north arrow, Caltrans logo. |
| `0000000000ea004.pdf` | Plot | Sheet L-4 at full size. |
| `0000000000ea004.dxf` | CAD exchange | For AutoCAD, Civil 3D or MicroStation: layout `L-4`, with the references bound in as `AA01$…` and `BB01$…` layers. |
| `0000000000ea004.png` | Render | 150 dpi. |
| `0000000000ea004-overlay.png` | Check | Published sheet in blue, redraft in red, black where they agree. |

Open `0000000000ea004.rdraft` in RoadDraft. It finds both base files beside it by relative path.

## Design data

The alignments are rebuilt from the numbers the plans print, not traced. Every station on
the sheet then comes out of the design model.

| Alignment | Geometry | Source |
|---|---|---|
| `IND1` (Industrial Avenue) | Tangent N 17°31'07" E. This file carries 50+00 to 64+00 of the 4833.49' tangent. | L-4 |
| `D13` (Route 65) | Curve 3, a left curve: R 5000', Δ 41°17'58", T 1884.32', L 3604.04'. BC 654+06.40, EC 690+10.44. POC 678+43.61 = `IND1` 55+90.29 POT. | L-4 table; BC from L-2, EC from L-5 |
| `IN4` (NB exit ramp) | Curve 36, a left curve: Δ 74°50'50", T 251.05', L 428.58', EC 681+58.69. Then N 72°28'52.9" W for 181.44' to POT 683+40.13 = `IND1` 59+72.49. | L-4 |

**Coordinates.** The PPM example prints no coordinates, so the model sits on a local datum:
`IND1` 55+90.29 POT is at E 10,000, N 10,000. The sheet↔model transform was fitted to the PDF:
- **Station ticks:** `IND1` ticks sit exactly 2.000 in apart.
- **D13 circle:** `D13` is a 100.00 in (5000 ft) circle through its ticks 675 to 682 (rms 0.0013 in).
- **POC:** `D13` crosses `IND1` at 55+90.29 to within 0.05 ft.
- **Centerlines:** the rebuilt centerlines lie within 0.02 in of the published ones.

## Callouts

All 33 callouts are RoadDraft `place_callout`s in sheet view, aimed through the viewport at
the referenced design:

- **8 at a station and offset** of a referenced alignment, as their text states them. Examples: `166.67' Lt "IND1" 53+19.96`, `"D13" 678+43.61 POC`, `"IN4" 681+58.69 EC`. Each lands within 0.05 in of the published leader tip.
- **17 at the referenced element** the published leader touches, at the same point along it. Examples: the MBGR and transition-railing stations, the bridge ends (EB/BB), the fence, the sidewalk ends.
- **8 at a point** where the published leader ends in an area, usually with Caltrans' `~` "area" squiggle. These are the bridges, approach slabs, MVP4, the ICO arrow and the exit-ramp note.

## Differences from the published sheet

- **Text size.** Text heights are the true Caltrans values (0.14", 0.175", 0.20" cap height), and the DXF carries them exactly. RoadDraft's renderer draws the height as the font size, so the PNG and PDF lettering looks smaller and narrower than the Caltrans font.
- **Callout second lines.** These are left-aligned with the first line. Caltrans indents them.
- **Curve 36 radius.** The table prints R 330'. The curve's own T, L and stations need R 328.08' (L / Δ), so the alignment uses 328.08' and the table still prints the sheet's 330'. Curve 3's R 5000' and its stations agree.
- **Fence callouts.** The two 34.78' callouts are aimed at their stated station and offset, which sits 0.045 in (2.3 ft) from where the published leaders end.
- **Curve data table.** It is a RoadDraft table, so its row height is the engine's and the grid is about 0.2 in shorter.
- **Seal.** The engineer's seal is the template's plain ring, without the ring lettering.
- **Layers.**
  - AA01 proposed linework is layered by Caltrans line style, with right of way picked out (`V-ROW`):
    - `V-ROAD-EDGE` heavy (edges of shoulder and structure)
    - `V-ROAD` medium (curbs, sidewalks, barriers, fence, bridges, islands)
    - `V-ROAD-THIN` (edges of traveled way, approach slabs)
    - `V-ROAD-CATCH` / `V-ROAD-CUT` (fill and cut catch lines)
  - Barriers, curbs and fence share `V-ROAD`.

## Rebuild

```bash
.venv/bin/python examples/ppm_redraft/make_l4.py
```

The pipeline is described in [`examples/ppm_redraft/README.md`](../../../../../ppm_redraft/README.md).
