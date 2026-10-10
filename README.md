# Cari Peraturan

Pencarian kata kunci per pasal untuk UU, PP, Permen, perda, dsb., dengan ringkasan AI (opsional).
**Cukup unggah PDF ke folder `pdf/`** — GitHub memproses dan memperbarui pustaka secara otomatis.

## Cara kerja singkat
```
unggah PDF ke pdf/  →  GitHub Actions memproses (OCR bila pindaian)  →  data/index.json diperbarui
                    →  Streamlit memuat ulang  →  dokumen muncul di sidebar dan hasil pencarian
```

## A. Pemasangan pertama kali (sekali saja)
1. Buat repo di GitHub (disarankan **privat** bila dokumen tidak untuk umum), lalu unggah **seluruh isi** folder ini
   (termasuk folder tersembunyi `.github` dan `.streamlit`).
2. **Beri izin Actions menulis ke repo:** di GitHub buka *Settings → Actions → General → Workflow permissions*,
   pilih **Read and write permissions**, lalu *Save*. Tanpa ini, indeks hasil proses tidak bisa disimpan.
3. Di https://share.streamlit.io pilih *New app* → pilih repo, branch `main`, *Main file path* `app.py` → *Deploy*.
4. (Opsional) Tombol ringkasan AI: di Streamlit *App settings → Secrets* isi
   ```
   API_FORMAT = "openai"        # atau "anthropic"
   API_BASE_URL = "https://alamat-gateway-anda"
   API_KEY = "kunci-anda"
   API_MODEL = "nama-model"
   API_TIMEOUT = 150            # detik, opsional
   ```
   Jangan menaruh kunci di repo.

## B. Menambah dokumen
1. Buka repo di GitHub → folder **`pdf/`** → *Add file → Upload files* → seret PDF → *Commit changes*.
2. Buka tab **Actions**. Alur kerja "Proses PDF menjadi indeks" akan berjalan (PDF teks: sekitar 1 menit;
   PDF pindaian: sekitar 4–5 menit per 70 halaman). Tunggu tanda centang hijau.
3. Buka **`data/laporan.md`** di repo (atau ringkasan di halaman run Actions) untuk memeriksa hasilnya:
   jumlah pasal, lampiran, dan peringatan.
4. Streamlit memuat ulang sendiri setelah repo berubah. Bila belum, pilih *Reboot app*.

Nama file bebas (mis. `UU 22 Tahun 2009.pdf`). Jenis, nomor, tahun, dan judul dibaca otomatis dari halaman pertama.

## Unduh PDF asli
PDF yang Anda taruh di `pdf/` otomatis bisa diunduh dari aplikasi: tombol **⬇ PDF asli** muncul di atas hasil pencarian
(satu per dokumen yang muncul) dan di sidebar (*Unduh PDF asli*). Tombol hanya muncul bila file PDF-nya ada di repo.
Bila repo privat dan aplikasi dilindungi login, PDF ikut terlindungi.
Dokumen lama tanpa PDF (UU 22/2009 dan PM 60/2019) mendapat tombolnya setelah Anda mengunggah PDF-nya ke `pdf/`;
indeksnya akan diganti otomatis oleh hasil dari PDF itu.

## C. Mengganti atau menghapus dokumen
- **Mengganti:** unggah PDF baru dengan nama sama (timpa). Isi yang berubah akan diproses ulang.
- **Menghapus:** hapus file PDF-nya di `pdf/`. Dokumennya hilang dari indeks pada proses berikutnya.
- **Proses ulang semua:** tab *Actions* → *Proses PDF menjadi indeks* → *Run workflow* → centang "Proses ulang semua".

## D. Mengoreksi hasil otomatis (opsional)
Isi `pdf/pengaturan.json` bila ada yang perlu dikoreksi. Contoh:
```json
{
  "UU 22 Tahun 2009.pdf": { "status": "Berlaku" },
  "Perda Kota X.pdf": {
    "jenis": "Peraturan Daerah", "nomor": "5", "tahun": "2020",
    "judul": "Pengelolaan Parkir", "singkat": "Perda Kota X 5/2020"
  },
  "scan buram.pdf": { "ocr": true }
}
```
Kolom yang bisa diisi: `status` (mis. Berlaku / Diubah / Dicabut), `jenis`, `nomor`, `tahun`, `judul`, `singkat`,
`catatan`, `id`, dan `ocr` (`true` memaksa OCR, `false` melarang OCR).

## E. Bila hasil kurang pas
| Gejala di `data/laporan.md` | Penyebab dan tindakan |
|---|---|
| ⚠️ Nomor pasal tidak terdeteksi: 15, 19 | Judul pasal tidak terbaca (umum pada pindaian). Isi pasal itu menyatu dengan pasal sebelumnya. Hasil tetap bisa dicari. Pindaian lebih jernih memperbaikinya. |
| ⚠️ Pola 'Pasal N' tidak ditemukan | Dokumen tidak berformat pasal biasa. Dipotong per 40 baris, tetap bisa dicari. |
| ⚠️ Nomor/tahun/jenis tidak terbaca | Isi lewat `pdf/pengaturan.json` (bagian D). |
| ❌ gagal diproses | Lihat pesan galatnya. PDF terkunci kata sandi atau rusak tidak bisa dibaca. |
| Actions gagal di langkah "Simpan indeks" | Izin belum *Read and write* (langkah A.2). |
| Kata di hasil tampak salah ketik | PDF pindaian (OCR). Kartu hasilnya diberi catatan; cek ke PDF asli. |

## F. Dijalankan di komputer sendiri (opsional)
```
sudo apt install poppler-utils tesseract-ocr tesseract-ocr-ind   # Linux; di Windows/macOS pasang padanannya
python scripts/proses_pdf.py            # hanya PDF baru/berubah
python scripts/proses_pdf.py --semua    # proses ulang semua
pip install -r requirements.txt && streamlit run app.py
```

## Catatan penting
- Dokumen yang sudah ada di `data/index.json` tanpa PDF (mis. isian awal) tetap dipertahankan.
  Bila Anda mengunggah PDF peraturan yang sama, entrinya diganti oleh hasil PDF.
- Status berlaku/diubah/dicabut **tidak** diperiksa otomatis. Isi lewat `status` di `pdf/pengaturan.json`.
- Folder `sumber/` dan `pecah.py` adalah alat versi lama (konversi manual); boleh dihapus bila tidak dipakai.
