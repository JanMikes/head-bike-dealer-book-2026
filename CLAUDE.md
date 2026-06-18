# HEAD Bikes 2026 — catalogue viewer

Static GitHub Pages site (totokolo.cz): a single `index.html` (vanilla JS) that
fetches `bikes.json` and renders the catalogue. No framework, no build step for
the page itself. Data and images are generated from `katalog.pdf` by the
scripts below.

## Data / image pipeline — RUN IN THIS ORDER

```bash
python3 parse.py            # katalog.pdf -> bikes.json (models, specs, prices)
python3 extract_images.py   # PDF -> images/ (800px, with alpha) + image/thumbnail links
python3 optimize_images.py  # flatten alpha -> 640px WebP + write img_w/img_h to bikes.json
```

**Gotcha — never skip `optimize_images.py` after `extract_images.py`.**
`extract_images.py` writes large 800px images *with alpha channels* and does
**not** add image dimensions. Shipping those directly regresses mobile
performance (huge images + cumulative layout shift). `optimize_images.py`
downscales/flattens/recompresses them (~40% smaller) and records each image's
pixel size into `bikes.json` (`img_w`/`img_h`). It is idempotent, so re-running
it is always safe. Each `parse.py` run overwrites `bikes.json`, so a full
regen must re-run all three steps in order.

## Performance invariants — don't regress these (mobile Lighthouse ~99)

The page was tuned from a Lighthouse score of 65 to 99. Keep these intact:

- **Image dimensions.** Every `<img>` gets `width`/`height` from `bikes.json`
  (`img_w`/`img_h`) so its box is reserved before load (CLS = 0). Don't drop
  the attributes or the `img_w`/`img_h` fields.
- **Self-hosted fonts.** Barlow Condensed + IBM Plex Mono live in `fonts/`
  (latin + latin-ext woff2) and are declared via inline `@font-face`. Do **not**
  re-add the Google Fonts `<link>` — it was render-blocking (cost ~3.6 s FCP).
  The above-the-fold weights (Barlow 600/700, Plex 400 latin) are preloaded.
- **Pre-rendered category chips.** The chips in `index.html` (`#cats`) are
  hardcoded to match the data's categories (MTB, E-Bike, Road, Gravel, Hybrid,
  Kids). `init()` regenerates them from the data, so if the category set
  changes, update the static chips too or the filter row will shift on load.
- **LCP image preload.** `<link rel="preload" as="image" href="images/bikes/p05_left.webp">`
  is the first card of the default (catalogue-order) view. If the first bike
  changes, update this path. The first 4 cards load eagerly; the rest are lazy.

## Verifying performance changes

Local `python3 -m http.server` does NOT gzip; GitHub Pages does, so it makes
`bikes.json` look ~17x larger and skews LCP. To measure realistically, serve
through a gzipping server before running Lighthouse mobile. Category images
(`images/categories/`) are only used as social `og:image`, not rendered on the
page — they don't affect page performance.
