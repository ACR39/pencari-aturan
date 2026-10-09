#!/usr/bin/env python3
"""Pecah dokumen peraturan menjadi potongan per pasal (+ lampiran, pembukaan, penjelasan).

Pemakaian: python3 -I pecah.py <keluaran.json> <uu.txt> <permenhub.txt>
"""
import json
import re
import sys

PAGE_NO = re.compile(r'^\s*-\s*\d+\s*-?\s*$')
CATCHWORD = re.compile(r'\.\s\.\s\.\s*$')
PASAL = re.compile(r'^\s*Pasal\s+(\d+)\s*$')
BAB = re.compile(r'^\s*BAB\s+([IVXLC]+)\s*$')
BAGIAN = re.compile(
    r'^\s*Bagian\s+(Kesatu|Kedua|Ketiga|Keempat|Kelima|Keenam|Ketujuh|Kedelapan|'
    r'Kesembilan|Kesepuluh|Kesebelas|Kedua Belas|Ketiga Belas|Keempat Belas)\s*$')
PARAGRAF = re.compile(r'^\s*Paragraf\s+(\d+)\s*$')
MARKER = re.compile(r'^(\(\d+\)|\d+\)|[a-z]\)|[a-z]\.|\d+\.)\s')
LAMPIRAN = re.compile(r'^\s*LAMPIRAN\s+(I|II|III|IV|V)\s*$')


def bersih(lines):
    out = []
    for ln in lines:
        s = ln.rstrip()
        if PAGE_NO.match(s):
            continue
        if CATCHWORD.search(s):
            continue
        out.append(s)
    return out


def perbaiki(teks):
    teks = re.sub(r'(?i)undangundang', lambda m: m.group(0)[:6] + '-' + m.group(0)[6:], teks)
    teks = re.sub(r'(?i)perundangundangan', lambda m: m.group(0)[:9] + '-' + m.group(0)[9:], teks)
    teks = re.sub(r'(?i)undangundangan', lambda m: m.group(0)[:6] + '-' + m.group(0)[6:], teks)
    teks = re.sub(r'[ \t]+', ' ', teks)
    return teks.strip()


def reflow(lines):
    paras, cur = [], []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if MARKER.match(s) and cur:
            paras.append(' '.join(cur))
            cur = [s]
        else:
            cur.append(s)
    if cur:
        paras.append(' '.join(cur))
    return perbaiki('\n'.join(perbaiki(p) for p in paras))


def judul_lanjut(lines, i):
    """Ambil judul (bisa 2 baris jika baris pertama berakhir koma/dan)."""
    judul = lines[i].strip() if i < len(lines) else ''
    j = i + 1
    while j < len(lines) and (judul.endswith(',') or judul.endswith(' dan')):
        judul += ' ' + lines[j].strip()
        j += 1
    return judul, j


def bab_judul(lines, i):
    """Judul BAB: baris huruf kapital berikutnya."""
    bagian = []
    j = i
    while j < len(lines):
        s = lines[j].strip()
        if (not s or s != s.upper() or s.startswith(('Pasal', 'Bagian', 'Paragraf'))
                or PASAL.match(s)):
            break
        bagian.append(s)
        j += 1
    return ' '.join(bagian), j


