"""Human-play mode: an AutoCAD-command-line-style REPL over the exact same
Session tool surface the AI uses (PRD section 5.4). If a PE can't draft a
100-score sheet through these commands, the action space is broken - not the
model.

Syntax: <command> [positional args] [key=value ...]
Values: numbers, 'x,y' points, true/false, JSON arrays/objects, or strings.
Drawing commands go to the current space (see 'space'); 'render' shows the
result. Sessions are recorded: 'journal <path>' saves a replayable trajectory.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys

from roaddraft.api.lines import REPL_ALIASES, build_params, print_params, resolve_verb
from roaddraft.api.session import QUERIES, Session

HELP = """RoadDraft REPL - same tool surface the AI uses.

Drafting (current space applies; see 'space'):
  line 0,0 100,50 [layer=NAME]        pline 0,0 50,0 50,25 [closed=true]
  arc center=X,Y radius=R start_angle_deg=A end_angle_deg=B
  circle 25,25 10                     text 5,5 "STA 12+00" height=0.15
  insert NORTH_ARROW 31.5,19 scale=1  table position=26,8 columns=[...] rows=[...]
  move TX-001 delta=0.5,0             erase TX-001 LN-002
  modify_entity id=TX-001 changes={"content":"NEW"}
Layers & styles:
  mklayer NAME color=red linetype=center lineweight_mm=0.35
  layer NAME            (set current layer)      layers
Sheets:
  sheet C-101 size=ANSI_D               sheets
  viewport sheet=C-101 center_paper=17,12 width_in=31 height_in=18 \\
           model_center=1700,1150 feet_per_inch=50
  titleblock C-101 project="SR 100" sheet_title="ROADWAY PLAN"
  space C-101 | space model             (where drawing commands go)
Design (alignments, profiles, anchored labels):
  alignment NAME x,y x,y,R x,y begin_station=10+00   (PIs: [x,y,R] interior)
  drawalign NAME [layer=L]              station alignment=NAME [interval=100]
  label PC-1 [NAME] [kind=pc side=right rotation=along content="..."]
  curvetable 24,8.5 NAME                (on a sheet: space C-101 first)
  profile NAME ALIGN sta,elev sta,elev,L ...   alignments
  sta2xy 16+00 NAME [offset]            xy2sta 1300,1012 NAME
  design curves|tangents|anchors|equations|profiles|pvis|vcs [NAME]
  anchor PC-1 [NAME]                    (dry run of label)
  offset 12L 12R [alignment=NAME]       edge of pavement (right +; edge = offset)
  landxmlin PATH                        landxml [PATH]   (import / export)
  alignment NAME start=1000,3000 legs='["S80E 800","40L 700 R=500","25R 600 R=700"]'
                                        (a layout by bearings and distances)
Coordinate geometry, editing and inquiry:
  bd 1000,3000 "S 80-00-00 E 800" "40L 700" "CURVE R=300 RIGHT L=200" [close=true]
                                        draw by bearing & distance (also: cogo, trav)
  bd LN-003 "15R 200"                   carry on from the end of an entity
  traverse 0,0 "N45E 100" "90R 100" close=true   compute only: points + closure
  offset LN-001 12 left | offset LN-001 12L 12R | offset LN-001 through=1200,950
  offset LN-001 AR-001 LN-002 -12 12    a chain, offset as one path (join=round)
  fillet LN-001 LN-002 50 [keep=[[x,y],[x,y]] trim=false]   (radius 0 = corner)
  dist 1300,980 1500,1030 along=LN-001  along & square off a line, chain or alignment
  snap 1601,1001 [tolerance=5 modes=["endpoint","intersection"] from=X,Y]
  keypoints LN-001 LN-002 | keypoints alignment=SR-100
  so 30+00@12R 31+20@24R 36+00@24R 36+00@12R [alignment=SR-100 polyline=true]
                                        draw through stations and offsets
Modify:
  trim LN-005 2986,2399 [LN-006 3014,2399] [boundaries=CI-001]   cut the part clicked
  trim LN-005 keep 2986,2100            keep the part at the point, cut the rest
  extend LN-005 end [boundaries=LN-003 extend_boundaries=true]
  break LN-004 1500,1012 [1560,1012]   split at a point, or cut out the part between
  join LN-001 AR-001 LN-002             one line / arc, or one polyline with arcs
  explode PL-003 BR-001                 into lines, arcs, text (hatch: boundaries)
  chamfer LN-001 LN-002 10 [20]   lengthen LN-005 end 12.5 (or total= percent= to=x,y)
  copy LN-001 20,0 [count=3] | copy LN-001 0,0 20,0     (from, to)
  rotate PL-001 1500,1200 30 [copy=true] | rotate ... angle="30 CW"
  mirror LN-020 AR-005 1000,1000 1600,1000 [keep_original=false]
  scale BR-002 31.5,19 0.5 | array BR-003 kind=path path=SR-100 every=50 offset=2R
