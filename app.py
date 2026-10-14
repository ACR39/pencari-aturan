"""Cari Peraturan — pencarian kata kunci per pasal + ringkasan. Jalankan: streamlit run app.py"""
import html
import json
import math
import re
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Cari Peraturan", page_icon="🔎", layout="centered",
                   initial_sidebar_state="expanded")

INDEKS = Path(__file__).parent / "data" / "index.json"
PDF_DIR = Path(__file__).parent / "pdf"
WORD = re.compile(r"[A-Za-zÀ-ÿ0-9]+")
STOP = set("yang dan di ke dari untuk dengan pada atau adalah itu ini dalam oleh bagi atas serta sebagai juga tidak dapat harus wajib".split())
SUFFIX = ("kan", "an", "i", "nya", "lah", "kah")
PREFIX = ("meng", "meny", "mem", "men", "me", "peng", "peny", "pem", "pen", "pe",
          "ber", "ter", "per", "di", "ke", "se")


def stem(w: str) -> str:
    w = w.lower()
    for s in SUFFIX:
        if len(w) > len(s) + 3 and w.endswith(s):
            w = w[: -len(s)]
            break
    for p in PREFIX:
        if len(w) > len(p) + 3 and w.startswith(p):
            w = w[len(p):]
            break
    return w


def terms(q: str):
    out = []
    for x in WORD.findall(q.lower()):
        if len(x) > 1 and x not in STOP:
            s = stem(x)
            if s not in out:
                out.append(s)
    return out


@st.cache_data
def muat():
    d = json.loads(INDEKS.read_text(encoding="utf-8"))
    df = {}
    for c in d["chunks"]:
        teks = " ".join(filter(None, [c["label"], c.get("bab"), c.get("bagian"),
                                      c.get("paragraf"), c["text"], c.get("penjelasan")]))
        c["_tf"] = {}
        for w in WORD.findall(teks):
            s = stem(w)
            c["_tf"][s] = c["_tf"].get(s, 0) + 1
        head = " ".join(filter(None, [c.get("bab"), c.get("bagian"), c.get("paragraf")]))
        c["_head"] = {stem(w) for w in WORD.findall(head)}
        c["_low"] = teks.lower()
        for t in c["_tf"]:
            df[t] = df.get(t, 0) + 1
    return d, df


DATA, DF = muat()


def urutan_hirarki(d):
    """Urutan menurut hierarki peraturan perundang-undangan, lalu jenis, tahun, nomor."""
    j = (d.get("jenis") or "").lower()
    if "undang-undang" in j or "perpu" in j:
        r = 1
    elif "pemerintah" in j and "daerah" not in j and "menteri" not in j:
        r = 2
    elif "presiden" in j or "perpres" in j:
        r = 3
    elif "menteri" in j or "kepala" in j or "badan" in j:
        r = 4
    elif "provinsi" in j or "gubernur" in j:
        r = 5
    elif "daerah" in j or "kabupaten" in j or "kota" in j or "bupati" in j or "walikota" in j:
        r = 6
    else:
        r = 9
    m = re.search(r"\d+", str(d.get("nomor") or ""))
    th = str(d.get("tahun") or "0")
    return (r, j, int(th) if th.isdigit() else 0, int(m.group()) if m else 0)


DOCS = {d["id"]: d for d in sorted(DATA["docs"], key=urutan_hirarki)}
st.session_state.setdefault("latar", True)   # gambar latar menyala secara bawaan

# Status tiap peraturan dibaca dari data/status.json (satu tempat untuk semua dokumen).
STATUS_BERKAS = Path(__file__).parent / "data" / "status.json"
try:
    for _id, _v in json.loads(STATUS_BERKAS.read_text(encoding="utf-8")).items():
        if _id in DOCS and isinstance(_v, dict):
            DOCS[_id]["status"] = _v.get("status") or DOCS[_id].get("status", "Belum diverifikasi")
            DOCS[_id]["status_ket"] = _v.get("keterangan", "")
except (OSError, ValueError):
    pass
KELAS_STATUS = {"berlaku": "ok", "diubah": "ubah", "dicabut": "cabut"}


