# PyInstaller build of dist/RoadDraft.app: RoadDraft with its own Python, the
# desktop window (roaddraft.desktop) as its entry point. Build it with
# scripts/build_app.sh, which makes the build environment and the icons first.
#
# The .rdraft type is declared so Finder shows RoadDraft's document icon on a
# drawing, but RoadDraft does not claim to open it (role None): drawings open
# from inside the app, and a double-clicked one would otherwise launch the app
# only to tell you it cannot open the file.
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
ICONS = ROOT / "build" / "icons"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
BUNDLE_ID = "com.robertdenison.roaddraft"
DRAWING_TYPE = BUNDLE_ID + ".drawing"

a = Analysis(
    [str(ROOT / "src" / "roaddraft" / "desktop" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=collect_data_files("roaddraft",
                             includes=["web/static/*", "probes/l2/*.json"])
    + [(str(ICONS / "RoadDraft-document.icns"), ".")],
    excludes=["tkinter", "_tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6",
              "qtpy", "gi", "cefpython3", "pytest", "_pytest", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RoadDraft",
    console=False,          # a window, not a terminal
    argv_emulation=False,   # files open from inside the app, not from Finder
)
coll = COLLECT(exe, a.binaries, a.datas, name="RoadDraft")
app = BUNDLE(
    coll,
    name="RoadDraft.app",
    icon=str(ICONS / "RoadDraft.icns"),
    bundle_identifier=BUNDLE_ID,
    version=VERSION,
    info_plist={
        "CFBundleName": "RoadDraft",
        "CFBundleDisplayName": "RoadDraft",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "11.0",
        "LSApplicationCategoryType": "public.app-category.graphics-design",
        "NSHighResolutionCapable": True,
        # the window's page comes from the app's own server on 127.0.0.1
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        "UTExportedTypeDeclarations": [{
            "UTTypeIdentifier": DRAWING_TYPE,
            "UTTypeDescription": "RoadDraft Drawing",
            "UTTypeConformsTo": ["public.data", "public.content"],
            "UTTypeIconFile": "RoadDraft-document.icns",
            "UTTypeTagSpecification": {
                "public.filename-extension": ["rdraft"],
                "public.mime-type": ["application/x-roaddraft"],
            },
        }],
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "RoadDraft Drawing",
            "CFBundleTypeRole": "None",
            "LSHandlerRank": "None",
            "LSItemContentTypes": [DRAWING_TYPE],
            "CFBundleTypeIconFile": "RoadDraft-document.icns",
        }],
    },
)