def parse_badan(lines, doc_id):
    """Kembalikan (pembukaan_lines, daftar pasal)."""
    pembukaan, chunks = [], []
    bab = bagian = paragraf = None
    last = 0
    cur = None
    i = 0
    mulai = False
    while i < len(lines):
        s = lines[i]
        m = BAB.match(s)
        if m:
            judul, j = bab_judul(lines, i + 1)
            kecil = {'Dan', 'Di', 'Dengan', 'Untuk', 'Bagi', 'Atas', 'Yang', 'Pada', 'Dari', 'Atau'}
            judul = ' '.join(w.lower() if w in kecil else w for w in judul.title().split())
            bab = f'BAB {m.group(1)} — {judul}' if judul else f'BAB {m.group(1)}'
            bagian = paragraf = None
            mulai = True
            i = j
            continue
        m = BAGIAN.match(s)
        if m and mulai:
            judul, j = judul_lanjut(lines, i + 1)
            bagian = f'Bagian {m.group(1)} — {judul}'
            paragraf = None
            i = j
            continue
        m = PARAGRAF.match(s)
        if m and mulai:
            judul, j = judul_lanjut(lines, i + 1)
            paragraf = f'Paragraf {m.group(1)} — {judul}'
            i = j
            continue
        m = PASAL.match(s)
        if m and int(m.group(1)) == last + 1:
            last += 1
            cur = {'doc': doc_id, 'type': 'pasal', 'pasal': last, 'bab': bab,
                   'bagian': bagian, 'paragraf': paragraf, 'lines': []}
            chunks.append(cur)
            i += 1
            continue
        if cur is None:
            pembukaan.append(s)
        else:
            cur['lines'].append(s)
        i += 1
    return pembukaan, chunks


def potong_penutup(lines):
    for k, ln in enumerate(lines):
        if ln.strip().startswith('Agar setiap orang mengetahuinya'):
            return lines[:k]
    return lines


HDR = re.compile(r'^\s*(Ayat \(\d+\)|Huruf [a-z]|Angka \d+)\s*$')


def parse_penjelasan(lines):
    """Kembalikan {nomor_pasal: teks} tanpa 'Cukup jelas'."""
    hasil, last, cur = {}, 0, None
    buf = {}
    for s in lines:
        m = PASAL.match(s)
        if m and int(m.group(1)) == last + 1:
            last += 1
            cur = last
            buf[cur] = {'pending': [], 'out': []}
            continue
        if cur is None:
            continue
        t = s.strip()
        if not t or t.startswith('TAMBAHAN LEMBARAN NEGARA'):
            continue
        b = buf[cur]
        if HDR.match(t):
            if t.startswith('Ayat'):
                b['pending'] = [t]
            elif t.startswith('Huruf'):
                b['pending'] = [p for p in b['pending'] if p.startswith('Ayat')] + [t]
            else:
                b['pending'] = [p for p in b['pending'] if not p.startswith('Angka')] + [t]
            continue
        if t.startswith('Cukup jelas'):
            if b['pending']:
                b['pending'].pop()
            continue
        if b['pending']:
            b['out'].append('[' + ' '.join(b['pending']) + ']')
            b['pending'] = [p for p in b['pending'] if False]
        b['out'].append(t)
    for n, b in buf.items():
        teks = reflow(b['out']) if b['out'] else ''
        if teks:
            hasil[n] = teks
    return hasil