COGO points, labels, hatching:
  point 1500,2000 [1534,2059 ...] description=MON | points text="1,2000,1500,101.2,MON"
  pointtable 26,20 [points=1-12]        a table of points (on the current space)
  labelseg PL-004 [style=tags table={"position":[2500,1400]} order_along=SR-100]
  along SR-100 every=200 offset=14R [block=DELINEATOR] | divide LN-001 count=5
  hatch 1700,988 ANSI31 [40] | hatch PL-002 CI-001 SOLID opacity=0.5
  area 1700,988 | area PL-002 | list LN-001   area, perimeter; LIST properties
Annotation scale (paper-size annotation at a plot scale):
  annoscale 100 | annoscale 1:1200 | annoscale off     annoscales
  annoadd 25 [name]  annodel 25   annopaper text_height_in=0.12 label_offset_in=0.35
Viewing & files:
  state [full] | entities [space] | extents [space] | blocks | styles | journal
  render [sheet] [dpi=N] [open]  |  rendermodel [open]
  print [model|SHEET|all] [paper=ANSI_B scale=1:2|50|fit orientation=portrait \\
        monochrome=true margin_in=0.25 bounds=x0,y0,x1,y1] [open]
        (plot with page setup: prints the current space by default)
  dxf [path] | pdf [path] | save PATH | journal PATH | opendoc PATH
Other:
  help [command] | undo | redo | quit
