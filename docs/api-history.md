# Reading History API

Dokumentasi untuk API Layer riwayat baca pada aplikasi **Hon**.  
Source: [`core/api.py`](../core/api.py) · DB Layer: [`core/database.py`](../core/database.py)

---

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS reading_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER UNIQUE NOT NULL,          -- 1 buku = 1 row (upsert)
    chapter_id  INTEGER NOT NULL,                 -- chapter terakhir dibuka
    last_page   INTEGER DEFAULT 1,                -- halaman terakhir dibaca
    updated_at  TIMESTAMP,                        -- subsecond precision: '%Y-%m-%d %H:%M:%f'
    FOREIGN KEY (book_id)    REFERENCES books(id)    ON DELETE CASCADE,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_reading_history_updated ON reading_history(updated_at DESC);
```

> **Note:** Setiap buku hanya memiliki **satu baris** riwayat. Saat `record_history()` dipanggil untuk buku yang sama, data lama akan di-**upsert** (overwrite) bukan ditambahkan sebagai baris baru. Ini menjaga tabel tetap ramping dan query tetap cepat.

---

## API Methods (`LibraryAPI`)

### `record_history(chapter_id, page_number=1, book_id=None)`

Catat atau update riwayat baca. Dipanggil **saat user mengklik sebuah chapter**.

```python
def record_history(
    self,
    chapter_id: int,
    page_number: int = 1,
    book_id: int = None       # opsional — otomatis dicari dari chapter_id
) -> dict | None
```

**Parameter:**

| Parameter | Tipe | Default | Keterangan |
|---|---|---|---|
| `chapter_id` | `int` | — | ID chapter yang sedang dibuka |
| `page_number` | `int` | `1` | Halaman terakhir yang dibaca |
| `book_id` | `int` | `None` | ID buku. Jika `None`, dicari otomatis dari DB |

**Return:**
```json
{
  "id": 17,
  "book_id": 864,
  "chapter_id": 1099,
  "last_page": 5,
  "updated_at": "2026-09-06 07:00:00.123"
}
```

Return `None` jika `chapter_id` tidak ditemukan di database.

**Contoh penggunaan di Frontend:**
```python
# pages/bookdetail.py — saat chapter diklik
def onclick_chapter(self, row, chapter):
    self.api.record_history(chapter_id=chapter["id"], page_number=1)

    reader_page = ReaderPage(chapter)
    nav_page = Adw.NavigationPage(child=reader_page, title=chapter["chapter_title"])
    self.get_root().nav_view.push(nav_page)
```

---

### `record_history_json(chapter_id, page_number=1, book_id=None)`

Sama persis dengan `record_history()`, namun return berupa **JSON string** (berguna untuk debugging).

```python
def record_history_json(
    self,
    chapter_id: int,
    page_number: int = 1,
    book_id: int = None
) -> str
```

---

### `get_history(limit=50, offset=0)`

Ambil daftar riwayat baca terbaru, diurutkan dari yang **paling baru dibaca** (`updated_at DESC`).  
Dipanggil **saat membuka halaman History**.

```python
def get_history(
    self,
    limit: int = 50,      # maks jumlah item yang dikembalikan
    offset: int = 0       # skip N item dari awal (untuk pagination)
) -> dict
```

**Parameter:**

| Parameter | Tipe | Default | Keterangan |
|---|---|---|---|
| `limit` | `int` | `50` | Jumlah maksimal item yang dikembalikan |
| `offset` | `int` | `0` | Untuk paginasi: skip N item pertama |

**Return:**
```json
{
  "history": [
    {
      "id": 17,
      "book_id": 864,
      "book_title": "Judul Buku A",
      "cover_path": "/path/to/cover.jpg",
      "chapter_id": 1099,
      "chapter_number": 2.0,
      "chapter_title": "Chapter 2",
      "last_page": 5,
      "updated_at": "2026-09-06 07:00:00.123"
    }
  ]
}
```

**Contoh penggunaan di Frontend:**
```python
# pages/history.py — load daftar riwayat
def load_history(self):
    res = self.api.get_history(limit=50)
    history_list = res.get("history", [])

    for item in history_list:
        print(item["book_title"])      # "Judul Buku A"
        print(item["chapter_title"])   # "Chapter 2"
        print(item["last_page"])       # 5
