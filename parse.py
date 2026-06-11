#!/usr/bin/env python3
"""Parse katalog.pdf (HEAD Dealer Book 2026) into structured JSON.

Strategy (coordinate-based, PyMuPDF):
- Spec pages are detected by the presence of "Short info" heading spans.
- Each "Short info" span marks the left edge (x0) of one bike column.
- Within a column: title = largest span near top; wheel size = `NN"` span;
  frame badge = CARBON/ALLOY small span near top; rotated sidebar text
  nearest to the column = subcategory; bottom holds price (`NN NNN,-`) and
  ID (`HNNNNN`).
- "Short info :" and "Specifications" headings split the column vertically
  into the two key/value blocks. Labels sit at x0..x0+112, values at
  x0+112.. ; rows pair by y proximity; value lines without a label within
  tolerance are treated as wrapped continuations of the previous value.
- Values are kept verbatim (catalogue typos included) for fidelity.
"""
import fitz
import json
import re
import sys
import unicodedata

PDF = 'katalog.pdf'
OUT = 'bikes.json'

# top-level section per page (1-based), derived from INTRODUCTION/THE MODELS pages
SECTIONS = [
    (5, 7, 'MTB', 'Full Suspension'),
    (10, 12, 'MTB', 'Hardtail Carbon'),
    (14, 18, 'MTB', 'Hardtail Alloy'),
    (20, 25, 'MTB', 'Joy'),
    (28, 39, 'E-Bike', None),
    (43, 48, 'Road', None),
    (49, 51, 'Gravel', None),
    (53, 57, 'Hybrid', None),
    (61, 63, 'Kids', 'Light Weight'),
    (64, 76, 'Kids', None),
]

ID_RE = re.compile(r'\bH\d{5}[A-Z]?\b')
PRICE_RE = re.compile(r'^\d[\d ]*\d{3}\s*,-$')
WHEEL_RE = re.compile(r'^\d{2}(?:[.,]\d)?(?:\s*-\s*\d{2}(?:[.,]\d)?)?\+?\s*["”]$')

LABEL_X_MAX = 112      # label zone width relative to column x0
ROW_Y_TOL = 5.0        # label/value y pairing tolerance
NBSP = ' '


def clean(s):
    s = unicodedata.normalize('NFC', s.replace(NBSP, ' '))
    return re.sub(r'\s+', ' ', s).strip()


def section_for(page_no):
    for lo, hi, cat, sub in SECTIONS:
        if lo <= page_no <= hi:
            return cat, sub
    return None, None


def get_spans(page):
    """Return (horizontal spans, rotated lines). Span: dict x, y, size, text."""
    horiz, rotated = [], []
    seen = set()  # Canva duplicates identical spans at the same coordinates
    for b in page.get_text('dict')['blocks']:
        for line in b.get('lines', []):
            text = clean(' '.join(s['text'] for s in line['spans']))
            if not text:
                continue
            if line['dir'] != (1.0, 0.0):
                x = min(s['origin'][0] for s in line['spans'])
                key = ('rot', round(x), text)
                if key not in seen:
                    seen.add(key)
                    rotated.append({'x': x, 'text': text})
                continue
            for s in line['spans']:
                t = clean(s['text'])
                if not t:
                    continue
                key = (round(s['origin'][0]), round(s['origin'][1]), t)
                if key not in seen:
                    seen.add(key)
                    horiz.append({'x': s['origin'][0], 'y': s['origin'][1],
                                  'size': s['size'], 'text': t})
    return horiz, rotated


