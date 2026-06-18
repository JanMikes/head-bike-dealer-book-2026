# HEAD Bikes 2026 — Catalogue Viewer

Static, single-page viewer for the HEAD 2026 bicycle catalogue, built from the source PDF into structured JSON.

- **`bikes.json`** — 105 bikes extracted from the 77-page catalogue PDF (model, ID, price, category, subcategory, wheel size, short info + full specifications as ordered label/value pairs). Values are preserved verbatim, including the catalogue's own typos and blank cells.
- **`parse.py`** — the PyMuPDF-based extraction script (coordinate-based column/row parsing). Requires `pip install pymupdf` and the source `katalog.pdf` (not committed, ~84 MB).
- **`extract_images.py`** — pulls the embedded product photos (alpha cut-outs) per bike and the section lifestyle photos per category out of the PDF into `images/` as WebP, and links them into `bikes.json`.
- **`optimize_images.py`** — post-processes the bike photos for fast delivery: flattens alpha onto white, downscales to 640 px, re-encodes WebP, and records each image's pixel dimensions in `bikes.json` (so the viewer reserves the image box and avoids layout shift). Idempotent; requires ImageMagick. Run after `extract_images.py`.
- **`fonts/`** — self-hosted Barlow Condensed and IBM Plex Mono (latin + latin-ext WebFonts), so the page carries no render-blocking third-party font CSS.
- **`index.html`** — single-file vanilla-JS viewer with search, category/subcategory filters, sorting, responsive layout and SEO metadata (Open Graph, Twitter card, JSON-LD product data). No build step.

Extraction was verified bike-by-bike against rendered page images.

## Image pipeline

```bash
python3 extract_images.py   # PDF -> images/ (+ image/thumbnail links in bikes.json)
python3 optimize_images.py  # flatten/resize/recompress + write image dimensions
```

## Run locally

```bash
python3 -m http.server 8000
# open http://localhost:8000
```