def lencana_status(d) -> str:
    st_ = d.get("status") or "Belum diverifikasi"
    kelas = KELAS_STATUS.get(st_.split()[0].lower(), "belum")
    tip = html.escape(d.get("status_ket") or "")
    return f'<span class="stat {kelas}" title="{tip}">{html.escape(st_)}</span>'



def berkas_pdf(doc):
    """Path PDF asli untuk satu dokumen, atau None bila tidak ada di folder pdf/."""
    calon = [doc.get("berkas"), doc.get("pdf"), doc["id"] + ".pdf",
             doc["singkat"].replace("/", "-") + ".pdf", doc["singkat"].replace("/", " ") + ".pdf"]
    for nama in calon:
        if nama and (PDF_DIR / nama).is_file():
            return PDF_DIR / nama
    return None


@st.cache_data(show_spinner=False)
def baca_pdf(path: str) -> bytes:
    return Path(path).read_bytes()


def tombol_unduh(doc_id, kunci, label=None):
    p = berkas_pdf(DOCS[doc_id])
    if p:
        st.download_button(label or f"⬇ PDF asli · {DOCS[doc_id]['singkat']}", data=baca_pdf(str(p)),
                           file_name=p.name, mime="application/pdf", key=f"{kunci}_{doc_id}",
                           use_container_width=True)
N = len(DATA["chunks"])


def cari(q: str, doc_ids):
    ts = terms(q)
    if not ts:
        return ts, []
    frasa = q.strip().lower()
    hits = []
    for c in DATA["chunks"]:
        if c["doc"] not in doc_ids:
            continue
        s, m = 0.0, 0
        for t in ts:
            f = c["_tf"].get(t, 0)
            if f:
                m += 1
                idf = math.log(1 + N / DF.get(t, 1))
                s += idf * (f * 2.2 / (f + 1.2)) + (idf * 0.6 if t in c["_head"] else 0)
        if not m:
            continue
        s *= (0.4 + 0.6 * m / len(ts)) * (1.5 if m == len(ts) else 1)
        if len(ts) > 1 and frasa in c["_low"]:
            s *= 1.6
        if c["type"] == "lampiran":
            s *= 0.8
        hits.append((s, c))
    hits.sort(key=lambda x: -x[0])
    return ts, [c for _, c in hits]


def potong(t: str, ts, maks: int) -> str:
    if len(t) <= maks:
        return t
    pos = 0
    for m in WORD.finditer(t):
        if stem(m.group()) in ts:
            pos = m.start()
            break
    a = max(0, pos - 120)
    return ("… " if a else "") + t[a:a + maks] + (" …" if a + maks < len(t) else "")


def sorot(t: str, ts) -> str:
    h = WORD.sub(lambda m: f"<mark>{m.group()}</mark>" if stem(m.group()) in ts else m.group(),
                 html.escape(t))
    return h.replace("$", "&#36;").replace("\n", "<br>")


def rujuk(c) -> str:
    return f"{DOCS[c['doc']]['singkat']} · {c['label']}"