```

---

### `get_history_json(limit=50, offset=0)`

Sama persis dengan `get_history()`, namun return berupa **JSON string**.

```python
def get_history_json(self, limit: int = 50, offset: int = 0) -> str
```

---

### `get_book_history(book_id)`

Ambil riwayat baca **satu buku tertentu**. Berguna untuk menampilkan tombol **"Resume Reading"** di halaman Detail Buku.

```python
def get_book_history(self, book_id: int) -> dict | None
```

**Parameter:**

| Parameter | Tipe | Keterangan |
|---|---|---|
| `book_id` | `int` | ID buku yang ingin dicek riwayatnya |

**Return:** sama dengan satu item dari `get_history()`, atau `None` jika belum pernah dibaca.

```json
{
  "id": 17,
  "book_id": 864,
  "book_title": "Judul Buku A",
  "cover_path": "/path/to/cover.jpg",
  "chapter_id": 1099,
  "chapter_number": 2.0,
  "chapter_title": "Chapter 2",
  "last_page": 5,
  "updated_at": "2026-09-06 07:00:00.123"
}
```

**Contoh penggunaan di Frontend:**
```python
# pages/bookdetail.py — tampilkan tombol Resume Reading
hist = self.api.get_book_history(book["id"])
if hist:
    resume_button.set_label(f"Resume: {hist['chapter_title']} pg.{hist['last_page']}")
    resume_button.set_visible(True)
```

---

### `get_book_history_json(book_id)`

Sama persis dengan `get_book_history()`, namun return berupa **JSON string**.

```python
def get_book_history_json(self, book_id: int) -> str
```

---

### `delete_history(book_id)`

Hapus riwayat baca **satu buku** berdasarkan `book_id`.

```python
def delete_history(self, book_id: int) -> dict
```

**Return:**
```json
{ "deleted": true, "book_id": 864 }
```

`"deleted": false` jika `book_id` tidak ditemukan di tabel riwayat.

---

### `clear_history()`

Hapus **seluruh** riwayat baca sekaligus.

```python
def clear_history(self) -> dict
```

**Return:**
```json
{ "cleared": true, "count": 17 }
```

`"count"` adalah jumlah baris yang berhasil dihapus.

---

## Ringkasan Semua Method

| Method | Operasi | Kapan Dipanggil |
|---|---|---|
| `record_history(chapter_id, page_number)` | **Create / Update** | Saat user klik chapter |
| `get_history(limit, offset)` | **Read List** | Saat buka halaman History |
| `get_book_history(book_id)` | **Read Single** | Untuk tombol Resume Reading |
| `get_history_json(limit, offset)` | **Read List (JSON)** | Debugging |
| `get_book_history_json(book_id)` | **Read Single (JSON)** | Debugging |
| `delete_history(book_id)` | **Delete Single** | Hapus 1 item dari History |
| `clear_history()` | **Delete All** | Hapus semua riwayat baca |

---

## Desain Database: Kenapa Upsert?

```
Setiap buku → HANYA 1 baris (UNIQUE book_id)

User baca Chapter 1    ──► INSERT baris baru  (book_id=1, chapter_id=10, page=1)
User baca Chapter 2    ──► UPDATE baris lama  (book_id=1, chapter_id=11, page=1)
User baca Chapter 2 p5 ──► UPDATE baris lama  (book_id=1, chapter_id=11, page=5)

Tabel tidak pernah membengkak.
```

Timestamp menggunakan `strftime('%Y-%m-%d %H:%M:%f', 'now')` agar presisinya **sub-milidetik**, memastikan urutan `ORDER BY updated_at DESC` selalu akurat bahkan jika dua history direkam dalam waktu yang sangat berdekatan.