def baca(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        return f.read().splitlines()


def proses_uu(path):
    raw = baca(path)
    idx = next(i for i, l in enumerate(raw) if re.match(r'^\s*P E N J E L A S A N\s*$', l))
    badan_raw, pen_raw = raw[:idx], raw[idx:]
    pembukaan, pasal = parse_badan(bersih(badan_raw), 'uu-22-2009')
    for c in pasal:
        c['lines'] = potong_penutup(c['lines'])
    pen = bersih(pen_raw)
    k_umum = next(i for i, l in enumerate(pen) if l.strip().startswith('I. UMUM'))
    k_pasal = next(i for i, l in enumerate(pen) if l.strip().startswith('II. PASAL DEMI PASAL'))
    umum = reflow(pen[k_umum + 1:k_pasal])
    penj = parse_penjelasan(pen[k_pasal + 1:])
    return pembukaan, pasal, umum, penj, []


def proses_permen(path):
    raw = baca(path)
    idx = next(i for i, l in enumerate(raw) if LAMPIRAN.match(l))
    badan_raw, lamp_raw = raw[:idx], raw[idx:]
    pembukaan, pasal = parse_badan(bersih(badan_raw), 'permenhub-60-2019')
    for c in pasal:
        c['lines'] = potong_penutup(c['lines'])
    # Lampiran
    lamp = bersih(lamp_raw)
    bagian_lamp, cur = [], None
    for ln in lamp:
        m = LAMPIRAN.match(ln)
        if m:
            cur = {'nama': 'Lampiran ' + m.group(1), 'lines': []}
            bagian_lamp.append(cur)
            continue
        if cur is not None:
            cur['lines'].append(ln)
    return pembukaan, pasal, None, {}, bagian_lamp


NOISE = re.compile(r'^\s*(ttd\.?|BUDI KARYA SUMADI|MENTERI PERHUBUNGAN|REPUBLIK INDONESIA,?|'
                   r'Sesuai dengan aslinya|.*HUKUM,|B|UI HERPRIARSONO|JI HERPRIARSONO|O HUKUM,)\s*$')


def rapikan_lampiran(lines, perbaiki_spasi):
    out = []
    for ln in lines:
        if NOISE.match(ln):
            continue
        s = ln.strip()
        if not s:
            continue
        if perbaiki_spasi:
            s = re.sub(r'\b([A-Z]) ([a-z]{2,})', r'\1\2', s)
        out.append(s)
    return out


def main():
    keluar, uu_path, pm_path = sys.argv[1:4]
    docs = [
        {'id': 'uu-22-2009', 'jenis': 'Undang-Undang', 'nomor': '22', 'tahun': '2009',
         'judul': 'Lalu Lintas dan Angkutan Jalan', 'singkat': 'UU 22/2009',
         'status': 'Belum diverifikasi'},
        {'id': 'permenhub-60-2019', 'jenis': 'Peraturan Menteri Perhubungan', 'nomor': 'PM 60',
         'tahun': '2019',
         'judul': 'Penyelenggaraan Angkutan Barang dengan Kendaraan Bermotor di Jalan',
         'singkat': 'PM 60/2019', 'status': 'Belum diverifikasi'},
    ]
    chunks = []

    # --- UU ---
    pembukaan, pasal, umum, penj, _ = proses_uu(uu_path)
    chunks.append({'doc': 'uu-22-2009', 'type': 'pembukaan', 'label': 'Konsiderans (Menimbang, Mengingat)',
                   'text': reflow(pembukaan), 'bab': None, 'bagian': None, 'paragraf': None})
    chunks.append({'doc': 'uu-22-2009', 'type': 'penjelasan_umum', 'label': 'Penjelasan Umum',
                   'text': umum, 'bab': None, 'bagian': None, 'paragraf': None})
    for c in pasal:
        c['text'] = reflow(c.pop('lines'))
        c['penjelasan'] = penj.get(c['pasal'], '')
        c['label'] = f"Pasal {c['pasal']}"
        chunks.append(c)
    n_uu = len(pasal)

    # --- Permen ---
    pembukaan, pasal, _, _, lamp = proses_permen(pm_path)
    chunks.append({'doc': 'permenhub-60-2019', 'type': 'pembukaan',
                   'label': 'Konsiderans (Menimbang, Mengingat)', 'text': reflow(pembukaan),
                   'bab': None, 'bagian': None, 'paragraf': None})
    for c in pasal:
        c['text'] = reflow(c.pop('lines'))
        c['penjelasan'] = ''
        c['label'] = f"Pasal {c['pasal']}"
        chunks.append(c)
    n_pm = len(pasal)
    for L in lamp:
        garbled = L['nama'] == 'Lampiran IV'
        baris = rapikan_lampiran(L['lines'], garbled)
        for k in range(0, len(baris), 45):
            potong = baris[k:k + 45]
            bag = k // 45 + 1
            total = (len(baris) + 44) // 45
            label = L['nama'] + (f' (bagian {bag}/{total})' if total > 1 else '')
            chunks.append({'doc': 'permenhub-60-2019', 'type': 'lampiran', 'label': label,
                           'text': '\n'.join(potong), 'bab': None, 'bagian': None,
                           'paragraf': None, 'lowq': garbled})

    for i, c in enumerate(chunks):
        c['id'] = i
    data = {'docs': docs, 'chunks': chunks}
    with open(keluar, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    print('UU pasal:', n_uu, '| PM pasal:', n_pm, '| total potongan:', len(chunks))


if __name__ == '__main__':
    main()
