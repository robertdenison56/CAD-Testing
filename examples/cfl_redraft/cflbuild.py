"""How CFL names its files, as a wflbuild.Naming: the CFL file naming convention
(highways.dot.gov, Federal Lands > Plan Prep > CFL > File Naming Convention):

    XXX(YYYY)ZZZZZ_NN.dgn        ALI(MAIN)SEKI_A2.dgn

XXX is the three-letter file type descriptor (ALI alignments, COR corridor, TER terrain,
DRN drainage, PNP plan and profile sheets, TYP typical sections, PRK parking lot, WAL
retaining wall, ECP erosion control, SST signing and striping, TCP traffic control, XSS
cross sections, XST cross section title, TAB tabulations, ...), (YYYY) the alignment
descriptor where more than one alignment is present (the first four letters of its
name), ZZZZZ the project descriptor, _NN a counter.  The sample sheets stamp their own
file names (PNP(Sample).dgn, TYP(Sample)4R.dgn, WAL(Sample).dgn): the sheet file keeps
that name, and the design files take the convention with the stamp's project descriptor.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wfl_redraft"))

import wflbuild                                                     # noqa: E402

# family -> CFL file type descriptor for a sheet without a usable stamp
DESCRIPTOR = {"plan-profile": "PNP", "approach": "PNP", "parking": "PRK", "layout": "PRK",
              "erosion": "ECP", "wall": "WAL", "drainage": "DRN", "signing": "SST",
              "detour": "TCP", "typical": "TYP", "soq": "TAB", "xs": "XSS", "xst": "XST",
              "details": "SP", "survey": "CTL", "general": "TTL", "other": "PLA"}
STAMP = re.compile(r"^([A-Z]{2,3}|B|SP\d+)[_(]?([A-Za-z0-9]*)\)?([A-Za-z0-9\-]*)\.dgn$", re.I)


class Naming(wflbuild.Naming):
    name = "cfl"
    manual = "the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: type, alignment, project, counter)"
    roles = {"SUR": "Terrain and survey file (CFL descriptor TER)",
             "ALI": "Alignment design file (CFL descriptor ALI)",
             "HYD": "Drainage design file (CFL descriptor DRN)",
             "COR": "Corridor file (CFL descriptor COR)"}

    def _names_for(self, dig):
        """(project descriptor, the sheet file's stem, sheet number, how it was named)"""
        f = dig["fields"]
        stamp = (f.get("dgn_file") or "").replace("\\", "/").split("/")[-1]
        m = STAMP.match(stamp)
        project = "Sample"
        if m:
            stem = stamp[:-4]
            if m.group(2) and m.group(2).lower() not in ("sheets",):
                project = m.group(2)
            how = f"is the file name stamped in the sheet's margin ({stamp}); design files take its project descriptor `{project}`"
        else:
            stem = f"{DESCRIPTOR.get(dig['family'], 'PLA')}({project})"
            how = "is the convention's descriptor for this kind of sheet (no usable stamp in the margin)"
        sid = (f.get("sheet_number") or "").strip()
        return project, stem, sid, how

    def names_for(self, dig):
        project, stem, sid, how = self._names_for(dig)
        self._road = self.road_name(dig)
        return project, stem, sid, how

    def design_file(self, prefix, key, align_names):
        """ALI and COR files carry the alignment descriptor: the first four letters of
        the alignment's lettered name, else of the road a note names, else none."""
        desc = {"SUR": "TER", "ALI": "ALI", "HYD": "DRN", "COR": "COR"}[key]
        algn = ""
        if key in ("ALI", "COR"):
            named = [n for n in align_names if not re.match(r"^CL\d+$", n)]
            src = named[0] if named else getattr(self, "_road", None)
            if src:
                algn = "(" + re.sub(r"[^A-Za-z0-9]", "", src)[:4].upper() + ")"
        return f"{desc}{algn}{prefix}.rdraft"

    def sheet_file(self, prefix, stem):
        return f"{stem}.rdraft"

    def in_manual(self, stem):
        return True

    @staticmethod
    def station_text(station):
        """CFL letters the whole station at a tick ("15+00")."""
        return f"{int(round(station / 100.0))}+00"


CFL = Naming()
