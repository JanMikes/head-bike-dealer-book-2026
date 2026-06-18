#!/usr/bin/env python3
"""Optimise the extracted bike photos for fast web delivery.

Post-processing step for the images that extract_images.py writes into
images/bikes/. For every photo it:

  * flattens the alpha channel onto white (the card background is white, and
    opaque WebP compresses dramatically better than the alpha cut-outs);
  * downscales to MAX_EDGE on the longest side (the catalogue never displays
    them larger than ~255 CSS px, so 640 px stays crisp on retina screens);
  * re-encodes as WebP at QUALITY with the slowest/best compression method;
  * records the final pixel dimensions in bikes.json so the viewer can emit
    explicit width/height attributes (prevents cumulative layout shift).

The step is idempotent: already-optimised files (no alpha, within MAX_EDGE)
are left untouched and only their dimensions are (re)recorded.

Pipeline:  python extract_images.py  &&  python optimize_images.py
Requires ImageMagick (`magick`) on PATH.
"""
import json
import subprocess
import sys
from pathlib import Path

BIKES_DIR = Path("images/bikes")
MAX_EDGE = 640
QUALITY = 82


def probe(path: Path) -> tuple[int, int, bool]:
    """Return (width, height, has_alpha) for an image."""
    out = subprocess.check_output(
        ["identify", "-format", "%w %h %[channels]", str(path)], text=True
    )
    w, h, channels = out.split(maxsplit=2)
    return int(w), int(h), "a" in channels.lower()


def main() -> None:
    if not BIKES_DIR.is_dir():
        sys.exit(f"{BIKES_DIR} not found — run extract_images.py first")

    dims: dict[str, list[int]] = {}
    total_before = total_after = 0

    for src in sorted(BIKES_DIR.glob("*.webp")):
        w, h, alpha = probe(src)
        before = src.stat().st_size
        total_before += before

        if alpha or max(w, h) > MAX_EDGE:
            tmp = src.with_suffix(".tmp.webp")
            subprocess.run(
                [
                    "magick", str(src),
                    "-resize", f"{MAX_EDGE}x{MAX_EDGE}>",      # only shrink
                    "-background", "white", "-flatten", "-alpha", "off",
                    "-quality", str(QUALITY),
                    "-define", "webp:method=6",
                    str(tmp),
                ],
                check=True,
            )
            tmp.replace(src)
            w, h, _ = probe(src)

        total_after += src.stat().st_size
        dims[f"images/bikes/{src.name}"] = [w, h]

    # Inject final dimensions into bikes.json for layout-shift-free rendering.
    data = json.loads(Path("bikes.json").read_text())
    for bike in data["bikes"]:
        img = bike.get("image")
        if img in dims:
            bike["img_w"], bike["img_h"] = dims[img]
    Path("bikes.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    )

    saved = total_before - total_after
    print(f"Optimised {len(dims)} images; dimensions written to bikes.json")
    print(f"  before: {total_before/1024:.0f} KB")
    print(f"  after:  {total_after/1024:.0f} KB")
    if total_before:
        print(f"  saved:  {saved/1024:.0f} KB ({saved*100/total_before:.0f}%)")


if __name__ == "__main__":
    main()
