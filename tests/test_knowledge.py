"""The eval knowledge base (benchmarks/knowledge) is internally consistent.

Checks the committed artifacts against the manifest and against each other: hashes, page
counts, separator lines, outline targets, and that every section the manifest marks as
D1-relevant actually exists in the source's outline.  The raw PDFs are gitignored, so
their hashes are verified only when a local copy is present.
"""
import hashlib
import json
import os
import re

import pytest

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "benchmarks", "knowledge")
MANIFEST = os.path.join(ROOT, "manifest.json")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def manifest():
    with open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def sources(manifest):
    return {s["id"]: s for s in manifest["sources"]}


def test_manifest_lists_both_ppm_volumes(sources):
    assert set(sources) >= {"ppm-text", "ppm-examples"}
    for entry in sources.values():
        for key in ("id", "collection", "kind", "title", "publisher", "edition", "url", "license", "file",
                    "sha256", "bytes", "pages", "artifacts", "artifact_sha256"):
            assert key in entry, (entry["id"], key)
        assert entry["kind"] in ("manual", "drawings")
        assert re.match(r"^sha256:[0-9a-f]{64}$", entry["sha256"])


def test_committed_artifacts_match_manifest_hashes(sources):
    for entry in sources.values():
        for name, rel in entry["artifacts"].items():
            path = os.path.join(ROOT, rel)
            assert os.path.exists(path), rel
            assert _sha256(path) == entry["artifact_sha256"][name], rel


def test_raw_pdf_hash_when_present(sources):
    present = [s for s in sources.values() if os.path.exists(os.path.join(ROOT, s["file"]))]
    if not present:
        pytest.skip("raw PDFs not present (gitignored); nothing to verify")
    for entry in present:
        path = os.path.join(ROOT, entry["file"])
        assert os.path.getsize(path) == entry["bytes"], entry["file"]
        assert _sha256(path) == entry["sha256"], entry["file"]


def test_page_index_covers_every_pdf_page(sources):
    for entry in sources.values():
        pages = _load(entry["artifacts"]["pages"])
        assert pages["source"] == entry["id"] and pages["kind"] == entry["kind"]
        records = pages["pages"]
        assert [r["pdf_page"] for r in records] == list(range(1, entry["pages"] + 1)), entry["id"]
        without = [r["pdf_page"] for r in records if not r["text_extractable"]]
        assert without == entry["pages_without_text"], entry["id"]


def test_text_artifact_has_one_separator_per_page(sources):
    for entry in sources.values():
        with open(os.path.join(ROOT, entry["artifacts"]["text"]), encoding="utf-8") as fh:
            seps = [l for l in fh if l.startswith("===== %s | pdf_page " % entry["id"])]
        numbers = [int(re.match(r"===== \S+ \| pdf_page (\d+) ", l).group(1)) for l in seps]
        assert numbers == list(range(1, entry["pages"] + 1)), entry["id"]


def test_outline_targets_are_within_the_document(sources):
    for entry in sources.values():
        outline = _load(entry["artifacts"]["outline"])
        assert outline["source"] == entry["id"]
        assert len(outline["entries"]) == entry["outline_entries"]
        for item in outline["entries"]:
            assert item["title"]
            assert item["pdf_page"] is None or 1 <= item["pdf_page"] <= entry["pages"], item


def test_manual_pages_carry_ppm_page_numbers_and_sections(sources):
    entry = sources["ppm-text"]
    records = _load(entry["artifacts"]["pages"])["pages"]
    numbered = [r for r in records if r["ppm_page"]]
    assert len(numbered) >= 0.9 * len(records)          # a few figure pages print no number
    body = [r for r in records if r["pdf_page"] >= 8]   # after the table of contents
    assert all(r["sections"] for r in body)
    by_pdf = {r["pdf_page"]: r for r in records}
    assert by_pdf[17]["ppm_page"] == "2-4" and "2-1.2" in by_pdf[17]["sections"]
    assert by_pdf[21]["ppm_page"] == "2-8" and by_pdf[21]["sections"][0] == "2-1.3"
    assert by_pdf[110]["ppm_page"] == "2-81" and "2-2.5" in by_pdf[110]["sections"]


def test_d1_relevant_sections_exist_in_the_manual_outline(sources):
    entry = sources["ppm-text"]
    outline = _load(entry["artifacts"]["outline"])["entries"]
    numbered = set()
    for item in outline:
        m = re.match(r"^(\d+)\s*-\s*(\d+(?:\.\d+)*)\b", item["title"])
        if m:
            numbered.add("%s-%s" % (m.group(1), m.group(2)))
    for section in entry["relevance"]["d1_sections"]:
        assert section in numbered, section


def test_d1_relevant_example_pages_are_layout_or_title_sheets(sources):
    entry = sources["ppm-examples"]
    records = {r["pdf_page"]: r for r in _load(entry["artifacts"]["pages"])["pages"]}
    for group, pages in entry["relevance"]["d1_pages"].items():
        for page in pages:
            record = records[page]
            assert record["title"], (group, page)
            assert record["text_extractable"], (group, page)
            assert re.search(r"Title|Layout|Profile|Superelevation|Project Control", record["title"]), (group, record["title"])


def test_every_source_has_a_publisher_download_url(sources):
    """The update path (scripts/build_knowledge.py --fetch) needs a direct URL per source, and
    the raw file name is the URL's basename so a hand download lands under the same name."""
    for entry in sources.values():
        url = entry.get("download_url", "")
        assert url.startswith("https://"), entry["id"]
        assert url.rsplit("/", 1)[-1] == os.path.basename(entry["file"]), entry["id"]


def test_manifest_points_at_the_update_procedure(manifest):
    assert manifest["update_procedure"] == "benchmarks/knowledge/UPDATING.md"
    assert os.path.exists(os.path.join(os.path.dirname(ROOT), "knowledge", "UPDATING.md"))
    assert manifest["update_notifications_url"].startswith("https://")
