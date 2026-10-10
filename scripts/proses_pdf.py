#!/usr/bin/env python3
"""Proses semua PDF di folder pdf/ menjadi indeks pencarian per pasal (data/index.json).

- PDF yang sudah diproses (isi sama, dilihat dari sidik jari SHA-256) dilewati.
- PDF pindaian (gambar) otomatis di-OCR dengan tesseract.
- PDF yang dihapus dari pdf/ ikut dihapus dari indeks.
- Dokumen lama di indeks yang tidak berasal dari PDF (tanpa field "pdf") dibiarkan.
- Hasil ringkas ditulis ke data/laporan.md.

Pemakaian: python scripts/proses_pdf.py [--semua]   (--semua = paksa proses ulang semua PDF)
"""
import concurrent.futures as cf
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import pecah as P  # noqa: E402

PDF_DIR = ROOT / "pdf"
INDEKS = ROOT / "data" / "index.json"
LAPORAN = ROOT / "data" / "laporan.md"
PENGATURAN = PDF_DIR / "pengaturan.json"

JENIS = [  # (kunci tanpa spasi/tanda hubung, nama, singkatan)
    ("UNDANGUNDANG", "Undang-Undang", "UU"),
    ("PERATURANPEMERINTAH", "Peraturan Pemerintah", "PP"),
    ("PERATURANPRESIDEN", "Peraturan Presiden", "Perpres"),
    ("PERATURANMENTERIPERHUBUNGAN", "Peraturan Menteri Perhubungan", "PM"),
    ("PERATURANMENTERI", "Peraturan Menteri", "Permen"),
    ("PERATURANGUBERNUR", "Peraturan Gubernur", "Pergub"),
    ("PERATURANBUPATI", "Peraturan Bupati", "Perbup"),
    ("PERATURANWALIKOTA", "Peraturan Wali Kota", "Perwali"),
    ("PERATURANDAERAH", "Peraturan Daerah", "Perda"),
]
KECIL = {"dan", "di", "dengan", "untuk", "bagi", "atas", "yang", "pada", "dari", "atau", "ke", "dalam", "oleh"}


