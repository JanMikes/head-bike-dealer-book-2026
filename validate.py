#!/usr/bin/env python3
"""Validate bikes.json against the contract before building the site.

This guards the seam between the two halves of the pipeline: the PDF-extraction
side may change freely, but bikes.json must keep this shape or build.py would
emit broken cards. Run it between extraction and build; a non-zero exit means
"do not build".

It performs:
  * structural checks mirroring schema/bikes.schema.json (and, if the optional
    `jsonschema` package is installed, full validation against that schema), and
  * referential checks the schema cannot express — that every referenced image
    file exists on disk and carries the dimensions the viewer needs.

Dependency-free; `jsonschema` is used only if already available.
"""
import json
import sys
from pathlib import Path

DATA = Path("bikes.json")
SCHEMA = Path("schema/bikes.schema.json")
LV = {"label", "value"}


def structural(data, errors):
    if not isinstance(data, dict):
        errors.append("top level is not an object")
        return
    for key in ("brand", "currency", "bikes"):
        if key not in data:
            errors.append(f"missing top-level '{key}'")
    bikes = data.get("bikes")
    if not isinstance(bikes, list) or not bikes:
        errors.append("'bikes' must be a non-empty array")
        return

    for i, b in enumerate(bikes):
        where = f"bikes[{i}]" + (f" ({b.get('model')})" if isinstance(b, dict) else "")
        if not isinstance(b, dict):
            errors.append(f"{where}: not an object")
            continue
        for key in ("model", "category"):
            if not b.get(key):
                errors.append(f"{where}: missing/empty '{key}'")
        if b.get("column") not in ("left", "right"):
            errors.append(f"{where}: column must be 'left' or 'right', got {b.get('column')!r}")
        if not isinstance(b.get("page"), int):
            errors.append(f"{where}: page must be an integer")
        if b.get("price_czk") is not None and not isinstance(b.get("price_czk"), int):
            errors.append(f"{where}: price_czk must be integer or null")
        for arr in ("short_info", "specifications", "thumbnails"):
            if not isinstance(b.get(arr), list):
                errors.append(f"{where}: '{arr}' must be an array")
        for arr in ("short_info", "specifications"):
            for row in b.get(arr, []) if isinstance(b.get(arr), list) else []:
                if not (isinstance(row, dict) and LV <= set(row)):
                    errors.append(f"{where}: '{arr}' rows need 'label' and 'value'")
                    break


def referential(data, errors):
    for i, b in enumerate(data.get("bikes", [])):
        if not isinstance(b, dict):
            continue
        where = f"bikes[{i}] ({b.get('model')})"
        for img in [b.get("image")] + list(b.get("thumbnails") or []):
            if img and not Path(img).is_file():
                errors.append(f"{where}: image file not found: {img}")
        if b.get("image"):
            for d in ("img_w", "img_h"):
                if not (isinstance(b.get(d), int) and b[d] > 0):
                    errors.append(f"{where}: has image but missing/invalid {d} "
                                  f"(run optimize_images.py)")
        if b.get("price_czk") is not None and not b.get("price_raw"):
            errors.append(f"{where}: price_czk set but price_raw is empty")


def jsonschema_check(data, errors):
    try:
        import jsonschema
    except ImportError:
        print("  (jsonschema not installed — using built-in structural checks)")
        return
    if not SCHEMA.is_file():
        return
    schema = json.loads(SCHEMA.read_text())
    v = jsonschema.Draft202012Validator(schema)
    for e in sorted(v.iter_errors(data), key=lambda e: e.path):
        loc = "/".join(str(p) for p in e.path)
        errors.append(f"schema: {loc}: {e.message}")


def main() -> int:
    if not DATA.is_file():
        print(f"error: {DATA} not found", file=sys.stderr)
        return 1
    data = json.loads(DATA.read_text())
    errors = []
    jsonschema_check(data, errors)
    structural(data, errors)
    referential(data, errors)

    if errors:
        print(f"bikes.json INVALID — {len(errors)} problem(s):", file=sys.stderr)
        for e in errors[:50]:
            print(f"  - {e}", file=sys.stderr)
        if len(errors) > 50:
            print(f"  … and {len(errors) - 50} more", file=sys.stderr)
        return 1
    print(f"bikes.json valid — {len(data['bikes'])} bikes, all image references resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main())
