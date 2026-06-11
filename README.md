# HEAD Dealer Book 2026 — Catalogue Viewer

Proof-of-concept static viewer for the HEAD bicycle dealer catalogue, parsed from the source PDF into structured JSON.

- **`bikes.json`** — 105 bikes extracted from the 77-page catalogue PDF (model, ID, price, category, subcategory, wheel size, short info + full specifications as ordered label/value pairs). Values are preserved verbatim, including the catalogue's own typos and blank cells.
- **`parse.py`** — the PyMuPDF-based extraction script (coordinate-based column/row parsing). Requires `pip install pymupdf` and the source `katalog.pdf` (not committed, ~84 MB).
- **`index.html`** — single-file vanilla-JS viewer with search, category/subcategory filters and sorting. No build step.

Extraction was verified bike-by-bike against rendered page images.

## Run locally

```bash
python3 -m http.server 8000
# open http://localhost:8000
```
