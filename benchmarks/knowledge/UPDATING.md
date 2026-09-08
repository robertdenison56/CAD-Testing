# Updating the knowledge base

Caltrans revises the Plans Preparation Manual section by section and re-issues the compiled
PDFs whenever a section changes; the PPM page shows an "Updated" date beside each download.
The knowledge base is built to absorb that: the manifest pins the publisher's copy, the builder
asks the publisher whether it changed, and a rebuild reports what moved. Nothing here changes
the drafting spec by itself.

## 1. Get told

- Subscribe to the Caltrans PPM change notifications:
  https://public.govdelivery.com/accounts/CALTRANS/subscriber/new?topic_id=CALTRANS_8
- The download pages, each with an "Updated" date per file:
  text https://dot.ca.gov/programs/design/manual-plans-preparation-manual-ppm,
  examples https://dot.ca.gov/programs/design/manual-plans-preparation-manual-ppm/ppm-examples
- Or just ask, no download involved:

  ```bash
  python3 scripts/build_knowledge.py --fetch --dry-run
  ```

  This compares the publisher's HTTP headers (ETag, Last-Modified, size) with those pinned in
  `manifest.json` at the last fetch and prints `unchanged` or `CHANGED` per source.

## 2. Update

```bash
python3 scripts/build_knowledge.py --fetch
```

For each source whose publisher copy differs from the pinned sha256, this downloads the new PDF
into `raw/` (the previous copy stays beside it as `<file>.prev`), rebuilds that source's text,
page index and outline, refreshes the manifest, and prints a **change report**: sections whose
revision date changed, sections added or removed, page renumbering, example sheets added,
removed or re-released. Sources that did not change are left alone, so the diff is only the
real change.

Then:

1. Read the change report and `git diff --stat benchmarks/knowledge`. The separator lines in
   `ppm-text.txt` carry the revision date, so the pages of a new revision are one grep away:

   ```bash
   grep -n '| June 2027 |' benchmarks/knowledge/caltrans-ppm/ppm-text.txt
   ```

   `git diff benchmarks/knowledge/caltrans-ppm/ppm-text.txt` shows the new wording. For example
   sheets, read the new page from the PDF in `raw/` and compare with `raw/<file>.prev`.
2. If a changed section is one the spec cites (2-1.2, 2-1.3, 2-1.5, 2-1.8, 2-2.2, 2-2.5; example
   pages 2 to 4 and 44 to 71), re-read it against the tables in `caltrans-ppm/README.md` and update
   the affected rows and the "departs from the PPM" list. A PPM change never edits
   `DRAFTING_SPEC_V1` on its own: any spec edit changes `spec_hash` and every task id, so it goes
   through the PE decision list in `RoadDraft_Eval_Plan.md` §3.7 like every other spec change.
3. Update the `edition` string of the changed source in `manifest.json` (the PDF's title and
   ModDate from `pdf_metadata`, and the page's "Updated" date).
4. Run the consistency tests:

   ```bash
   .venv/bin/python -m pytest -q tests/test_knowledge.py
   ```

5. Commit the artifacts, the manifest and any README edits, with the change report in the
   commit message. `raw/` (including `.prev` and `.download` files) is ignored by git.

## 3. If a download URL moves

Caltrans hosts the compiled PDFs under `/-/media/dot-media/programs/design/documents/cadd/`.
When `--fetch` gets a 404, open the download pages above, copy the new "Complete Download
Version" link into `download_url` in `manifest.json`, and run `--fetch` again. If the publisher
stops offering a compiled file, download by hand, save it under `raw/` with the `file` name from
the manifest, and run the builder without `--fetch`:

```bash
python3 scripts/build_knowledge.py --only ppm-text
```

Hash pinning and the change report work the same way; only the remote headers stay unpinned
until the next successful `--fetch`.

## 4. Fresh checkout

The committed artifacts are complete without the PDFs. To restore `raw/` (needed only to view
example sheets or to rebuild):

```bash
python3 scripts/build_knowledge.py --check     # reports the raw PDFs as absent
python3 scripts/build_knowledge.py --fetch     # downloads them; a matching sha256 rebuilds nothing
```

## 5. Adding another source

Same steps as in `README.md`: put the PDF under `<collection>/raw/`, add a hand-written manifest
entry with `download_url`, run the builder, run the tests. Candidates the PPM itself cites: the
Caltrans CADD Users Manual (text sizes, levels, line weights, sheet naming) and the Standard Plans
(abbreviations and symbols).

## What the manifest pins per source

| field | set by | meaning |
|---|---|---|
| `sha256`, `bytes`, `pages`, `pdf_metadata` | every build | the exact PDF the artifacts were built from |
| `remote` (`etag`, `last_modified`, `content_length`, `final_url`), `fetched_at` | `--fetch` | the publisher's copy at the last fetch; what `--dry-run` compares against |
| `artifacts`, `artifact_sha256`, `built_at`, `pages_without_text`, `outline_entries` | every build | what is committed and how it was derived |
| `edition`, `download_url`, `relevance`, `notes` | by hand | what the source is and why it is here |
