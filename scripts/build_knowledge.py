#!/usr/bin/env python3
"""Build and update the eval knowledge base under ``benchmarks/knowledge/``.

For every source listed in ``benchmarks/knowledge/manifest.json`` this script

* verifies the raw PDF (sha256, size, page count) and refreshes the computed
  fields of its manifest entry,
* extracts the text with poppler's ``pdftotext`` (reading order, not layout)
  into ``<collection>/<id>.txt`` with one separator line per PDF page,
* writes ``<collection>/<id>.pages.json`` (one record per PDF page: the
  manual's own page number, running header, revision date, sections; or, for
  example-sheet volumes, the sheet title and release dates),
* writes ``<collection>/<id>.outline.json`` (the PDF bookmark tree), and
* prints a change report against the previous artifacts (sections whose
  revision date changed, sheets added or removed).

The raw PDFs are not committed (``**/raw/`` is gitignored); the manifest pins
their sha256 so a fresh checkout can fetch them from ``download_url`` and
rebuild.  Publishers revise these manuals continually, so the update path is
built in: ``--fetch`` compares the remote copy with the pinned one and rebuilds
only what changed.  See ``benchmarks/knowledge/UPDATING.md``.

Usage::

    python3 scripts/build_knowledge.py                    # rebuild every source from raw/
    python3 scripts/build_knowledge.py --only ppm-text
    python3 scripts/build_knowledge.py --check            # verify hashes only, exit 1 on mismatch
    python3 scripts/build_knowledge.py --fetch --dry-run  # ask the publisher whether anything changed
    python3 scripts/build_knowledge.py --fetch            # download changed sources, rebuild them

Requires ``pdftotext`` (poppler) on PATH and the ``pypdf`` package.  Neither is
a runtime dependency of ``roaddraft``; this is a build tool for reference data.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "benchmarks" / "knowledge"
MANIFEST = ROOT / "manifest.json"

#: Manifest keys that are maintained by hand and never overwritten here.
HAND_KEYS = ("id", "collection", "kind", "title", "publisher", "edition", "url", "download_url",
             "license", "file", "notes", "relevance")
#: Computed keys that survive a rebuild (set by --fetch, not by the extraction).
CARRY_KEYS = ("remote", "fetched_at")

USER_AGENT = "roaddraft-knowledge-builder/1.0 (+https://github.com/robertdenison56/CAD-Testing)"

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
REVISED_RE = re.compile(r"^(?:Revised\s+)?(?:%s)\s+\d{4}$" % MONTHS)
HEADER_RE = re.compile(r"^(?:Chapter|Section|Appendix|Table of Contents)\b.*$")
# The manual's own page number: "2-8", "4-41", "i", "iv" -- on its own line or after the copyright line.
PPM_PAGE_RE = re.compile(r"(?:^|\s)((?:[ivxlc]{1,6})|(?:\d{1,2}-\d{1,3}[A-Za-z]?)|(?:[A-Z]{1,2}-\d{1,3}))\s*$")
SECTION_RE = re.compile(r"^(\d+)\s*-\s*(\d+(?:\.\d+)*)\b")          # outline titles like "2 -1.3 ..."
RELEASED_RE = re.compile(r"\bRELEASED\s+(\d{1,2}/\d{1,2}/\d{2,4})")
SUPERSEDES_RE = re.compile(r"SUPERSEDES\s+EXAMPLE\s+RELEASED\s+(\d{1,2}/\d{1,2}/\d{2,4})")
MIN_TEXT_CHARS = 20   # pages with fewer extractable characters are recorded as scanned/blank


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- helpers ---------------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def pdftotext_version() -> str:
    out = subprocess.run(["pdftotext", "-v"], capture_output=True, text=True)
    first = (out.stderr or out.stdout).strip().splitlines()
    return first[0] if first else "unknown"


def extract_pages(pdf: Path) -> List[str]:
    """Reading-order text of every page (poppler warnings about the PDF's marked content are dropped)."""
    out = subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf), "-"],
                         capture_output=True, text=True, check=True)
    pages = out.stdout.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return [clean_page(p) for p in pages]


def clean_page(text: str) -> str:
    """Strip trailing whitespace and collapse runs of blank lines."""
    lines: List[str] = []
    blank = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            if blank:
                continue
            blank = True
        else:
            blank = False
        lines.append(line)
    return "\n".join(lines).strip("\n")