def parse_column(spans, x0, x1, page_no, col_name, rotated):
    col = [s for s in spans if x0 - 20 <= s['x'] < x1 - 20]
    warnings = []
    bike = {
        'id': None, 'model': None, 'page': page_no, 'column': col_name,
        'category': None, 'subcategory': None, 'wheel_size': None,
        'frame_badge': None, 'price_czk': None, 'price_raw': None,
        'short_info': [], 'specifications': [], 'warnings': warnings,
    }
    cat, sub = section_for(page_no)
    bike['category'] = cat
    if rotated:
        mid = (x0 + x1) / 2
        nearest = min(rotated, key=lambda r: abs(r['x'] - mid))
        bike['subcategory'] = nearest['text']
    elif sub:
        bike['subcategory'] = sub
    if sub and not bike['subcategory']:
        bike['subcategory'] = sub

    # header zone (above "Short info")
    si = [s for s in col if s['text'].startswith('Short info')]
    if not si:
        warnings.append('no Short info heading')
        return None
    si_y = min(s['y'] for s in si)
    header = [s for s in col if s['y'] < si_y - 5]
    titles = [s for s in header if s['size'] >= 24 and not WHEEL_RE.match(s['text'])
              and not PRICE_RE.match(s['text'])]
    if titles:
        # Canva sometimes leaves an older title span covered by the visible
        # one; spans overlapping vertically are duplicates - keep the one
        # drawn last (document order = paint order)
        deduped = []
        for s in titles:  # titles preserve document order
            deduped = [d for d in deduped
                       if abs(d['y'] - s['y']) >= s['size'] * 0.8
                       or abs(d['x'] - s['x']) >= 60]
            deduped.append(s)
        titles = deduped
        t = max(titles, key=lambda s: s['size'])
        same = sorted([s for s in titles if abs(s['y'] - t['y']) < 8 and abs(s['size'] - t['size']) < 2],
                      key=lambda s: s['x'])
        bike['model'] = clean(' '.join(s['text'] for s in same))
    else:
        warnings.append('no title found')
    wheels = [s for s in header if WHEEL_RE.match(s['text'])]
    if wheels:
        bike['wheel_size'] = min(wheels, key=lambda s: s['y'])['text'].replace('”', '"')
    badge = [s for s in header if s['text'].upper() in ('CARBON', 'ALLOY') and s['size'] < 20]
    if badge:
        bike['frame_badge'] = badge[0]['text'].upper()

    # bottom zone: price + id
    for s in col:
        if PRICE_RE.match(s['text']) and s['y'] > si_y:
            bike['price_raw'] = s['text']
            bike['price_czk'] = int(re.sub(r'[^\d]', '', s['text']))
    ids = [m.group(0) for s in col for m in [ID_RE.search(s['text'])] if m]
    if ids:
        bike['id'] = ids[0]
        if len(set(ids)) > 1:
            warnings.append(f'multiple IDs in column: {ids}')
    else:
        warnings.append('no ID found')

    # specifications heading
    spec_heads = [s for s in col if s['text'] == 'Specifications']
    spec_y = min((s['y'] for s in spec_heads), default=None)
    if spec_y is None:
        warnings.append('no Specifications heading')

    # key/value rows
    id_y = min((s['y'] for s in col if ID_RE.search(s['text'])), default=1e9)
    body = [s for s in col if s['y'] > si_y + 2 and s['y'] < id_y - 2
            and s['size'] < 20  # exclude stray headings/badges
            and s['text'] != 'Specifications'
            and not s['text'].startswith('Short info')
            and not PRICE_RE.match(s['text'])
            and not ID_RE.fullmatch(s['text'])
            and s['text'] not in ('ID', 'LIGHT WEIGHT')]  # LIGHT WEIGHT = decorative badge
    # adaptive label/value boundary: labels cluster at the column's left edge,
    # values start after the first sizeable x gap
    xs = sorted(set(round(s['x']) for s in body))
    boundary = (xs[0] + LABEL_X_MAX) if xs else x0 + LABEL_X_MAX
    for a, b in zip(xs, xs[1:]):
        if b - a > 40 and a - xs[0] < 60:
            boundary = (a + b) / 2
            break
    labels = sorted([s for s in body if s['x'] < boundary], key=lambda s: s['y'])
    values = sorted([s for s in body if s['x'] >= boundary], key=lambda s: s['y'])

    used = set()
    rows = []  # (y, label, value)
    for lab in labels:
        best, best_d = None, ROW_Y_TOL
        for i, v in enumerate(values):
            if i in used:
                continue
            d = abs(v['y'] - lab['y'])
            if d < best_d:
                best, best_d = i, d
        val = ''
        if best is not None:
            used.add(best)
            val = values[best]['text']
        rows.append([lab['y'], lab['text'], val])
    # unmatched value spans: wrapped continuation of nearest row above
    for i, v in enumerate(values):
        if i in used:
            continue
        above = [r for r in rows if r[0] < v['y'] + ROW_Y_TOL]
        if above:
            r = max(above, key=lambda r: r[0])
            r[2] = clean(r[2] + ' ' + v['text']) if r[2] else v['text']
        else:
            warnings.append(f'orphan value: {v["text"]!r}')
    rows.sort(key=lambda r: r[0])

    for y, label, value in rows:
        target = bike['short_info'] if (spec_y is None or y < spec_y) else bike['specifications']
        target.append({'label': label, 'value': value})
    return bike


def main():
    doc = fitz.open(PDF)
    bikes = []
    skipped = []
    for pno in range(len(doc)):
        page_no = pno + 1
        page = doc[pno]
        spans, rotated = get_spans(page)
        si_spans = sorted([s for s in spans if s['text'].startswith('Short info')],
                          key=lambda s: s['x'])
        if not si_spans:
            skipped.append(page_no)
            continue
        col_x = []
        for s in si_spans:
            if not col_x or s['x'] - col_x[-1] > 150:
                col_x.append(s['x'])
        bounds = col_x + [page.rect.width]
        for i, x0 in enumerate(col_x):
            name = 'left' if (len(col_x) == 1 or i == 0) else 'right'
            b = parse_column(spans, x0, bounds[i + 1], page_no, name, rotated)
            if b:
                bikes.append(b)
    out = {
        'source': PDF,
        'brand': 'HEAD',
        'title': 'Dealer Book 2026',
        'currency': 'CZK',
        'bike_count': len(bikes),
        'bikes': bikes,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    n_warn = sum(1 for b in bikes if b['warnings'])
    print(f'pages with no spec data skipped: {skipped}')
    print(f'bikes: {len(bikes)}, with warnings: {n_warn}')
    for b in bikes:
        if b['warnings']:
            print(f"  p{b['page']} {b['column']} {b['model']}: {b['warnings']}")


if __name__ == '__main__':
    main()
