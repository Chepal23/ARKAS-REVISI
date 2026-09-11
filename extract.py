# -*- coding: utf-8 -*-
"""Extract ARKAS monthly detail (Rincian Kertas Kerja perBulan) from PDF to JSON."""
import json
import re
import pymupdf

PDF = 'uploads/ARKAS Januari-Desember  2026.pdf'

BANDS = {
    'urut': (0, 66),
    'rekening': (66, 150),
    'L1': (150, 172),
    'L2': (172, 189),
    'L3': (189, 210),
    'uraian': (210, 560),
    'volume': (560, 624),
    'satuan': (624, 692),
    'tarif': (692, 762),
    'jumlah': (762, 1000),
}

MONTHS = ['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus',
          'September','Oktober','November','Desember']

def money(s):
    return int(s.replace('.', ''))

def money_fmt(n):
    return f"{n:,}".replace(',', '.')

def col_of(xc):
    for k, (a, b) in BANDS.items():
        if a <= xc < b:
            return k
    return None

def page_words(doc, p):
    ws = []
    for w in doc[p].get_text('words'):
        ws.append({'x': w[0], 'y': w[1], 'x1': w[2], 'y1': w[3],
                   'xc': (w[0] + w[2]) / 2, 'yc': (w[1] + w[3]) / 2, 't': w[4]})
    return ws

def parse_page(words):
    """Return (rows, total). rows = list of row dicts on this page (in y order)."""
    anchors = []
    for w in words:
        if w['xc'] < 66 and re.fullmatch(r'\d{1,2}\.', w['t']):
            anchors.append((w['yc'], int(w['t'].rstrip('.'))))
    anchors.sort()
    ded = []
    for y, n in anchors:
        if ded and abs(ded[-1][0] - y) < 4:
            continue
        ded.append((y, n))
    anchors = ded
    # total row on this page?
    total_y = None
    total = None
    for w in words:
        if w['t'] == 'Jumlah' and 210 <= w['xc'] < 480:
            total_y = w['yc']
    if total_y is not None:
        best = None
        for w in words:
            if w['xc'] > 762 and abs(w['yc'] - total_y) < 6:
                if best is None or abs(w['yc'] - total_y) < abs(best['yc'] - total_y):
                    best = w
        if best:
            total = best['t']
    rows = []
    n = len(anchors)
    for idx, (ay, num) in enumerate(anchors):
        y_top = (anchors[idx - 1][0] + ay) / 2 if idx > 0 else ay - 13
        if idx == n - 1:
            y_bot = (ay + total_y) / 2 if total_y else ay + 14
        else:
            y_bot = (ay + anchors[idx + 1][0]) / 2
        y_bot = min(y_bot, 558)  # never reach the page footer (y ~564)
        row = {'no': num, 'uraian': '', 'rekening': '', 'L1': '', 'L2': '', 'L3': '',
               'volume': '', 'satuan': '', 'tarif': '', 'jumlah': ''}
        u_words = []
        for w in words:
            if w['yc'] < y_top or w['yc'] >= y_bot:
                continue
            c = col_of(w['xc'])
            if c in (None, 'urut'):
                continue
            if c == 'uraian':
                u_words.append(w)
            elif c == 'rekening':
                row['rekening'] += w['t']
            elif c in ('L1', 'L2', 'L3'):
                row[c] = w['t'].rstrip('.')
            elif c == 'volume':
                if re.fullmatch(r'\d+', w['t']):
                    row['volume'] += w['t']
            elif c == 'satuan':
                row['satuan'] += w['t'] + ' '
            elif c == 'tarif':
                row['tarif'] += w['t']
            elif c == 'jumlah':
                row['jumlah'] += w['t']
        u_words.sort(key=lambda w: (round(w['yc']), w['x']))
        row['uraian'] = ' '.join(w['t'] for w in u_words)
        row['satuan'] = row['satuan'].strip()
        rows.append(row)
    return rows, total

def main():
    doc = pymupdf.open(PDF)
    month_pages = {}
    for i in range(doc.page_count):
        t = doc[i].get_text()
        for mth in MONTHS:
            if re.search(r'\n' + mth + r' 2026', t):
                if mth not in month_pages:
                    month_pages[mth] = i
    order = [month_pages[m] for m in MONTHS]
    ends = order[1:] + [doc.page_count]

    result = {}
    for mi, mth in enumerate(MONTHS):
        sp = month_pages[mth]
        ep = ends[mi]
        rows = []
        total = None
        for p in range(sp, ep):
            pr, pt = parse_page(page_words(doc, p))
            rows.extend(pr)
            if pt:
                total = pt
        result[mth] = {'rows': rows, 'total': total}

    with open('arkas_data.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print('%-11s %6s %12s %12s %s' % ('Bulan', 'rows', 'Total(PDF)', 'SumLeaf', 'OK'))
    ok_all = True
    for mth in MONTHS:
        rows = result[mth]['rows']
        total = result[mth]['total']
        leaf_sum = 0
        bad = 0
        for r in rows:
            if r['jumlah'] and not re.fullmatch(r'[\d.]+', r['jumlah']):
                bad += 1
            if r['rekening']:
                try:
                    leaf_sum += money(r['jumlah'])
                except ValueError:
                    bad += 1
        ok = (money(total) == leaf_sum and bad == 0)
        ok_all = ok_all and ok
        print('%-11s %6d %12s %12s %s' % (mth, len(rows), total, money_fmt(leaf_sum),
                                           'OK' if ok else f'BAD(badrows={bad})'))
    print('ALL OK' if ok_all else 'SOME BAD')

if __name__ == '__main__':
    main()