def read_outline(pdf: Path):
    """Return (outline entries, page count, metadata) via pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("pypdf is required: pip install pypdf")
    logging.getLogger("pypdf").setLevel(logging.ERROR)   # broken external destinations are expected
    reader = PdfReader(str(pdf))
    entries: List[dict] = []

    def walk(items, depth: int) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
                continue
            try:
                page = reader.get_destination_page_number(item) + 1
            except Exception:
                page = None
            entries.append({"depth": depth, "title": " ".join(str(item.title).split()), "pdf_page": page})

    walk(reader.outline, 0)
    meta = {}
    for key in ("/Title", "/Subject", "/Author", "/Keywords", "/Creator", "/CreationDate", "/ModDate"):
        value = (reader.metadata or {}).get(key)
        if value:
            meta[key.lstrip("/").lower()] = str(value)
    return entries, len(reader.pages), meta


def normalize_section(title: str) -> Optional[str]:
    m = SECTION_RE.match(title)
    return "%s-%s" % (m.group(1), m.group(2)) if m else None


# --- page indexes ----------------------------------------------------------------------------

def _find_revised(lines: List[str]) -> Optional[str]:
    """The running header's revision date: normally within the first lines, but reading-order
    extraction can push it anywhere in the page stream, so fall back to the whole page."""
    for pool in (lines[:8], lines):
        for line in pool:
            if REVISED_RE.match(line):
                return line
    return None


def _find_ppm_page(lines: List[str], header: Optional[str]) -> Optional[str]:
    """The manual's own page number: normally the last line (or after the copyright line); on
    figure pages it can sit earlier in the stream, so fall back to a standalone token whose
    chapter prefix matches the running header."""
    for line in reversed(lines[-4:]):
        m = PPM_PAGE_RE.search(line)
        if m:
            return m.group(1)
    chapter = re.match(r"^(?:Chapter|Section)\s+(\d+)", header or "")
    if chapter:
        exact = re.compile(r"^%s-\d{1,3}[A-Za-z]?$" % chapter.group(1))
    elif header and header.startswith("Table of Contents"):
        exact = re.compile(r"^[ivxlc]{1,6}$")
    else:
        return None
    for line in reversed(lines):
        if exact.match(line):
            return line
    return None


def index_manual(pages: List[str], outline: List[dict]) -> List[dict]:
    """One record per PDF page of a prose manual with its own page numbering.

    ``sections`` lists the numbered section in effect at the top of the page followed by every
    numbered section that starts on it, in reading order (a page can hold the end of 2-1.3 and
    the start of 2-1.4).
    """
    starts: Dict[int, List[str]] = {}
    section_starts: Dict[int, List[str]] = {}
    for entry in outline:
        page = entry["pdf_page"]
        if page is None:
            continue
        starts.setdefault(page, []).append(entry["title"])
        sec = normalize_section(entry["title"])
        if sec:
            section_starts.setdefault(page, []).append(sec)
    records = []
    current_section: Optional[str] = None
    for n, text in enumerate(pages, start=1):
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        header = next((l for l in lines[:5] if HEADER_RE.match(l)), None)
        revised = _find_revised(lines)
        ppm_page = _find_ppm_page(lines, header)
        sections: List[str] = [current_section] if current_section else []
        for sec in section_starts.get(n, []):
            if sec not in sections:
                sections.append(sec)
            current_section = sec
        records.append({
            "pdf_page": n, "ppm_page": ppm_page, "header": header, "revised": revised,
            "sections": sections, "outline": starts.get(n, []), "chars": len(text),
            "text_extractable": len(text) >= MIN_TEXT_CHARS,
        })
    return records


def index_drawings(pages: List[str], outline: List[dict]) -> List[dict]:
    """One record per PDF page of an example-sheet volume (one plan sheet per page)."""
    starts: Dict[int, List[dict]] = {}
    for entry in outline:
        if entry["pdf_page"] is not None:
            starts.setdefault(entry["pdf_page"], []).append(entry)
    records = []
    current_group: Optional[str] = None
    for n, text in enumerate(pages, start=1):
        entries = starts.get(n, [])
        for entry in entries:
            if entry["depth"] == 1:             # "Section 2-2.5 Layouts, Profiles and ..."
                current_group = entry["title"]
        leaf = max(entries, key=lambda e: e["depth"])["title"] if entries else None
        supersedes = SUPERSEDES_RE.search(text)
        # "RELEASED m/d/yy" inside the SUPERSEDES phrase is the old example's date, not this sheet's.
        released = RELEASED_RE.search(SUPERSEDES_RE.sub(" ", text))
        records.append({
            "pdf_page": n, "title": leaf, "group": current_group,
            "outline": [e["title"] for e in entries],
            "released": released.group(1) if released else None,
            "supersedes": supersedes.group(1) if supersedes else None,
            "chars": len(text), "text_extractable": len(text) >= MIN_TEXT_CHARS,
        })
    return records


def separator(source_id: str, record: dict) -> str:
    fields = ["pdf_page %d" % record["pdf_page"]]
    if "ppm_page" in record:                     # manual
        if record["ppm_page"]:
            fields.append("ppm_page %s" % record["ppm_page"])
        if record["header"]:
            fields.append(record["header"])
        if record["revised"]:
            fields.append(record["revised"])
        if record["sections"]:
            fields.append("section %s" % ", ".join(record["sections"]))
    else:                                        # drawings
        if record["title"]:
            fields.append(record["title"])
        if record["released"]:
            fields.append("released %s" % record["released"])
        if record["supersedes"]:
            fields.append("supersedes %s" % record["supersedes"])
    return "===== %s | %s =====" % (source_id, " | ".join(fields))


# --- change report ---------------------------------------------------------------------------

def _section_dates(records: List[dict]) -> Dict[str, set]:
    dates: Dict[str, set] = {}
    for r in records:
        for sec in r.get("sections", []):
            dates.setdefault(sec, set())
            if r.get("revised"):
                dates[sec].add(r["revised"])
    return dates


def change_report(kind: str, old: Optional[List[dict]], new: List[dict]) -> List[str]:
    """Human-readable differences between the previous page index and the new one."""
    if old is None:
        return ["first build, no previous index to compare"]
    lines: List[str] = []
    if len(old) != len(new):
        lines.append("page count %d -> %d" % (len(old), len(new)))
    if kind == "manual":
        before, after = _section_dates(old), _section_dates(new)
        for sec in sorted(set(before) | set(after), key=lambda s: [int(x) for x in re.findall(r"\d+", s)]):
            if sec not in before:
                lines.append("section %s added (%s)" % (sec, ", ".join(sorted(after[sec])) or "no date"))
            elif sec not in after:
                lines.append("section %s removed" % sec)
            elif before[sec] != after[sec]:
                lines.append("section %s revised: %s -> %s" % (
                    sec, ", ".join(sorted(before[sec])) or "none", ", ".join(sorted(after[sec])) or "none"))
        old_pages = {r["pdf_page"]: r for r in old}
        moved = sum(1 for r in new if r["pdf_page"] in old_pages
                    and old_pages[r["pdf_page"]].get("ppm_page") != r.get("ppm_page"))
        if moved:
            lines.append("%d pages now carry a different manual page number (renumbering)" % moved)
    else:
        before = {r["title"]: r for r in old if r.get("title")}
        after = {r["title"]: r for r in new if r.get("title")}
        for title in sorted(set(after) - set(before)):
            lines.append("sheet added: %s (pdf %d)" % (title, after[title]["pdf_page"]))
        for title in sorted(set(before) - set(after)):
            lines.append("sheet removed: %s" % title)
        for title in sorted(set(before) & set(after)):
            b, a = before[title], after[title]
            if (b.get("released"), b.get("supersedes")) != (a.get("released"), a.get("supersedes")):
                lines.append("sheet re-released: %s (%s -> %s)" % (title, b.get("released"), a.get("released")))
    return lines or ["no section, sheet or date changes detected (text may still differ: git diff the .txt)"]


# --- fetch -----------------------------------------------------------------------------------

def _request(url: str, method: str = "GET") -> urllib.request.Request:
    return urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})


def probe(url: str) -> dict:
    """Remote metadata without downloading the body: ETag, Last-Modified, Content-Length."""
    for method in ("HEAD", "GET"):
        try:
            with urllib.request.urlopen(_request(url, method), timeout=60) as resp:
                h = resp.headers
                return {"etag": h.get("ETag"), "last_modified": h.get("Last-Modified"),
                        "content_length": int(h["Content-Length"]) if h.get("Content-Length") else None,
                        "final_url": resp.geturl()}
        except urllib.error.HTTPError as ex:
            if method == "HEAD" and ex.code in (403, 405, 501):
                continue
            raise
    return {}


def download(url: str, dest: Path) -> Tuple[Path, str]:
    """Stream ``url`` to ``dest.download`` and return (temp path, sha256)."""
    tmp = dest.with_name(dest.name + ".download")
    h = hashlib.sha256()
    with urllib.request.urlopen(_request(url), timeout=600) as resp, open(tmp, "wb") as out:
        for chunk in iter(lambda: resp.read(1 << 20), b""):
            h.update(chunk)
            out.write(chunk)
    return tmp, "sha256:" + h.hexdigest()


def _headers_match(remote: dict, pinned: dict) -> bool:
    keys = [k for k in ("etag", "last_modified", "content_length") if pinned.get(k)]
    return bool(keys) and all(remote.get(k) == pinned.get(k) for k in keys)


def fetch_source(entry: dict, dry_run: bool) -> bool:
    """Download the source when the publisher's copy differs from the pinned one.

    Returns True when ``raw/<file>`` was replaced (the previous copy is kept beside it as
    ``<file>.prev`` for a side-by-side look).  With ``dry_run`` nothing is written; the remote
    headers are compared with those recorded at the last fetch.
    """
    url = entry.get("download_url")
    if not url:
        print("%-14s no download_url in the manifest; fetch it by hand from %s" % (entry["id"], entry.get("url")))
        return False
    pdf = ROOT / entry["file"]
    pinned = entry.get("remote", {})
    remote = probe(url)
    local_ok = pdf.exists() and sha256_of(pdf) == entry.get("sha256")
    if dry_run:
        if not pinned:
            print("%-14s remote %s bytes, last-modified %s; no headers pinned yet, run --fetch once"
                  % (entry["id"], remote.get("content_length"), remote.get("last_modified")))
        elif _headers_match(remote, pinned):
            print("%-14s unchanged at the publisher (headers match the pinned copy%s)"
                  % (entry["id"], "" if local_ok else "; local raw copy missing or stale"))
        else:
            print("%-14s CHANGED at the publisher: last-modified %s -> %s, size %s -> %s"
                  % (entry["id"], pinned.get("last_modified"), remote.get("last_modified"),
                     pinned.get("content_length"), remote.get("content_length")))
        return False
    if local_ok and _headers_match(remote, pinned):
        print("%-14s unchanged (remote headers match the pinned copy)" % entry["id"])
        return False
    print("%-14s downloading %s" % (entry["id"], url))
    tmp, digest = download(url, pdf)
    entry["remote"] = remote
    entry["fetched_at"] = _now()
    if digest == entry.get("sha256"):
        if local_ok:
            tmp.unlink()
        else:
            tmp.replace(pdf)
        print("%-14s unchanged (same sha256 as pinned)" % entry["id"])
        return False
    if pdf.exists():
        pdf.replace(pdf.with_name(pdf.name + ".prev"))
    tmp.replace(pdf)
    print("%-14s CHANGED: %s -> %s (previous copy kept as %s.prev)" % (entry["id"], entry.get("sha256"), digest, pdf.name))
    return True


# --- build -----------------------------------------------------------------------------------

def build_source(entry: dict) -> Tuple[dict, List[str]]:
    pdf = ROOT / entry["file"]
    if not pdf.exists():
        sys.exit("missing raw source %s (fetch with --fetch, or from %s)" % (pdf, entry.get("download_url") or entry.get("url")))
    outline, n_pages, meta = read_outline(pdf)
    pages = extract_pages(pdf)
    if len(pages) != n_pages:
        sys.exit("%s: pdftotext returned %d pages, pypdf says %d" % (entry["id"], len(pages), n_pages))
    kind = entry.get("kind", "manual")
    records = index_manual(pages, outline) if kind == "manual" else index_drawings(pages, outline)

    out_dir = ROOT / entry["collection"]
    text_path = out_dir / ("%s.txt" % entry["id"])
    pages_path = out_dir / ("%s.pages.json" % entry["id"])
    outline_path = out_dir / ("%s.outline.json" % entry["id"])

    previous = None
    if pages_path.exists():
        with open(pages_path, encoding="utf-8") as fh:
            previous = json.load(fh).get("pages")
    report = change_report(kind, previous, records)

    with open(text_path, "w", encoding="utf-8") as fh:
        fh.write("# %s\n# %s\n# Source: %s (%s)\n# Rebuilt by scripts/build_knowledge.py; do not edit by hand.\n"
                 % (entry["title"], entry.get("edition", ""), entry["file"], entry.get("url", "")))
        for record, text in zip(records, pages):
            fh.write("\n%s\n" % separator(entry["id"], record))
            if text:
                fh.write(text + "\n")
    with open(pages_path, "w", encoding="utf-8") as fh:
        json.dump({"source": entry["id"], "kind": kind, "pages": records}, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    with open(outline_path, "w", encoding="utf-8") as fh:
        json.dump({"source": entry["id"], "entries": outline}, fh, indent=1, ensure_ascii=False)
        fh.write("\n")

    computed = {
        "sha256": sha256_of(pdf), "bytes": pdf.stat().st_size, "pages": n_pages, "pdf_metadata": meta,
        "artifacts": {"text": str(text_path.relative_to(ROOT)), "pages": str(pages_path.relative_to(ROOT)),
                      "outline": str(outline_path.relative_to(ROOT))},
        "artifact_sha256": {"text": sha256_of(text_path), "pages": sha256_of(pages_path),
                            "outline": sha256_of(outline_path)},
        "pages_without_text": [r["pdf_page"] for r in records if not r["text_extractable"]],
        "outline_entries": len(outline),
        "built_at": _now(),
    }
    fresh = {k: entry[k] for k in HAND_KEYS if k in entry}
    fresh.update({k: entry[k] for k in CARRY_KEYS if k in entry})
    fresh.update(computed)
    return fresh, report


def check(manifest: dict) -> int:
    failures = 0
    for entry in manifest["sources"]:
        pdf = ROOT / entry["file"]
        if pdf.exists():
            ok = sha256_of(pdf) == entry.get("sha256")
            print("%-14s raw     %s %s" % (entry["id"], "ok " if ok else "MISMATCH", entry["file"]))
            failures += 0 if ok else 1
        else:
            print("%-14s raw     absent   %s (fetch with --fetch)" % (entry["id"], entry["file"]))
        for name, rel in entry.get("artifacts", {}).items():
            path = ROOT / rel
            ok = path.exists() and sha256_of(path) == entry.get("artifact_sha256", {}).get(name)
            print("%-14s %-7s %s %s" % (entry["id"], name, "ok " if ok else "MISMATCH", rel))
            failures += 0 if ok else 1
    return failures


def save_manifest(manifest: dict) -> None:
    manifest["builder"] = "scripts/build_knowledge.py"
    manifest["tools"] = {"pdftotext": pdftotext_version(), "python": sys.version.split()[0]}
    try:
        manifest["tools"]["pypdf"] = __import__("pypdf").__version__
    except ImportError:
        pass
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="verify hashes only; exit 1 on any mismatch")
    ap.add_argument("--only", metavar="ID", help="restrict to a single source id")
    ap.add_argument("--fetch", action="store_true",
                    help="download each source from its download_url when the publisher's copy changed, then rebuild it")
    ap.add_argument("--dry-run", action="store_true", help="with --fetch: report whether the publisher's copy changed, write nothing")
    args = ap.parse_args(argv)

    with open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    if args.check:
        return 1 if check(manifest) else 0
    if shutil.which("pdftotext") is None:
        sys.exit("pdftotext (poppler) is required on PATH")

    selected = [e for e in manifest["sources"] if not args.only or e["id"] == args.only]
    if args.only and not selected:
        sys.exit("no source with id %r in the manifest" % args.only)

    if args.fetch:
        changed = [e["id"] for e in selected if fetch_source(e, args.dry_run)]
        if args.dry_run:
            return 0
        if not changed:
            print("nothing changed at the publisher; artifacts left as they are")
            save_manifest(manifest)      # remote headers / fetched_at refreshed
            return 0
        selected = [e for e in selected if e["id"] in changed]

    reports: Dict[str, List[str]] = {}
    rebuilt = {}
    for entry in selected:
        print("building %s from %s" % (entry["id"], entry["file"]))
        rebuilt[entry["id"]], reports[entry["id"]] = build_source(entry)
    manifest["sources"] = [rebuilt.get(e["id"], e) for e in manifest["sources"]]
    save_manifest(manifest)

    for entry in manifest["sources"]:
        if entry["id"] in rebuilt:
            print("  %-14s %4d pages, %3d without text, outline %d entries"
                  % (entry["id"], entry["pages"], len(entry["pages_without_text"]), entry["outline_entries"]))
    print("\nchange report (previous index -> this build):")
    for source_id, lines in reports.items():
        for line in lines:
            print("  %-14s %s" % (source_id, line))
    print("\nnext: git diff --stat benchmarks/knowledge; .venv/bin/python -m pytest -q tests/test_knowledge.py; "
          "then follow benchmarks/knowledge/UPDATING.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