def jalan(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------- ekstraksi teks
def jumlah_halaman(pdf: Path) -> int:
    m = re.search(r"Pages:\s+(\d+)", jalan(["pdfinfo", str(pdf)]).stdout)
    return int(m.group(1)) if m else 0


def apakah_pindaian(pdf: Path, halaman: int) -> bool:
    """Pindaian = hampir tiap halaman berisi gambar penuh, atau teks sangat sedikit."""
    out = jalan(["pdfimages", "-list", str(pdf)]).stdout.splitlines()[2:]
    hal_gambar = {ln.split()[0] for ln in out if ln.split()}
    teks = jalan(["pdftotext", "-layout", str(pdf), "-"]).stdout
    huruf = len(re.findall(r"[A-Za-z]", teks))
    return (halaman and len(hal_gambar) >= 0.8 * halaman) or (halaman and huruf / halaman < 400)


def teks_langsung(pdf: Path):
    return jalan(["pdftotext", "-layout", str(pdf), "-"]).stdout.splitlines()


def bahasa_ocr() -> str:
    langs = jalan(["tesseract", "--list-langs"]).stdout.split()
    return "ind+eng" if "ind" in langs else "eng"


def teks_ocr(pdf: Path):
    lang = bahasa_ocr()
    with tempfile.TemporaryDirectory() as tmp:
        jalan(["pdftoppm", "-r", "220", "-png", str(pdf), f"{tmp}/p"])
        gambar = sorted(Path(tmp).glob("p-*.png"))

        def satu(g):
            jalan(["tesseract", str(g), str(g), "-l", lang, "--psm", "4"])
            return Path(str(g) + ".txt").read_text(encoding="utf-8", errors="replace")

        with cf.ThreadPoolExecutor(max_workers=2) as ex:
            hasil = list(ex.map(satu, gambar))
    teks = "\n".join(hasil)
    teks = re.sub(r"(?m)^\s*BAB\s*[|lI1]\s*$", "BAB I", teks)
    return teks.splitlines(), lang


def ocr_fix(t: str) -> str:
    t = re.sub(r"\bdanl\s*atau\b", "dan/atau", t)
    t = re.sub(r"(?<=\w)\s+,", ",", t)
    t = re.sub(r"(?<=[a-z])ch\b", "eh", t)
    t = re.sub(r"\bsc(?=[bdghklmnprstw])", "se", t)
    t = re.sub(r"(?<=[a-z])ct(?=[a-z])", "et", t)
    t = re.sub(r"([;:]) ([a-e])[,] ", r"\1\n\2. ", t)
    return t


# ---------------------------------------------------------------- metadata
def judul_cantik(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if s.isupper():
        s = " ".join(w.lower() if w.lower() in KECIL else w.capitalize() for w in s.split())
        s = s[:1].upper() + s[1:]
    return s


def baca_meta(lines, nama_berkas: str) -> dict:
    kepala = [ln for ln in lines[:90]]
    k_tentang = next((i for i, ln in enumerate(kepala) if re.match(r"^\s*TENTANG\s*$", ln)), 25)
    gabung = " ".join(kepala[:k_tentang + 1])
    rapat = re.sub(r"[\s\-]", "", gabung.upper())
    jenis = singk = None
    terbaik = 10 ** 9
    for kunci, nama, ab in JENIS:  # jenis yang muncul paling awal di kepala dokumen
        pos = rapat.find(kunci)
        if 0 <= pos < terbaik:
            terbaik, jenis, singk = pos, nama, ab
    m = re.search(r"NOMOR\s*([A-Z]{0,3}\s*\d+[A-Za-z/]*)\s*TAHUN\s*(\d{4})", gabung, re.I)
    nomor, tahun = (re.sub(r"\s+", " ", m.group(1)).strip(), m.group(2)) if m else (None, None)
    judul = None
    for i, ln in enumerate(kepala):
        if re.match(r"^\s*TENTANG\s*$", ln):
            bag = []
            for x in kepala[i + 1:i + 8]:
                if not x.strip() or re.match(r"^\s*(DENGAN RAHMAT|MENTERI|PRESIDEN|GUBERNUR|BUPATI|WALI ?KOTA)\b", x):
                    if bag:
                        break
                    continue
                bag.append(x.strip())
            judul = judul_cantik(" ".join(bag)) if bag else None
            break
    if not (jenis and nomor and tahun):
        return {"jenis": jenis or "Peraturan", "nomor": nomor or "?", "tahun": tahun or "?",
                "judul": judul or nama_berkas, "singkat": nama_berkas, "id": slug(nama_berkas), "_pasti": False}
    angka = re.sub(r"^[A-Z]+\s*", "", nomor)
    singkat = f"{nomor}/{tahun}" if re.match(r"[A-Z]", nomor) else f"{singk} {nomor}/{tahun}"
    return {"id": slug(f"{singk}-{angka}-{tahun}"), "jenis": jenis, "nomor": nomor, "tahun": tahun,
            "judul": judul or nama_berkas, "singkat": singkat, "_pasti": True}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


# ---------------------------------------------------------------- pemecahan
KUNCI_PEN = re.compile(r"^\s*P\s*E\s*N\s*J\s*E\s*L\s*A\s*S\s*A\s*N\s*$")
AKHIR = re.compile(r"^\s*(Ditetapkan|Disahkan) di\b")
LAMP = re.compile(r"^\s*LAMPIRAN\s*([IVXL]+)\s*$")


def sisip_pasal_1(badan):
    """Judul 'Pasal 1' sering hilang pada pindaian. Sisipkan bila kalimat definisi ditemukan."""
    if any(re.match(r"^\s*Pasal\s*1\s*$", l) for l in badan):
        return badan
    for i, l in enumerate(badan):
        if re.match(r"^\s*Dalam .{0,70}\bini\s+yang\s+dimaksud\s+dengan", l):
            return badan[:i] + ["", "Pasal 1"] + badan[i:]
    return badan


def pecah(lines, doc_id, ocr: bool):
    """Kembalikan (chunks, info). info berisi jumlah pasal, nomor hilang, dsb."""
    info = {"pasal": 0, "hilang": [], "lampiran": 0, "penjelasan": False, "mode": "pasal"}
    idx_pen = next((i for i, l in enumerate(lines) if KUNCI_PEN.match(l)), None)
    idx_akhir = next((i for i, l in enumerate(lines) if AKHIR.match(l)), None)
    mulai_cari = idx_akhir if idx_akhir is not None else 0
    idx_lamp = next((i for i in range(mulai_cari, len(lines)) if LAMP.match(lines[i])), None)
    batas = [x for x in (idx_pen, idx_lamp) if x is not None]
    akhir_badan = min(batas) if batas else len(lines)
    badan = lines[:akhir_badan]
    pen_lines = lines[idx_pen:] if idx_pen is not None and (idx_lamp is None or idx_pen < idx_lamp) else []
    lamp_lines = lines[idx_lamp:] if idx_lamp is not None else []

    badan = sisip_pasal_1(badan)
    pembukaan, pasal = P.parse_badan(P.bersih(badan), doc_id, gap=3)
    chunks = []
    if len(pasal) < 3:  # pola pasal tidak ketemu -> potong biasa
        info["mode"] = "teks"
        baris = [l.strip() for l in P.bersih(lines) if l.strip()]
        for k in range(0, len(baris), 40):
            chunks.append({"doc": doc_id, "type": "teks", "label": f"Bagian {k // 40 + 1}",
                           "text": "\n".join(baris[k:k + 40]), "bab": None, "bagian": None, "paragraf": None})
        return chunks, info

    for c in pasal:
        for j, l in enumerate(c["lines"]):
            if AKHIR.match(l):
                c["lines"] = c["lines"][:j]
                break
        c["lines"] = P.potong_penutup(c["lines"])
    nomor = [c["pasal"] for c in pasal]
    info["pasal"] = len(pasal)
    info["hilang"] = sorted(set(range(1, max(nomor) + 1)) - set(nomor))

    penj = {}
    umum = ""
    if pen_lines:
        pen = P.bersih(pen_lines)
        ku = next((i for i, l in enumerate(pen) if re.match(r"^\s*I\.\s*UMUM", l)), None)
        kp = next((i for i, l in enumerate(pen) if re.match(r"^\s*II\.\s*PASAL DEMI PASAL", l)), None)
        if kp is not None:
            penj = P.parse_penjelasan(pen[kp + 1:])
            if ku is not None and ku < kp:
                umum = P.reflow(pen[ku + 1:kp])
            info["penjelasan"] = True

    chunks.append({"doc": doc_id, "type": "pembukaan", "label": "Konsiderans (Menimbang, Mengingat)",
                   "text": P.reflow(pembukaan), "bab": None, "bagian": None, "paragraf": None})
    if umum:
        chunks.append({"doc": doc_id, "type": "penjelasan_umum", "label": "Penjelasan Umum", "text": umum,
                       "bab": None, "bagian": None, "paragraf": None})
    for c in pasal:
        c["text"] = P.reflow(c.pop("lines"))
        c["penjelasan"] = penj.get(c["pasal"], "")
        c["label"] = f"Pasal {c['pasal']}"
        chunks.append(c)

    bag, cur = [], None
    for ln in P.bersih(lamp_lines):
        m = LAMP.match(ln)
        if m:
            cur = {"nama": "Lampiran " + m.group(1), "lines": []}
            bag.append(cur)
            continue
        if cur is not None and ln.strip():
            cur["lines"].append(ln.strip())
    for L in bag:
        tot = (len(L["lines"]) + 44) // 45
        for k in range(0, len(L["lines"]), 45):
            lab = L["nama"] + (f" (bagian {k // 45 + 1}/{tot})" if tot > 1 else "")
            chunks.append({"doc": doc_id, "type": "lampiran", "label": lab, "text": "\n".join(L["lines"][k:k + 45]),
                           "bab": None, "bagian": None, "paragraf": None})
    info["lampiran"] = len(bag)
    return chunks, info


# ---------------------------------------------------------------- utama
def main():
    paksa = "--semua" in sys.argv
    PDF_DIR.mkdir(exist_ok=True)
    INDEKS.parent.mkdir(exist_ok=True)
    data = json.loads(INDEKS.read_text(encoding="utf-8")) if INDEKS.exists() else {"docs": [], "chunks": []}
    setelan = json.loads(PENGATURAN.read_text(encoding="utf-8")) if PENGATURAN.exists() else {}
    pdfs = sorted(p for p in PDF_DIR.glob("*.pdf"))
    nama_ada = {p.name for p in pdfs}
    laporan = ["# Laporan pemrosesan PDF", ""]

    # hapus dokumen yang PDF-nya sudah dihapus
    hapus = {d["id"] for d in data["docs"] if d.get("pdf") and d["pdf"] not in nama_ada}
    for d in data["docs"]:
        if d["id"] in hapus:
            laporan.append(f"- 🗑️ **{d['singkat']}** dihapus dari indeks (file `{d['pdf']}` sudah tidak ada).")
    data["docs"] = [d for d in data["docs"] if d["id"] not in hapus]
    data["chunks"] = [c for c in data["chunks"] if c["doc"] not in hapus]

    by_pdf = {d["pdf"]: d for d in data["docs"] if d.get("pdf")}
    ada_perubahan = bool(hapus)
    for pdf in pdfs:
        manual = next((d for d in data["docs"] if not d.get("pdf") and pdf.name in (
            d.get("berkas"), d["id"] + ".pdf", d["singkat"].replace("/", "-") + ".pdf",
            d["singkat"].replace("/", " ") + ".pdf")), None)
        if manual:
            laporan.append(f"- 📎 `{pdf.name}` dipakai sebagai PDF asli untuk **{manual['singkat']}** "
                           "(isi indeks yang sudah dikoreksi tidak diproses ulang).")
            continue
        s = sha(pdf)
        lama = by_pdf.get(pdf.name)
        if lama and lama.get("sha") == s and not paksa:
            laporan.append(f"- ⏭️ `{pdf.name}` tidak berubah, dilewati.")
            continue
        try:
            ada_perubahan = True
            ov = setelan.get(pdf.name, {})
            hal = jumlah_halaman(pdf)
            ocr = ov["ocr"] if "ocr" in ov else apakah_pindaian(pdf, hal)
            if ocr:
                lines, lang = teks_ocr(pdf)
            else:
                lines, lang = teks_langsung(pdf), None
            meta = baca_meta(lines, pdf.stem)
            for k in ("id", "jenis", "nomor", "tahun", "judul", "singkat", "status", "catatan"):
                if k in ov:
                    meta[k] = ov[k]
            chunks, info = pecah(lines, meta["id"], ocr)
            if ocr:
                for c in chunks:
                    c["text"] = ocr_fix(c["text"])
                    if c.get("penjelasan"):
                        c["penjelasan"] = ocr_fix(c["penjelasan"])
                    c["lowq"] = True
            sebelumnya = next((d for d in data["docs"] if d["id"] == meta["id"]), {})
            doc = {"id": meta["id"], "jenis": meta["jenis"], "nomor": meta["nomor"], "tahun": meta["tahun"],
                   "judul": meta["judul"], "singkat": meta["singkat"],
                   "status": meta.get("status") or sebelumnya.get("status", "Belum diverifikasi"),
                   "pdf": pdf.name, "sha": s}
            cat = meta.get("catatan") or ("PDF hasil pindaian (OCR); mungkin ada salah ketik." if ocr else "")
            if cat:
                doc["catatan"] = cat
            ganti = {d["id"] for d in data["docs"] if d["id"] == meta["id"] or d["singkat"] == meta["singkat"]}
            data["docs"] = [d for d in data["docs"] if d["id"] not in ganti] + [doc]
            data["chunks"] = [c for c in data["chunks"] if c["doc"] not in ganti] + chunks
            baris = [f"- ✅ **{doc['singkat']}** — {doc['judul']} (`{pdf.name}`, {hal} hlm, "
                     f"{'OCR ' + lang if ocr else 'teks langsung'})"]
            if info["mode"] == "teks":
                baris.append("  - ⚠️ Pola 'Pasal N' tidak ditemukan; dokumen dipotong per 40 baris. Cek hasilnya.")
            else:
                baris.append(f"  - {info['pasal']} pasal, {info['lampiran']} lampiran"
                             + (", ada penjelasan" if info["penjelasan"] else ""))
                if info["hilang"]:
                    baris.append(f"  - ⚠️ Nomor pasal tidak terdeteksi (isinya menyatu dengan pasal sebelumnya): "
                                 f"{', '.join(map(str, info['hilang']))}")
            if not meta.get("_pasti", True):
                baris.append("  - ⚠️ Nomor/tahun/jenis tidak terbaca otomatis. Isi lewat `pdf/pengaturan.json`.")
            laporan += baris
        except Exception as e:  # noqa: BLE001
            laporan.append(f"- ❌ `{pdf.name}` gagal diproses: {e}")

    for i, c in enumerate(data["chunks"]):
        c["id"] = i
    if ada_perubahan or not INDEKS.exists():
        INDEKS.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    laporan.append("")
    laporan.append(f"Total: {len(data['docs'])} dokumen, {len(data['chunks'])} potongan.")
    LAPORAN.write_text("\n".join(laporan) + "\n", encoding="utf-8")
    print("\n".join(laporan))


if __name__ == "__main__":
    main()
