#!/usr/bin/env python3
"""Render bikes.json into the static index.html (the json -> HTML build step).

This is the presentation half of the pipeline and depends ONLY on bikes.json
(never on the source PDF). It bakes the full catalogue into index.html so the
deployed page is complete on arrival — good for SEO and first paint — while the
in-page script only filters/sorts the prerendered DOM (no fetch, no rendering).

It replaces the content between `<!--build:NAME-->` / `<!--/build:NAME-->`
markers in index.html, in place and idempotently:

    jsonld   Product/ItemList structured data (in <head>)
    chips    category filter chips
    subcats  subcategory <option>s
    cards    every bike <article> (in catalogue order, with filter/sort data-*)
    count    the "<shown> / <total>" counter
    stats    the footer line

Pipeline:  parse.py -> extract_images.py -> optimize_images.py -> validate.py -> build.py
"""
import json
import re
from pathlib import Path

SITE = "https://totokolo.cz/"
HTML = Path("index.html")
DATA = Path("bikes.json")


def esc(s) -> str:
    s = "" if s is None else str(s)
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def catalogue_order(bikes):
    """Default 'catalogue order' = PDF page, then left column before right.

    Page/column are PDF-layout artifacts; they stay encapsulated here and reach
    the page only as an opaque data-order index, so the viewer never depends on
    PDF-specific concepts.
    """
    return sorted(bikes, key=lambda b: (b.get("page", 0), b.get("column", "")))


def rows(pairs) -> str:
    return "".join(
        f'<tr><td class="k">{esc(r.get("label"))}</td>'
        f'<td class="v{"" if r.get("value") else " blank"}">{esc(r.get("value"))}</td></tr>'
        for r in pairs
    )


def card(b, i) -> str:
    eager = i < 4                       # first rows are above the fold
    dim = f' width="{b["img_w"]}" height="{b["img_h"]}"' if b.get("img_w") else ""
    price = (f'{esc(b["price_raw"])} <small>CZK</small>'
             if b.get("price_czk") is not None else "<small>no price</small>")

    img = ""
    if b.get("image"):
        loading = "eager" if eager else "lazy"
        prio = ' fetchpriority="high"' if i == 0 else ""
        alts = ""
        if b.get("thumbnails"):
            alts = '<div class="alts">' + "".join(
                f'<img src="{esc(t)}" alt="HEAD {esc(b["model"])} variant" '
                f'width="48" height="36" decoding="async" loading="lazy">'
                for t in b["thumbnails"]
            ) + "</div>"
        img = (f'<div class="bike-img">'
               f'<img class="main" src="{esc(b["image"])}" '
               f'alt="HEAD {esc(b["model"])} {esc(b["category"])} bike"{dim} '
               f'decoding="async" loading="{loading}"{prio}>{alts}</div>')

    tags = (
        (f'<span class="tag id">ID {esc(b["id"])}</span>' if b.get("id") else "")
        + (f'<span class="tag badge">{esc(b["frame_badge"])}</span>' if b.get("frame_badge") else "")
        + f'<span class="tag">{esc(b["category"])}</span>'
        + (f'<span class="tag">{esc(b["subcategory"])}</span>' if b.get("subcategory") else "")
    )

    wheel = (f'<span class="wheel">{esc(b["wheel_size"])}</span>'
             if b.get("wheel_size") else "")

    specs = ""
    if b.get("short_info"):
        specs += f"<h3>Short info</h3><table>{rows(b['short_info'])}</table>"
    if b.get("specifications"):
        specs += (f"<details><summary>Specifications ({len(b['specifications'])})</summary>"
                  f"<table>{rows(b['specifications'])}</table></details>")

    # No data-search attribute: the viewer searches each card's text content
    # (already in the DOM), which keeps the HTML smaller.
    data = (
        f'data-cat="{esc(b.get("category"))}" '
        f'data-sub="{esc(b.get("subcategory") or "")}" '
        f'data-price="{b["price_czk"] if b.get("price_czk") is not None else ""}" '
        f'data-model="{esc(b.get("model"))}" '
        f'data-order="{i}"'
    )
    return (f'<article class="bike" {data}>'
            f'<div class="bike-head"><h2>{esc(b["model"])}</h2>'
            f'{wheel}<span class="price">{price}</span></div>'
            f'{img}<div class="tags">{tags}</div>'
            f'<div class="specs">{specs}</div></article>')


def jsonld(bikes) -> str:
    items = []
    for i, b in enumerate(bikes):
        product = {"@type": "Product", "name": b["model"], "category": b["category"],
                   "brand": {"@type": "Brand", "name": "HEAD"}}
        if b.get("id"):
            product["sku"] = b["id"]
        if b.get("image"):
            product["image"] = SITE + b["image"]
        if b.get("price_czk") is not None:
            product["offers"] = {"@type": "Offer", "price": b["price_czk"],
                                 "priceCurrency": "CZK",
                                 "availability": "https://schema.org/InStock"}
        items.append({"@type": "ListItem", "position": i + 1, "item": product})
    payload = {"@context": "https://schema.org", "@type": "ItemList",
               "name": "HEAD Bikes 2026", "numberOfItems": len(bikes),
               "itemListElement": items}
    blob = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{blob}</script>'


def fill(html: str, name: str, content: str) -> str:
    open_m, close_m = f"<!--build:{name}-->", f"<!--/build:{name}-->"
    if open_m not in html or close_m not in html:
        raise SystemExit(f"marker <!--build:{name}--> missing from index.html")
    pattern = re.compile(re.escape(open_m) + ".*?" + re.escape(close_m), re.DOTALL)
    return pattern.sub(lambda _: open_m + content + close_m, html, count=1)


def main() -> None:
    data = json.loads(DATA.read_text())
    bikes = catalogue_order(data["bikes"])
    categories = list(dict.fromkeys(b["category"] for b in data["bikes"]))
    subcats = sorted({b["subcategory"] for b in data["bikes"] if b.get("subcategory")})
    n = len(bikes)

    chips = ('<span class="chip on" data-cat="">Vše</span>'
             + "".join(f'<span class="chip" data-cat="{esc(c)}">{esc(c)}</span>'
                       for c in categories))
    subcat_opts = "".join(f"<option>{esc(s)}</option>" for s in subcats)
    cards = "".join(card(b, i) for i, b in enumerate(bikes))
    count = f'<b id="shown">{n}</b> / <span id="total">{n}</span>'
    stats = (f"<span>HEAD Bikes 2026</span><span>{n} models · all prices in CZK</span>"
             f"<span>Specifications and prices are subject to change.</span>")

    html = HTML.read_text()
    for name, content in (("jsonld", jsonld(bikes)), ("chips", chips),
                          ("subcats", subcat_opts), ("cards", cards),
                          ("count", count), ("stats", stats)):
        html = fill(html, name, content)
    HTML.write_text(html)
    print(f"Built index.html: {n} bikes, {len(categories)} categories, "
          f"{len(subcats)} subcategories")


if __name__ == "__main__":
    main()
