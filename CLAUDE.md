# HEAD Bikes 2026 — catalogue viewer

Static GitHub Pages site (totokolo.cz). The deployed `index.html` is **fully
prerendered**: every bike is baked into the HTML by `build.py`, and the in-page
script only filters/sorts/searches the existing DOM — no `fetch`, no
client-side rendering. Data and images come from `katalog.pdf`.

## Architecture: two halves joined by a contract

```
PDF-dependent (volatile)            bikes.json            PDF-independent (stable)
parse.py, extract_images.py   →   (the contract,    →   optimize_images.py, build.py
                                   schema-checked)
```

`bikes.json` is the seam. Change the PDF parser however you like; as long as
its output still validates (`schema/bikes.schema.json` + `validate.py`), the
site builds correctly. `validate.py` runs at this seam and fails loudly on a
broken contract — run it before building.

## Pipeline — RUN IN THIS ORDER (or `make all`)

```bash
python3 parse.py            # katalog.pdf -> bikes.json (models, specs, prices)
python3 extract_images.py   # PDF -> images/ (800px, alpha) + image/thumbnail links
python3 optimize_images.py  # flatten alpha -> 640px WebP + write img_w/img_h to bikes.json
python3 validate.py         # assert bikes.json matches the contract (+ images exist)
python3 build.py            # bikes.json -> prerender into index.html
```

**Gotchas:**
- **Never skip `optimize_images.py` after `extract_images.py`.** The extractor
  writes large 800px images *with alpha* and no dimensions; shipping those
  regresses performance and CLS. `optimize_images.py` fixes that and writes
  `img_w`/`img_h`. Idempotent.
- **Re-run `build.py` after any data change.** `index.html` is partly generated:
  `build.py` fills the `<!--build:NAME-->…<!--/build:NAME-->` regions (cards,
  chips, subcats, count, footer stats, Product JSON-LD). Edit anything *outside*
  those markers (head, CSS, the script) by hand; never hand-edit inside them.
- `parse.py` overwrites `bikes.json`, so a full regen re-runs all five steps.

## Performance / SEO invariants — don't regress these

Mobile Lighthouse: performance ~96, SEO 100, best-practices 100, CLS 0, TBT 0.
(Perf is ~96 not ~99 by design: prerendering the whole catalogue ships a bigger
initial HTML — the deliberate trade for crawlable content. The earlier 99 was
client-rendered and not in the HTML.)

- **Prerendered content = the SEO win.** All cards + `Product`/`ItemList`
  JSON-LD live in the static HTML. Don't revert to fetching `bikes.json` and
  rendering client-side.
- **JSON-LD goes at the END of `<body>`**, not `<head>` (the ~37 KB block would
  otherwise delay first paint). `build.py`'s marker is placed there.
- **`content-visibility: auto`** on `.bike:nth-of-type(n+5)` skips off-screen
  card layout (the first row stays eager so the LCP image isn't delayed).
- **Image dimensions.** Every `<img>` has `width`/`height` from `img_w`/`img_h`
  → box reserved before load (CLS 0). Keep the attributes and the JSON fields.
- **Self-hosted fonts** in `fonts/` via inline `@font-face`. Do **not** re-add
  the Google Fonts `<link>` (render-blocking, cost ~3.6 s FCP). Above-the-fold
  weights (Barlow 600/700, Plex 400 latin) are preloaded.
- **LCP image preload.** `<link rel="preload" as="image" href="images/bikes/p05_left.webp">`
  is the first card of the default catalogue-order view — update if the first
  bike changes. First 4 cards eager, rest lazy.
- **Chips & subcats are build-generated** from the data, so they stay in sync
  automatically (no hardcoded list to maintain).

## Verifying performance changes

Local `python3 -m http.server` does NOT gzip — and the *directory index* (`/`)
needs gzip too, not just explicit file paths. GitHub Pages gzips everything, so
measure through a gzipping server that compresses `/` or Lighthouse will see the
~420 KB raw HTML (vs ~25 KB gzipped) and report a wildly wrong LCP. Category
images (`images/categories/`) are only the social `og:image`, never rendered on
the page.