def ringkas_llm(q, ts, hits):
    """Ringkasan lewat gateway/API apa pun. Atur di Secrets:
    API_FORMAT = "openai" (default, /chat/completions) atau "anthropic" (/v1/messages)
    API_BASE_URL, API_KEY, API_MODEL
    """
    import urllib.request

    kutipan = "\n\n".join(
        f"[{rujuk(c)}]\n{potong(c['text'], ts, 600)}"
        + (f"\nPenjelasan: {potong(c['penjelasan'], ts, 200)}" if c.get("penjelasan") else "")
        for c in hits[:6])
    prompt = (
        f'Kamu asisten hukum. Berdasarkan HANYA kutipan peraturan berikut, ringkas dalam bahasa Indonesia '
        f'(maks 120 kata, 3–5 poin pendek) jawaban atas kata kunci: "{q}". Setiap poin wajib menyebut sumbernya '
        f'persis seperti penanda di kurung siku, mis. (UU 22/2009 · Pasal 76). Jangan menambah hal yang tidak ada '
        f'di kutipan; jika kutipan tidak menjawab, katakan begitu.\n\nKUTIPAN:\n{kutipan}')
    fmt = st.secrets.get("API_FORMAT", "openai").lower()
    base = st.secrets["API_BASE_URL"].rstrip("/")
    key = st.secrets["API_KEY"]
    model = st.secrets["API_MODEL"]
    if fmt == "anthropic":
        url = base + ("/messages" if base.endswith("/v1") else "/v1/messages")
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        body = {"model": model, "max_tokens": 500, "messages": [{"role": "user", "content": prompt}]}
    else:
        url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
        headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
        body = {"model": model, "max_tokens": 500, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(url, json.dumps(body).encode(), headers, method="POST")
    with urllib.request.urlopen(req, timeout=int(st.secrets.get("API_TIMEOUT", 150))) as r:
        j = json.loads(r.read())
    return j["content"][0]["text"] if fmt == "anthropic" else j["choices"][0]["message"]["content"]


WARNA = ["#0b8a82", "#e12885", "#3b6fd1", "#7a4fc2", "#d08a00"]
WARNA_DOC = {k: WARNA[i % len(WARNA)] for i, k in enumerate(DOCS)}

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
:root{--kertas:#f5f1e8;--kartu:#fffdf8;--tinta:#1f2430;--redup:#68707e;--garis:#e0d8c6;--aksen:#17445c;--aksen2:#0f2f41}
html,body,[class*="css"],.stApp{font-family:'IBM Plex Sans',system-ui,sans-serif}
.stApp{background:var(--kertas);color:var(--tinta)}
#MainMenu,footer{visibility:hidden}
header[data-testid="stHeader"]{background:transparent}
section[data-testid="stSidebar"]{background:#ece6d6;border-right:1px solid var(--garis)}
section[data-testid="stSidebar"] h2{font:700 20px/1.2 'Source Serif 4',Georgia,serif;color:var(--aksen2)}
.block-container{max-width:860px;padding-top:1.2rem;padding-bottom:4rem}
.hero{background:linear-gradient(135deg,var(--aksen2),var(--aksen));color:#f4efe2;border-radius:16px;padding:30px 30px 26px;margin-bottom:22px;position:relative;overflow:hidden}
.hero:after{content:"§";position:absolute;right:18px;top:-36px;font:700 190px/1 'Source Serif 4',serif;color:rgba(255,255,255,.07)}
.hero .eyebrow{letter-spacing:.14em;text-transform:uppercase;font-size:12px;opacity:.75;margin:0 0 8px}
.hero h1{font:700 34px/1.15 'Source Serif 4',Georgia,serif;margin:0 0 8px;color:#fff;padding:0}
.hero p{margin:0;opacity:.85;max-width:560px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}
.stats span{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.18);border-radius:99px;padding:4px 14px;font-size:13px}
div[data-testid="stTextInput"] input{font-size:17px;padding:14px 16px;border-radius:12px;border:1.5px solid var(--garis);background:var(--kartu);color:var(--tinta)}
div[data-testid="stTextInput"] input:focus{border-color:var(--aksen);box-shadow:0 0 0 3px rgba(23,68,92,.15)}
div[data-testid="stTextInput"] label p{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--redup);font-weight:600}
.stButton>button{border-radius:10px;border:1px solid var(--aksen);background:var(--aksen);color:#fff;font-weight:500;padding:.5rem 1.1rem}
.stButton>button:hover{background:var(--aksen2);border-color:var(--aksen2);color:#fff}
.ringkas{background:var(--kartu);border:1px solid var(--garis);border-left:5px solid var(--aksen);border-radius:12px;padding:16px 20px;margin:18px 0 8px}
.ringkas .lbl{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--aksen);font-weight:600;margin-bottom:6px}
.ringkas .angka{font:700 30px/1 'Source Serif 4',serif;color:var(--aksen);margin-right:6px}
.ringkas p{margin:6px 0 0;line-height:1.55}
.bar{display:flex;height:8px;border-radius:99px;overflow:hidden;margin:12px 0 4px;background:var(--garis)}
.bar i{display:block;height:100%}
.legenda{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--redup)}
.legenda b{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}
.kartu{background:var(--kartu);border:1px solid var(--garis);border-radius:14px;padding:18px 22px;margin:14px 0;box-shadow:0 1px 0 rgba(0,0,0,.02),0 8px 22px -14px rgba(23,40,60,.28)}
.kartu .atas{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.kartu .lencana{color:#fff;font-size:11.5px;font-weight:600;letter-spacing:.04em;padding:3px 10px;border-radius:99px}
.kartu .nomor{font:700 24px/1.2 'Source Serif 4',Georgia,serif;margin:6px 0 2px;color:var(--tinta)}
.kartu .jejak{font-size:12.5px;color:var(--redup);line-height:1.45;margin-bottom:10px}
.kartu .isi{font:400 16px/1.7 'Source Serif 4',Georgia,serif;overflow-wrap:anywhere}
.kartu .pen{margin-top:12px;padding:10px 14px;background:#f1ece0;border-radius:8px;font-size:13.5px;line-height:1.55;color:#4a5160;overflow-wrap:anywhere}
.kartu .pen summary{cursor:pointer;font-weight:600;color:var(--aksen);margin-bottom:6px}
.kartu .pen .tag{color:var(--aksen);font-weight:600}
.kartu .pen b{color:var(--aksen)}
.kartu .catatan{margin-top:8px;font-size:12px;color:var(--redup)}
.kartu mark{background:#ffe08a;color:#3a2b00;padding:0 2px;border-radius:3px}
.kosong{text-align:center;color:var(--redup);padding:34px 0}
.catfoot{font-size:12.5px;color:var(--redup);border-top:1px solid var(--garis);padding-top:14px;margin-top:28px}
div[data-testid="stMultiSelect"] span[data-baseweb="tag"]{background:var(--aksen);color:#fff;border-radius:99px}
button[data-baseweb="tab"] p{font-weight:600}
.butir{display:flex;gap:.55em;margin:.18em 0 .18em calc(var(--lv,0) * 1.7em)}
.butir .mk{flex:0 0 auto;min-width:1.9em;text-align:right;color:var(--redup)}
.butir .tx{flex:1 1 auto;min-width:0}
.butir.tanpa .tx{margin-left:0}
.kartu .pen .butir .mk{min-width:1.5em}
@media(max-width:640px){.hero{padding:22px 18px}.hero h1{font-size:27px}.kartu{padding:15px 16px}}
</style>""", unsafe_allow_html=True)


# ================= TEMA TURKUOIS + MERAH MUDA =================
ASET = Path(__file__).parent / "assets"


@st.cache_resource(show_spinner=False)
def gambar_b64(nama: str) -> str:
    import base64
    try:
        return base64.b64encode((ASET / nama).read_bytes()).decode()
    except OSError:
        return ""


st.markdown("""<style>
:root{--kertas:#eefafa;--kartu:#ffffff;--tinta:#17323a;--redup:#527a80;--garis:#b9e3de;--aksen:#0b8a82;--aksen2:#086a64;--pink:#e12885;--pinkink:#b0176b}
.stApp{background:radial-gradient(circle at 92% -5%,rgba(57,197,187,.28),transparent 42%),radial-gradient(circle at -5% 105%,rgba(225,40,133,.10),transparent 38%),var(--kertas);background-attachment:fixed}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#dcf4f1,#c9efea);border-right:1px solid var(--garis)}
section[data-testid="stSidebar"] h2{color:var(--aksen2)}
.hero{background:linear-gradient(135deg,#086a64,#0b8a82 55%,#17a89e);border-top:4px solid #39c5bb;box-shadow:0 8px 26px -10px rgba(11,138,130,.45)}
.hero:after{color:rgba(255,255,255,.09)}
.hero .stats span{background:rgba(255,255,255,.16);border-color:rgba(255,255,255,.28)}
.eq{display:flex;gap:3px;align-items:flex-end;height:26px;margin:18px 0 -6px;overflow:hidden}
.eq i{flex:1 1 0;min-width:2px;height:100%;background:linear-gradient(#ff7ab8,#7ff0e6);border-radius:2px;transform-origin:bottom;transform:scaleY(var(--hi));animation:eq 1.4s ease-in-out infinite;animation-delay:var(--d)}
@keyframes eq{0%,100%{transform:scaleY(var(--lo))}50%{transform:scaleY(var(--hi))}}
@media (prefers-reduced-motion:reduce){.eq i{animation:none}}
div[data-testid="stTextInput"] input:focus{border-color:var(--aksen);box-shadow:0 0 0 3px rgba(11,138,130,.18)}
.stButton>button{background:linear-gradient(135deg,#0b8a82,#17a89e);border-color:transparent}
.stButton>button:hover{background:linear-gradient(135deg,#086a64,#0b8a82);color:#fff}
button[data-baseweb="tab"][aria-selected="true"] p{color:var(--pinkink)}
div[data-baseweb="tab-highlight"]{background:var(--pink)!important}
div[data-testid="stMultiSelect"] span[data-baseweb="tag"]{background:var(--aksen)}
.ringkas{border-left-color:var(--pink)}
.ringkas .lbl,.ringkas .angka{color:var(--pinkink)}
.kartu{box-shadow:0 1px 0 rgba(0,0,0,.02),0 8px 22px -14px rgba(11,138,130,.4)}
.kartu .pen{background:#e9f8f6;color:#2f5a60}
.kartu .pen summary,.kartu .pen .tag,.kartu .pen b{color:var(--aksen2)}
.kartu mark{background:#ffd3e8;color:#5a0c35}
.catfoot{color:var(--aksen)}
.catfoot:before{content:"\\266A  "}
.stat{font-size:11.5px;font-weight:600;padding:2px 9px;border-radius:99px;border:1px solid}
.stat.ok{background:#dff6e8;color:#14663a;border-color:#a8dfc0}
.stat.ubah{background:#fff1d6;color:#8a5200;border-color:#f0cf8f}
.stat.cabut{background:#fde3e3;color:#a11d1d;border-color:#f3b3b3}
.stat.belum{background:#eef1f3;color:#5a6b73;border-color:#d3dce1}
img.maskot{width:100%;aspect-ratio:5/4;object-fit:cover;border-radius:14px;border:1px solid var(--garis);box-shadow:0 4px 16px rgba(11,138,130,.18);margin-top:14px;pointer-events:none}
@media (max-width:820px){img.maskot{display:none}}
</style>""", unsafe_allow_html=True)



MARKER = re.compile(r"^(\(\d+\)|\d+\)|[a-z]\)|[a-z]\.|\d+\.)\s+(.*)$", re.S)


def jenis_marker(m: str) -> str:
    if m.startswith("("):
        return "A"          # (1)
    if m.endswith(")"):
        return "P"          # 1) atau a)
    return "L" if m[0].isalpha() else "N"   # a.  /  1.


def isi_html(teks: str, ts) -> str:
    """Ubah teks pasal menjadi butir bertingkat dengan lekukan menggantung."""
    tumpukan, keluar = [], []
    for baris in teks.split("\n"):
        if not baris.strip():
            continue
        m = MARKER.match(baris.strip())
        if m:
            k = jenis_marker(m.group(1))
            if k in tumpukan:
                del tumpukan[tumpukan.index(k) + 1:]
            else:
                tumpukan.append(k)
            lv = tumpukan.index(k)
            keluar.append(f'<div class="butir" style="--lv:{lv}"><span class="mk">{html.escape(m.group(1))}</span>'
                          f'<span class="tx">{sorot(m.group(2), ts)}</span></div>')
        else:
            lv = max(len(tumpukan) - 1, 0)
            b = baris.strip()
            tag = re.match(r"^\[((?:Ayat|Huruf|Angka)[^\]]*)\]\s*(.*)$", b)
            if tag:
                keluar.append(f'<div class="butir tanpa" style="--lv:0"><span class="tx"><b class="tag">{html.escape(tag.group(1))}</b> '
                              f'{sorot(tag.group(2), ts)}</span></div>')
            else:
                keluar.append(f'<div class="butir tanpa" style="--lv:{lv}"><span class="tx">{sorot(b, ts)}</span></div>')
    return "".join(keluar)


def kartu_html(c, ts, penuh=False, buka_pen=False):
    d = DOCS[c["doc"]]
    warna = WARNA_DOC[c["doc"]]
    jejak = " › ".join(html.escape(x) for x in filter(None, [c.get("bab"), c.get("bagian"), c.get("paragraf")]))
    isi = c["text"] if penuh else potong(c["text"], ts, 700)
    pen_t = c.get("penjelasan") or ""
    pen = ""
    if pen_t:
        pen_t = re.sub(r"\s*(\[(?:Ayat|Huruf|Angka)[^\]]*\])", lambda m: "\n" + m.group(1), pen_t).strip()
        cocok = bool(set(ts) & {stem(w) for w in WORD.findall(pen_t)})
        buka = " open" if (buka_pen or cocok) else ""
        pen = (f'<details class="pen"{buka}><summary>Penjelasan</summary>'
               f'{isi_html(pen_t if penuh else potong(pen_t, ts, 400), ts)}</details>')
    cat = ('<div class="catatan">Teks ini hasil pindaian (OCR) dan mungkin ada salah ketik; cek ke dokumen asli.</div>'
           if c.get("lowq") else "")
    return (f'<div class="kartu" style="border-top:4px solid {warna}">'
            f'<div class="atas"><span class="lencana" style="background:{warna}">{html.escape(d["singkat"])}</span>'
            f'<span class="jejak" style="margin:0">{html.escape(d["jenis"])} {html.escape(d["nomor"])}/{html.escape(d["tahun"])}</span>'
            f'{lencana_status(d)}</div>'
            f'<div class="nomor">{html.escape(c["label"])}</div><div class="jejak">{jejak}</div>'
            f'<div class="isi">{isi_html(isi, ts)}</div>{pen}{cat}'
            + (f'<div class="catatan">Status: {html.escape(d["status_ket"])}</div>' if d.get("status_ket") else "")
            + '</div>')


def baca_dokumen():
    """Pembaca dokumen: pilih dokumen, bagian (BAB), dan lompat ke pasal tertentu."""
    pilihan = list(DOCS)
    k = st.selectbox("Dokumen", pilihan, format_func=lambda i: f"{DOCS[i]['singkat']} — {DOCS[i]['judul']}",
                     key="baca_doc")
    d = DOCS[k]
    potongan = [c for c in DATA["chunks"] if c["doc"] == k]
    bab_urut = []
    for c in potongan:
        if c.get("bab") and c["bab"] not in bab_urut:
            bab_urut.append(c["bab"])
    jenis_ada = {c["type"] for c in potongan}
    daftar = ["Semua bagian"]
    if "pembukaan" in jenis_ada:
        daftar.append("Konsiderans")
    if "penjelasan_umum" in jenis_ada:
        daftar.append("Penjelasan Umum")
    daftar += bab_urut
    if "lampiran" in jenis_ada:
        daftar.append("Lampiran")
    if "teks" in jenis_ada:
        daftar.append("Teks")
    c1, c2 = st.columns([3, 1])
    bagian = c1.selectbox("Bagian", daftar, key=f"baca_bagian_{k}")
    ada_pen = any(c.get("penjelasan") for c in potongan)
    buka_pen = st.checkbox("Buka semua penjelasan", value=False, key=f"baca_pen_{k}") if ada_pen else False
    nomor_pasal = [c["pasal"] for c in potongan if c["type"] == "pasal"]
    lompat = c2.number_input("Ke pasal", min_value=0, max_value=max(nomor_pasal or [0]), value=0, step=1,
                             key=f"baca_lompat_{k}", help="0 = tidak melompat")

    if bagian == "Semua bagian":
        item = potongan
    elif bagian == "Konsiderans":
        item = [c for c in potongan if c["type"] == "pembukaan"]
    elif bagian == "Penjelasan Umum":
        item = [c for c in potongan if c["type"] == "penjelasan_umum"]
    elif bagian == "Lampiran":
        item = [c for c in potongan if c["type"] == "lampiran"]
    elif bagian == "Teks":
        item = [c for c in potongan if c["type"] == "teks"]
    else:
        item = [c for c in potongan if c.get("bab") == bagian]

    per = 8
    total = max(1, (len(item) + per - 1) // per)
    mulai = 0
    if lompat:
        idx = next((i for i, c in enumerate(item) if c["type"] == "pasal" and c["pasal"] == lompat), None)
        if idx is None:
            st.info(f"Pasal {lompat} tidak ada pada bagian ini. Pilih 'Semua bagian' untuk mencarinya.")
        else:
            mulai = idx
    else:
        hal = st.number_input("Halaman", min_value=1, max_value=total, value=1, step=1,
                              key=f"baca_hal_{k}_{bagian}") if total > 1 else 1
        mulai = (hal - 1) * per
    cap = f"{d['jenis']} {d['nomor']}/{d['tahun']} · {len(item)} bagian"
    if not lompat:
        cap += f" · halaman {mulai // per + 1} dari {total}"
    st.caption(cap)
    tombol_unduh(k, "baca", "⬇ Unduh PDF asli")
    for c in item[mulai:mulai + per]:
        st.markdown(kartu_html(c, [], penuh=True, buka_pen=buka_pen), unsafe_allow_html=True)

def equalizer(n=56):
    out = []
    for i in range(n):
        r = abs(math.sin(i * 12.9898) * 43758.5453) % 1
        r2 = abs(math.sin(i * 78.233) * 12345.678) % 1
        out.append(f'<i style="--lo:{.15 + r * .15:.2f};--hi:{.55 + r2 * .45:.2f};--d:-{i * .11:.2f}s"></i>')
    return '<div class="eq" aria-hidden="true">' + "".join(out) + "</div>"


st.markdown(
    f'<div class="hero"><p class="eyebrow">Basis pengetahuan hukum</p><h1>Cari Peraturan</h1>'
    f'<p>Telusuri kata kunci langsung ke pasal yang tepat, lengkap dengan penjelasan dan ringkasan.</p>'
    f'<div class="stats"><span>{len(DOCS)} peraturan</span><span>{N} potongan pasal</span></div>{equalizer()}</div>',
    unsafe_allow_html=True)

tab_cari, tab_baca = st.tabs(["🔎 Cari kata kunci", "📖 Baca dokumen"])
with tab_baca:
    baca_dokumen()
with tab_cari:
    q = st.text_input("Kata kunci", placeholder="mis. denda administratif, izin angkutan barang")
    with st.sidebar:
        st.markdown("## Dokumen")
        st.caption("Pilih peraturan yang ingin dicari.")
        if "dipilih" not in st.session_state:
            st.session_state["dipilih"] = set(DOCS)

        def atur_semua(nilai: bool):
            st.session_state["dipilih"] = set(DOCS) if nilai else set()
            for kk in DOCS:
                st.session_state[f"doc_{kk}"] = nilai

        def ubah(k):
            if st.session_state.get(f"doc_{k}"):
                st.session_state["dipilih"].add(k)
            else:
                st.session_state["dipilih"].discard(k)

        b1, b2 = st.columns(2)
        b1.button("Pilih semua", on_click=atur_semua, args=(True,), use_container_width=True, key="pilih_semua")
        b2.button("Hapus semua", on_click=atur_semua, args=(False,), use_container_width=True, key="hapus_semua")
        saring = (st.text_input("Saring daftar", placeholder="ketik nama/nomor", label_visibility="collapsed")
                  if len(DOCS) > 6 else "")
        for k, d in DOCS.items():
            label = f"{d['singkat']} — {d['judul']}"
            if saring and saring.lower() not in label.lower():
                continue
            kunci = f"doc_{k}"
            if kunci not in st.session_state:
                st.session_state[kunci] = k in st.session_state["dipilih"]
            st.checkbox(label, key=kunci, on_change=ubah, args=(k,))
        pilih = [k for k in DOCS if k in st.session_state["dipilih"]]
        if not pilih:
            st.warning("Pilih minimal satu dokumen.")
        st.caption(f"{len(pilih)} dari {len(DOCS)} dokumen aktif")
        ada_pdf = [k for k, d in DOCS.items() if berkas_pdf(d)]
        if ada_pdf:
            with st.expander("⬇ Unduh PDF asli"):
                pdf_pilih = st.selectbox("Dokumen", ada_pdf, format_func=lambda k: DOCS[k]["singkat"],
                                         label_visibility="collapsed")
                tombol_unduh(pdf_pilih, "sb", "Unduh PDF")
        for d in DOCS.values():
            if d.get("catatan"):
                st.caption(f"ℹ️ {d['singkat']}: {d['catatan']}")
        st.toggle("Gambar sebagai latar", key="latar", help="Matikan untuk menampilkan gambar kecil di panel ini.")
        if not st.session_state.get("latar") and gambar_b64("mascot.jpg"):
            st.markdown(f'<img class="maskot" alt="" src="data:image/jpeg;base64,{gambar_b64("mascot.jpg")}">',
                        unsafe_allow_html=True)

    if q:
        ts, hits = cari(q, set(pilih))
        if not ts:
            st.markdown('<div class="kosong">Ketik kata kunci yang lebih spesifik.</div>', unsafe_allow_html=True)
        elif not hits:
            st.markdown(f'<div class="kosong">Tidak ada hasil untuk “{html.escape(q)}”.<br>Coba kata dasar atau sinonim.</div>',
                        unsafe_allow_html=True)
        else:
            per = {}
            for c in hits:
                per[c["doc"]] = per.get(c["doc"], 0) + 1
            bar = "".join(f'<i style="width:{v / len(hits) * 100:.1f}%;background:{WARNA_DOC[k]}"></i>' for k, v in per.items())
            leg = "".join(f'<span><b style="background:{WARNA_DOC[k]}"></b>{html.escape(DOCS[k]["singkat"])}: {v}</span>'
                          for k, v in per.items())
            top = ", ".join(html.escape(rujuk(c)) for c in hits[:3])
            st.markdown(
                f'<div class="ringkas"><div class="lbl">Ringkasan</div>'
                f'<span class="angka">{len(hits)}</span>bagian cocok'
                f'<div class="bar">{bar}</div><div class="legenda">{leg}</div>'
                f'<p>Paling relevan: {top}.</p></div>', unsafe_allow_html=True)
            unduh = [k for k in per if berkas_pdf(DOCS[k])]
            for i in range(0, len(unduh), 3):
                kol = st.columns(3)
                for kk, k in zip(kol, unduh[i:i + 3]):
                    with kk:
                        tombol_unduh(k, "hasil")
            if all(k in st.secrets for k in ("API_BASE_URL", "API_KEY", "API_MODEL")):
                if st.button("✨ Ringkas isinya dengan AI"):
                    with st.spinner("Meringkas…"):
                        try:
                            with st.container(border=True):
                                st.markdown(ringkas_llm(q, ts, hits))
                        except Exception as e:  # noqa: BLE001
                            st.error(f"Ringkasan gagal: {e}. Jika \"timed out\", gateway/model terlalu lambat: coba model yang lebih cepat di API_MODEL atau naikkan API_TIMEOUT di Secrets.")
            tampil = st.session_state.get("tampil", 10)
            for c in hits[:tampil]:
                st.markdown(kartu_html(c, ts), unsafe_allow_html=True)
            if len(hits) > tampil:
                if st.button(f"Tampilkan lebih banyak ({len(hits) - tampil})"):
                    st.session_state["tampil"] = tampil + 10
                    st.rerun()


st.markdown(
    '<div class="catfoot">'
    + ("Status berlaku/diubah/dicabut belum diverifikasi: "
       + ", ".join(html.escape(d["singkat"]) for d in DOCS.values() if (d.get("status") or "Belum diverifikasi") == "Belum diverifikasi")
       + ". " if any((d.get("status") or "Belum diverifikasi") == "Belum diverifikasi" for d in DOCS.values()) else "")
    + "Periksa perubahan terbaru sebelum dijadikan rujukan.</div>", unsafe_allow_html=True)

if st.session_state.get("latar") and gambar_b64("latar.jpg"):
    st.markdown(
        '<style>.stApp{background:linear-gradient(rgba(238,250,250,.38),rgba(238,250,250,.38)),'
        f'url("data:image/jpeg;base64,{gambar_b64("latar.jpg")}") 8% 8%/cover no-repeat fixed}}'
        'section[data-testid="stSidebar"]{background:rgba(220,244,241,.62);backdrop-filter:blur(2px)}'
        '.kartu,.ringkas{background:rgba(255,255,255,.88)}</style>', unsafe_allow_html=True)
