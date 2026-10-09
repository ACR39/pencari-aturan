# Cari Peraturan

Pencarian kata kunci per pasal untuk UU, Permen, perda, dsb., dengan ringkasan.

## Jalankan di komputer
```
pip install -r requirements.txt
streamlit run app.py
```

## Tayang online (gratis) lewat Streamlit Community Cloud
1. Buat repo di GitHub (disarankan **privat** bila dokumen tidak untuk umum), unggah seluruh isi folder ini.
2. Buka https://share.streamlit.io → *New app* → pilih repo, branch `main`, file `app.py` → *Deploy*.
3. (Opsional, untuk tombol ringkasan AI) Di *App settings → Secrets* isi, sesuaikan dengan gateway Anda:
   ```
   API_FORMAT = "openai"        # atau "anthropic" bila gateway meniru API Anthropic
   API_BASE_URL = "https://alamat-gateway-anda"
   API_KEY = "kunci-anda"
   API_MODEL = "nama-model-di-gateway"
   ```
   Tanpa ini aplikasi tetap jalan; ringkasan hanya berupa jumlah hasil dan pasal teratas. Jangan menaruh kunci di repo.

## Menambah dokumen
`data/index.json` adalah indeks hasil pemecahan per pasal. `pecah.py` membuatnya dari teks PDF:
```
pdftotext -layout peraturan.pdf sumber/peraturan.txt
python3 pecah.py data/index.json sumber/UU_...txt sumber/Permenhub_...txt
```
`pecah.py` saat ini disetel untuk dua dokumen contoh (UU 22/2009 dan PM 60/2019). Format dokumen lain
(perda, UU tanpa penjelasan, tanpa lampiran) perlu sedikit penyesuaian; minta bantuan Claude.
Setelah itu `git push`; situs diperbarui otomatis.

## Catatan
- Field `status` tiap dokumen di indeks masih "Belum diverifikasi": isi manual (berlaku/diubah/dicabut).
