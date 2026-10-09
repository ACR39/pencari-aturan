"""Cari Peraturan — pencarian kata kunci per pasal + ringkasan. Jalankan: streamlit run app.py"""
import html
import json
import math
import re
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Cari Peraturan", page_icon="🔎", layout="centered")

INDEKS = Path(__file__).parent / "data" / "index.json"
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
DOCS = {d["id"]: d for d in DATA["docs"]}
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
    return WORD.sub(lambda m: f"<mark>{m.group()}</mark>" if stem(m.group()) in ts else m.group(),
                    html.escape(t)).replace("\n", "<br>")


def rujuk(c) -> str:
    return f"{DOCS[c['doc']]['singkat']} · {c['label']}"


def ringkas_llm(q, ts, hits):
    """Ringkasan lewat gateway/API apa pun. Atur di Secrets:
    API_FORMAT = "openai" (default, /chat/completions) atau "anthropic" (/v1/messages)
    API_BASE_URL, API_KEY, API_MODEL
    """
    import urllib.request

    kutipan = "\n\n".join(
        f"[{rujuk(c)}]\n{potong(c['text'], ts, 900)}"
        + (f"\nPenjelasan: {potong(c['penjelasan'], ts, 300)}" if c.get("penjelasan") else "")
        for c in hits[:8])
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
        body = {"model": model, "max_tokens": 600, "messages": [{"role": "user", "content": prompt}]}
    else:
        url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
        headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
        body = {"model": model, "max_tokens": 600, "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(url, json.dumps(body).encode(), headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.loads(r.read())
    return j["content"][0]["text"] if fmt == "anthropic" else j["choices"][0]["message"]["content"]


st.title("Cari Peraturan")
st.caption(f"Cari kata kunci di {len(DOCS)} peraturan ({N} potongan per pasal).")

q = st.text_input("Kata kunci", placeholder="mis. denda administratif")
pilih = st.multiselect("Dokumen", list(DOCS), default=list(DOCS),
                       format_func=lambda i: f"{DOCS[i]['singkat']} — {DOCS[i]['judul']}")

if q:
    ts, hits = cari(q, set(pilih))
    if not ts:
        st.info("Ketik kata kunci yang lebih spesifik.")
    elif not hits:
        st.warning(f"Tidak ada hasil untuk “{q}”. Coba kata dasar atau sinonim.")
    else:
        per = {}
        for c in hits:
            per[c["doc"]] = per.get(c["doc"], 0) + 1
        with st.container(border=True):
            st.markdown("**RINGKASAN**")
            st.write(f"{len(hits)} bagian cocok ({', '.join(f'{DOCS[k]['singkat']}: {v}' for k, v in per.items())}). "
                     f"Paling relevan: {', '.join(rujuk(c) for c in hits[:3])}.")
            if all(k in st.secrets for k in ("API_BASE_URL", "API_KEY", "API_MODEL")):
                if st.button("Ringkas isinya dengan AI"):
                    with st.spinner("Meringkas…"):
                        try:
                            st.markdown(ringkas_llm(q, ts, hits))
                        except Exception as e:  # noqa: BLE001
                            st.error(f"Ringkasan gagal: {e}")
        tampil = st.session_state.get("tampil", 10)
        for c in hits[:tampil]:
            d = DOCS[c["doc"]]
            with st.container(border=True):
                st.caption(" › ".join(filter(None, [f"{d['jenis']} {d['nomor']}/{d['tahun']}",
                                                     c.get("bab"), c.get("bagian"), c.get("paragraf")])))
                st.markdown(f"**{c['label']}**")
                st.markdown(sorot(potong(c["text"], ts, 700), ts), unsafe_allow_html=True)
                if c.get("penjelasan"):
                    st.markdown("<small><b>Penjelasan:</b> " + sorot(potong(c["penjelasan"], ts, 400), ts)
                                + "</small>", unsafe_allow_html=True)
                if c.get("lowq"):
                    st.caption("Teks lampiran ini hasil pindaian kurang rapi; cek ke dokumen asli.")
        if len(hits) > tampil:
            if st.button(f"Tampilkan lebih banyak ({len(hits) - tampil})"):
                st.session_state["tampil"] = tampil + 10
                st.rerun()

st.divider()
st.caption("Status berlaku/diubah/dicabut belum diverifikasi: "
           + ", ".join(d["singkat"] for d in DOCS.values())
           + ". Periksa perubahan terbaru sebelum dijadikan rujukan.")
