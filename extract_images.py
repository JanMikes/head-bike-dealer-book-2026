#!/usr/bin/env python3
"""Extract bike product photos and category intro photos from katalog.pdf.

- Per bike (from bikes.json): the largest embedded image whose bbox center
  falls in the bike's column half (page-wide on single-bike pages), skipping
  decorative images that repeat across 3+ pages (logos, ornaments).
- Per category: the largest image on the section's INTRODUCTION page.
- Photos carry an SMask (alpha cut-outs) -> recombined, downscaled to
  max 800px wide, saved as WebP into images/bikes/ and images/categories/.
- Updates bikes.json in place: adds "image" per bike and a top-level
  "category_images" map.
"""
import fitz
import json
import io
import os
from PIL import Image

PDF = 'katalog.pdf'
MAX_W = 800
MIN_AREA = 80_000    # pt^2 rendered area to qualify as a product photo
CATEGORY_PAGES = {   # category -> INTRODUCTION page (1-based)
    'MTB': 3, 'E-Bike': 26, 'Road': 40, 'Gravel': 40, 'Hybrid': 52, 'Kids': 58,
}

doc = fitz.open(PDF)
data = json.load(open('bikes.json'))
os.makedirs('images/bikes', exist_ok=True)
os.makedirs('images/categories', exist_ok=True)

# xrefs appearing on 3+ pages are decorative (logos, ornaments)
xref_pages = {}
for pno in range(len(doc)):
    for info in doc[pno].get_image_info(xrefs=True):
        xref_pages.setdefault(info['xref'], set()).add(pno)
decorative = {x for x, pages in xref_pages.items() if len(pages) >= 3}


def save_webp(xref, path):
    base = doc.extract_image(xref)
    img = Image.open(io.BytesIO(base['image'])).convert('RGB')
    if base['smask']:
        smask = doc.extract_image(base['smask'])
        mask = Image.open(io.BytesIO(smask['image'])).convert('L')
        if mask.size != img.size:
            mask = mask.resize(img.size)
        img = img.convert('RGBA')
        img.putalpha(mask)
    if img.width > MAX_W:
        img = img.resize((MAX_W, round(img.height * MAX_W / img.width)), Image.LANCZOS)
    img.save(path, 'WEBP', quality=82)
    return path


def candidates(pno):
    out = []
    for info in doc[pno].get_image_info(xrefs=True):
        if info['xref'] in decorative or info['xref'] == 0:
            continue
        x0, y0, x1, y1 = info['bbox']
        area = (x1 - x0) * (y1 - y0)
        if area >= MIN_AREA:
            out.append({'xref': info['xref'], 'cx': (x0 + x1) / 2, 'y0': y0,
                        'area': area})
    return out


# --- per-bike photos ---
bikes_by_page = {}
for b in data['bikes']:
    bikes_by_page.setdefault(b['page'], []).append(b)

missing = []
xref_cache = {}
for page_no, bikes in sorted(bikes_by_page.items()):
    cands = candidates(page_no - 1)
    for b in bikes:
        half = [c for c in cands if (c['cx'] < 720) == (b['column'] == 'left')]
        if len(bikes) == 1 and not half:
            half = cands  # single-bike page with the photo on the other side
        if not half:
            b['image'] = None
            missing.append((page_no, b['column'], b['model']))
            continue
        pick = max(half, key=lambda c: c['area'])
        if pick['xref'] in xref_cache:
            b['image'] = xref_cache[pick['xref']]
        else:
            path = f"images/bikes/p{page_no:02d}_{b['column']}.webp"
            b['image'] = save_webp(pick['xref'], path)
            xref_cache[pick['xref']] = b['image']

# --- category photos ---
cat_images = {}
for cat, page_no in CATEGORY_PAGES.items():
    cands = candidates(page_no - 1)
    if not cands:
        continue
    pick = max(cands, key=lambda c: c['area'])
    fname = f"images/categories/{cat.lower().replace(' ', '-')}.webp"
    cat_images[cat] = save_webp(pick['xref'], fname)
data['category_images'] = cat_images

json.dump(data, open('bikes.json', 'w'), ensure_ascii=False, indent=2)

n = sum(1 for b in data['bikes'] if b.get('image'))
print(f'bike images: {n}/{len(data["bikes"])}')
print(f'category images: {list(cat_images)}')
if missing:
    print('missing:', missing)
total = sum(os.path.getsize(os.path.join(r, f))
            for r, _, fs in os.walk('images') for f in fs)
print(f'total size: {total/1e6:.1f} MB')
