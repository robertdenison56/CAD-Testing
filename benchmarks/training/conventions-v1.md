# Office drafting conventions: roadway layout sheets

These are this office's standing conventions. Follow them wherever a request does not say otherwise; a value the request gives wins.

## What a request covers
- A plan sheet: the sheet and its viewport, the centerline, the stationing, the curve points, the curve numbers, the bearings, the curve data table, the north arrow and the title block. A layout on more than one sheet breaks at a match line.
- A line's alignment data: the stationing, curve points, curve numbers, bearings and curve data table. Annotating a sheet is all of that plus the north arrow and the title block.
- Stationing a line: the ticks, their numbers, and the station of every curve point (BC and EC) and every station equation.
- Numbering the curves: a numbered bubble at every curve. Bearings: bearing and distance on every tangent.
- Pavement: the edges of pavement both sides of the centerline, through the curves, and the width dimensioned across every tangent.
- Draw all of it, on every sheet the request names, and nothing it does not ask for. Leave work already in the file as it is.

## Layers
Nothing is ever drafted on layer 0, the current layer when a file opens: give every command its layer, or set the current layer first, and create a standard layer that is missing before you use it.
- align_MAIN: the centerline.
- align_MAIN-anno: station ticks and numbers, curve point labels, curve numbers, bearings.
- align_CURVE-DATA: the curve data table.
- rd_EP: edges of pavement. rd_LAYOUT-NOTE-anno: width dimensions.
- pp_PRESENTATION: the north arrow (block NORTH_ARROW).
- border_INSIDE-BORDER-anno: match lines and their labels.

A layout file carries all of these: align_MAIN (black, 0.5 mm), align_MAIN-anno, align_CURVE-DATA, rd_EP (0.35 mm), rd_ETW, rd_ES, rd_LAYOUT-NOTE-anno (0.18 mm), rd_RIGHT-OF-WAY and rd_RIGHT-OF-WAY-anno (cyan), pp_PRESENTATION, pp_LEGEND-anno, border_SHEET (0.7 mm), border_PROJ-ID-BLOCK-anno (magenta), border_INSIDE-BORDER-anno (magenta, 0.35 mm), border_SEAL and border_SIGNATURE (yellow). Unless noted a layer is black at 0.25 mm.

## Sheets
- Sheets are ANSI D, or ANSI B on the wfl and fdot borders. One viewport per sheet at 1" = 40' or 1" = 50', whichever shows that sheet's whole part of the line inside the usable area (get_sheet_state reports it).
- North arrow in the upper right of every sheet, clear of the title block, turned with a turned viewport so it points north as plotted.
- Fill every title block field the document's project data (get_document_state) and the request give; the scale reads like 1" = 50' and matches the viewport. Leave a field blank rather than invent it.
- Match line: square across the centerline at the break, 100 ft each side, labelled at its end on each sheet MATCH LINE STA <station> SEE SHEET <other sheet>.

## Lettering
Sizes are on paper; in model space multiply by the feet per inch (0.10 in at 1" = 50' is 5 ft).
- Labels and notes 0.10 in, tables 0.12 in, station ticks 0.14 in long across the line.
- Stationing the Caltrans way: a tick every 100 ft, the number 0.12 in below the line, the full station every 500 ft and only the ones digit between.
- Curve points: station then word, to the hundredth (24+05.27 BC), 0.45 in off the line on its left, square to it, reading bottom to top. Station equations the same way (STA 20+00.00 BK = STA 25+00.00 AH).
- Curve numbers 1, 2, ... in order along the line, never restarted on the next sheet, each in a bubble 0.80 in off the right of the curve with a leader to it.
- Bearing and distance above the middle of each tangent, 0.06 in off the line, parallel to it: quadrant bearing to the second, distance to the hundredth (N 71°33'54" E 1240.36').
- Curve data table on each sheet, titled CURVE DATA, columns No., R, Δ, T, L, Δ in degrees, minutes and seconds, lengths to the hundredth, one row for each curve the sheet shows.
- Width dimension: aligned, edge to edge, at the half station nearest the middle of each tangent, the width to the hundredth with a foot mark.
- Construction notes go on the sheet as callouts, 0.14 in text, the leader aimed through the line at the station and offset given.

## Legible on the plotted sheet
- No label, note or table may overlap another, and no dimension line or leader may cross lettering. Put the table and notes in open paper; text touching an edge line is fine.
- Everything stays inside the usable area: inside the border, off the title block, not cut by a viewport's edge.
- Lettering reads upright as plotted. Where a viewport is turned, give the labelling commands its twist (view_rotation).

## Before you submit
A failed command drew nothing: read the error, fix the call and run it again until the piece is on the sheet. Check each sheet against the list above with the queries. Never submit an empty drawing.
