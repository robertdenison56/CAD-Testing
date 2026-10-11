"""How FDOT names its files, as a wflbuild.Naming: the FDOT CADD Manual's standard
file names, <type><discipline><sequence> (the FDOT CADD Standard File Name table,
30 Sep 2021):

    ALGNRD01   Alignment Geometry (roadway design)      SURVRD01  Survey Development Model
    DSGNRD01   2D Plan, proposed (roadway design)       DRPRRD01  Drainage Structures - Proposed
    PLPRRD01   Plan-Profile sheets                      KEYSRD01  Key Sheet
    TYPSRD01   Typical Sections                         GNNTRD01  General Notes
    DRMPRD01   Drainage Map                             RDXSRD01  Cross Sections
    UTADRD01   Utility Adjustments                      SSUVRD01  Soil Survey
    RPTBRD01   Report of Borings                        SCGPRD01  Selective Clearing and Grubbing Plan
    SCGDRD01   Selective Clearing and Grubbing Details  CTLSRD01  Project Control
    BHRSRD01   Bridge Hydraulic Recommendations         DROMRD01  Optional Materials Tabulation
    SIGNRD01   Signature Sheet                          PLANLD01  Landscape Plan

The exhibit sheets stamp their own file names (PLPRRD02.dgn, DRPRRD01.dgn, RDXSRD03.dgn,
KEYSRD06.dgn); the sheet file keeps a stamped standard name, and takes the table's name
for its kind of sheet where the stamp is the FDM's exhibit master file.  FDOT cuts the
drainage sheets from the drainage design file, so a sheet stamped DRPRRD01 owns the
drainage structures in its own model.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wfl_redraft"))

import wflbuild                                                     # noqa: E402

SHEET_NAME = {"plan-profile": "PLPRRD01", "drainage": "DRPRRD01", "drainage-profile": "DRPRRD01",
              "drainage-xs": "DRPRRD01", "tabulation": "DROMRD01", "drainage-map": "DRMPRD01",
              "typical": "TYPSRD01", "notes": "GNNTRD01", "key": "KEYSRD01", "concept": "KEYSRD01",
              "signature": "SIGNRD01", "control": "CTLSRD01", "xs": "RDXSRD01", "soil": "SSUVRD01",
              "borings": "RPTBRD01", "utility": "UTADRD01", "clearing": "SCGPRD01",
              "details": "SCGDRD01", "hydraulics": "BHRSRD01", "landscape": "PLANLD01",
              "model-management": "MDMGRD01", "other": "PLANRD01"}
NOT_IN_TABLE = {"MDMGRD01"}
STANDARD = re.compile(r"^(?:AMG-\d)?([A-Z]{4}[A-Z]{2}\d{2})\.dgn$", re.I)


class Naming(wflbuild.Naming):
    name = "fdot"
    manual = "the FDOT CADD Manual's standard file names (<type><discipline><sequence>)"
    roles = {"SUR": "Survey development model (FDOT standard file SURVRD)",
             "ALI": "Alignment geometry (FDOT standard file ALGNRD)",
             "HYD": "Drainage structures, proposed (FDOT standard file DRPRRD)",
             "COR": "2D plan, proposed (FDOT standard file DSGNRD)"}

    def names_for(self, dig):
        """(project id, the sheet file's stem, sheet number, how it was named)"""
        f = dig["fields"]
        stamp = (f.get("dgn_file") or "").replace("\\", "/").split("/")[-1].split(" ")[0]
        m = STANDARD.match(stamp)
        fam = dig["family"]
        if m and not stamp.upper().startswith("AMG"):
            stem = m.group(1).upper()
            how = f"is the standard file name stamped in the sheet's margin ({stamp})"
        else:
            stem = SHEET_NAME.get(fam, "PLANRD01")
            how = (f"is the table's name for this kind of sheet (the margin stamps the FDM's exhibit "
                   f"master file, {stamp})" if stamp else "is the table's name for this kind of sheet")
        self._sheet_stem = stem
        project = (f.get("fpid") or "").strip()
        sid = (f.get("sheet_number") or "").strip()
        return project, stem, sid, how

    def design_file(self, prefix, key, align_names):
        return {"SUR": "SURVRD01.rdraft", "ALI": "ALGNRD01.rdraft", "HYD": "DRPRRD01.rdraft",
                "COR": "DSGNRD01.rdraft"}[key]

    def sheet_file(self, prefix, stem):
        return f"{stem}.rdraft"

    def in_manual(self, stem):
        return stem not in NOT_IN_TABLE

    def inline(self, key, dig):
        """A sheet stamped from the drainage design file keeps the drainage structures
        in its own model, as FDOT does."""
        return key == "HYD" and getattr(self, "_sheet_stem", "").startswith("DRPR")

    @staticmethod
    def station_text(station):
        return str(int(round(station / 100.0)))


FDOT = Naming()