Any Session command/query works verbatim: name key=value ... (help NAME shows
its schema). C3D-style aliases (LINE, PLINE, ERASE, MVIEW...) also resolve.
"""


def repl_params(name: str, args: list, current_space: str):
    params, unexpected = build_params(name, args, current_space)
    for token in unexpected:
        print(f"  ! unexpected argument {token!r}")
    return params


def print_result(result: dict):
    if result.get("ok"):
        print(f"  {result.get('message', 'ok')}")
        for w in result.get("warnings", []):
            print(f"  warning: {w}")
    else:
        err = result.get("error", {})
        print(f"  ERROR ({err.get('type')}): {err.get('message')}")
        if err.get("hint"):
            print(f"  hint: {err['hint']}")
        if err.get("example"):
            print(f"  example: {json.dumps(err['example'])}")


def _open_file(path: str):
    if sys.platform == "darwin":
        subprocess.run(["open", path], check=False)


class Repl:
    def __init__(self, session: Session):
        self.session = session
        self.space = "model"

    # ------------------------------------------------------------ builtins

    def do_help(self, args):
        if not args:
            print(HELP)
            return
        name = REPL_ALIASES.get(args[0].lower(), args[0])
        manifest = self.session.manifest()
        for item in manifest["commands"] + manifest["queries"]:
            if item["name"].lower() == name.lower():
                print(f"  {item['name']} ({item['kind']}): {item['description']}")
                print(f"  schema: {json.dumps(item['params_schema'], indent=2)}")
                print(f"  example: {json.dumps(item['example'])}")
                return
        print(f"  no command or query named {name!r}")

    def do_state(self, args):
        detail = "full" if args and args[0] == "full" else "summary"
        result = self.session.query("get_document_state", {"detail": detail})
        print(json.dumps(result.get("summary") or result.get("document"), indent=2))

    def do_entities(self, args):
        space = args[0] if args else self.space
        if space == "model":
            result = self.session.query("get_model_state")
            entities = result.get("entities", [])
        else:
            result = self.session.query("get_sheet_state", {"sheet": space})
            if not result["ok"]:
                print_result(result)
                return
            entities = list(result["sheet"]["entities"].values())
        for e in entities:
            print(f"  {json.dumps(e)}")
        print(f"  ({len(entities)} entities in {space})")

    def do_render(self, args):
        args = list(args)
        want_open = "open" in args
        if want_open:
            args.remove("open")
        params = {}
        for a in list(args):
            if a.startswith("dpi="):
                params["dpi"] = float(a[4:])
                args.remove(a)
        sheets = [s["name"] for s in self.session.doc.sheets.values()] \
            if not args else [args[0]]
        if not sheets:
            print("  no sheets yet; create one with: sheet C-101")
            return
        for name in sheets:
            result = self.session.query("render_sheet", {"sheet": name, **params})
            if result["ok"]:
                print(f"  rendered {name} -> {result['path']}")
                if want_open:
                    _open_file(result["path"])
            else:
                print_result(result)

    def do_rendermodel(self, args):
        result = self.session.query("render_model")
        if result["ok"]:
            print(f"  rendered model -> {result['path']}")
            if "open" in args:
                _open_file(result["path"])
        else:
            print_result(result)

    def do_print(self, args):
        args = list(args)
        want_open = "open" in args
        if want_open:
            args.remove("open")
        params, unexpected = print_params(args, self.space)
        for token in unexpected:
            print(f"  ! unexpected argument {token!r}")
        result = self.session.query("print_pdf", params)
        if not result["ok"]:
            print_result(result)
            return
        for page in result["pages"]:
            print(f"  {page['space']} -> {page['paper']} "
                  f"({page['paper_in'][0]:g} x {page['paper_in'][1]:g} in) "
                  f"at {page['scale']}")
        print(f"  printed {result['page_count']} page(s) -> {result['path']}")
        if want_open:
            _open_file(result["path"])

    def do_simple_query(self, qname, key=None, args=()):
        params = {key: args[0]} if key and args else {}
        result = self.session.query(qname, params)
        if result["ok"]:
            result.pop("ok"), result.pop("name")
            print(json.dumps(result, indent=2))
        else:
            print_result(result)

    # ------------------------------------------------------------- dispatch

    def dispatch(self, line: str) -> bool:
        try:
            tokens = shlex.split(line, posix=True)
        except ValueError as ex:
            print(f"  parse error: {ex}")
            return True
        if not tokens:
            return True
        cmd, args = tokens[0], tokens[1:]
        low = cmd.lower()

        if low in ("quit", "exit", "q"):
            return False
        if low == "help":
            self.do_help(args)
        elif low == "state":
            self.do_state(args)
        elif low == "entities":
            self.do_entities(args)
        elif low == "layers":
            self.do_simple_query("list_layers")
        elif low == "styles":
            self.do_simple_query("list_text_styles")
        elif low == "blocks":
            self.do_simple_query("list_blocks")
        elif low == "sheets":
            self.do_simple_query("list_sheets")
        elif low == "extents":
            self.do_simple_query("get_extents", "space", args or [self.space])
        elif low == "journal" and args:
            self.do_simple_query("save_journal", "path", args)
        elif low == "journal":
            self.do_simple_query("get_journal")
        elif low == "render":
            self.do_render(args)
        elif low == "rendermodel":
            self.do_rendermodel(args)
        elif low == "dxf":
            self.do_simple_query("export_dxf", "path", args)
        elif low == "pdf":
            self.do_simple_query("export_pdf", "path", args)
        elif low in ("print", "plot"):
            self.do_print(args)
        elif low == "landxml":
            self.do_simple_query("export_landxml", "path", args)
        elif low == "alignments":
            self.do_simple_query("list_alignments")
        elif low == "annoscales":
            self.do_simple_query("list_annotation_scales")
        elif low == "save":
            self.do_simple_query("save_document", "path", args)
        elif low == "opendoc" and args:
            self.session = Session.load(args[0], out_dir=self.session.out_dir)
            self.space = "model"
            print(f"  loaded {args[0]}")
        elif low == "space":
            if not args:
                print(f"  current space: {self.space}")
            elif args[0] == "model" or self.session.doc.sheet_by_ref(args[0]):
                self.space = args[0]
                print(f"  drawing into: {self.space}")
            else:
                print(f"  no space {args[0]!r}; "
                      f"valid: {self.session.doc.space_refs()}")
        elif low == "layer" and args:
            print_result(self.session.execute("set_current_layer",
                                              {"name": args[0]}))
        else:
            name = resolve_verb(low, args)
            if name == low and low not in REPL_ALIASES:
                name = cmd
            resolved = self.session.bus.resolve(name)
            canonical = resolved.name if resolved else name
            if canonical in QUERIES:
                params = repl_params(canonical, args, self.space)
                result = self.session.query(canonical, params)
                if result["ok"]:
                    result.pop("ok"), result.pop("name")
                    print(json.dumps(result, indent=2)[:4000])
                else:
                    print_result(result)
            else:
                params = repl_params(canonical, args, self.space)
                print_result(self.session.execute(canonical, params))
        return True

    def loop(self):
        doc = self.session.doc
        print(f"RoadDraft {__import__('roaddraft').__version__} - "
              f"{doc.meta['project_name']}")
        print("Type 'help' for commands, 'quit' to exit. "
              f"Renders go to {self.session.out_dir}/")
        while True:
            try:
                line = input(f"RD [{self.space}]> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not self.dispatch(line):
                break


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="roaddraft",
        description="RoadDraft human-play REPL (the AI's tool surface, "
                    "driven by hand)")
    parser.add_argument("document", nargs="?",
                        help="saved document JSON to open")
    parser.add_argument("--project", default="Untitled",
                        help="project name for a new document")
    parser.add_argument("--out-dir", default=None,
                        help="directory for renders/exports (default ./renders)")
    parser.add_argument("--script", default=None,
                        help="run REPL commands from a file, then continue")
    parser.add_argument("--exit", action="store_true",
                        help="with --script: exit after running the script")
    ns = parser.parse_args(argv)

    if ns.document:
        session = Session.load(ns.document, out_dir=ns.out_dir)
    else:
        session = Session(project_name=ns.project, out_dir=ns.out_dir)
    repl = Repl(session)

    if ns.script:
        for line in open(ns.script):
            line = line.strip()
            if line and not line.startswith("#"):
                print(f"RD [{repl.space}]> {line}")
                repl.dispatch(line)
        if ns.exit:
            return 0
    if sys.stdin.isatty() or not ns.script:
        repl.loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
