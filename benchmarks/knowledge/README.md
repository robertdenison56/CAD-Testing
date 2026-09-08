# Eval knowledge base

Reference standards behind the RoadDraft drafting spec (`src/roaddraft/tasks/spec_v1.py`),
the task generator's design tables (`tasks/standards.py`) and the verifier. The PRD calls the
spec "Caltrans-flavored but genericized"; this directory holds the Caltrans source so every
value in the spec can be traced to a page, and every departure from the source is a recorded
PE decision rather than an accident.

**What it is for.** Spec authoring and PE review (eval plan §3.7), the verifier's documentation,
the benchmark writeup, and future dialect skins (eval plan §4.5). It is **not** part of the agent's
observation: agents see only the task brief and `spec_subset()`; nothing here is ever sent to a
model during an eval run.

## Layout

```
benchmarks/knowledge/
  manifest.json                 every source: publisher, edition, URL, sha256, page count, artifact hashes
  README.md                     this file
  UPDATING.md                   how to pick up a new edition from the publisher (fetch, rebuild, review, commit)
  caltrans-ppm/                 collection: Caltrans Plans Preparation Manual (PPM)
    README.md                   section map, D1 relevance, where draft-v1 departs from the PPM
    raw/                        the source PDFs (gitignored; sha256 pinned in the manifest)
    ppm-text.txt                manual text, reading order, one separator line per PDF page
    ppm-text.pages.json         per page: PPM page number, running header, revision date, section
    ppm-text.outline.json       the PDF bookmark tree with page targets (490 entries)
    ppm-examples.txt            text of every example sheet, one separator line per page
    ppm-examples.pages.json     per page: sheet title, section group, RELEASED / SUPERSEDES dates
    ppm-examples.outline.json   the PDF bookmark tree (303 entries)
scripts/build_knowledge.py      rebuilds everything above from raw/ and refreshes manifest.json
tests/test_knowledge.py         committed artifacts agree with the manifest and with each other
```

## Conventions

- **Citation.** Manual text: `ppm-text p. 2-8 (pdf 21)`. Example sheet: `ppm-examples pdf 45 "65 LAYOUT-1"`.
  Both are the fields of the separator lines, so a citation can be grepped straight into the `.txt`:

  ```bash
  grep -n '^===== ppm-text | pdf_page 21 ' benchmarks/knowledge/caltrans-ppm/ppm-text.txt
  ```

- **Separator lines** start with `===== <source id> | pdf_page <n> |` and carry the page's own
  number, header, revision date and section (manual) or the sheet title and release dates (examples).
  Everything between two separators is that page's text. Pages listed under `pages_without_text`
  in the manifest are scanned images; read them from the PDF.
- **Drawings need the PDF.** The examples text is the annotation and notes of each sheet, useful
  for search; the sheet itself is only in `raw/`. Read a page range from the PDF to see it.
- **Raw PDFs are not committed** (`**/raw/` is gitignored). The manifest pins their sha256, size
  and page count; `python3 scripts/build_knowledge.py --check` verifies a local copy. The PPM is
  Caltrans copyrighted material held here for reference; keep the collection out of anything
  published with the benchmark and cite it instead.

## Keeping it current

Publishers revise these manuals continually. `python3 scripts/build_knowledge.py --fetch --dry-run`
asks the publisher whether a source changed (HTTP headers only); `--fetch` downloads what changed,
rebuilds it and prints a change report. The full procedure, including how to carry a change into the
spec review, is in [UPDATING.md](UPDATING.md).

## Rebuilding or adding a source

1. Put the PDF under `<collection>/raw/` and add a hand-written entry to `manifest.json`
   (`id`, `collection`, `kind` = `manual` or `drawings`, `title`, `publisher`, `edition`, `url`,
   `download_url`, `license`, `file`, `notes`, `relevance`). The computed fields are filled in by
   the builder.
2. Run the builder (needs poppler's `pdftotext` on PATH and `pip install pypdf`; neither is a
   `roaddraft` dependency):

   ```bash
   python3 scripts/build_knowledge.py
   ```

3. Run the consistency test:

   ```bash
   .venv/bin/python -m pytest -q tests/test_knowledge.py
   ```

`kind: manual` sources get the page-number / header / section index; `kind: drawings` sources get
the sheet-title / release-date index. Both rely on the PDF's bookmark outline for section and title
names, so a source without an outline will index pages but not name them.
