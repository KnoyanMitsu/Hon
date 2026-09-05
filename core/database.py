import sqlite3
import threading


from .connection import Connection

class LibraryDB:
    def __init__(self):
        conn_wrapper = Connection()
        self.conn = conn_wrapper.get()
        self.lock = conn_wrapper.query_lock
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS library_paths (...);
            CREATE TABLE IF NOT EXISTS books (...);
            CREATE TABLE IF NOT EXISTS chapters (...);
        """)
        self.conn.commit()

    def save_books(self, books: list):
        cur = self.conn.cursor()
        imported, skipped = 0, 0

        for book in books:
            try:
                cur.execute(
                    "INSERT INTO books (title, folder_path, cover_path) VALUES (?, ?, ?)",
                    (book["title"], book["folder_path"], book["cover_path"]),
                )
                book_id = cur.lastrowid
            except sqlite3.IntegrityError:
                skipped += 1
                continue

            for ch in book["chapters"]:
                cur.execute(
                    "INSERT INTO chapters (book_id, chapter_number, chapter_title, file_path) "
                    "VALUES (?, ?, ?, ?)",
                    (book_id, ch["chapter_number"], ch["chapter_title"], ch["file_path"]),
                )
            imported += 1

        self.conn.commit()
        return {"imported": imported, "skipped": skipped}

    def get_all_books(self):
        with self.lock:   # <-- bungkus tiap operasi DB
            cur = self.conn.cursor()
            cur.execute("SELECT id, title, folder_path, cover_path FROM books ORDER BY title")
            books_raw = cur.fetchall()

            cur.execute(
                "SELECT book_id, id, chapter_number, chapter_title, file_path "
                "FROM chapters ORDER BY (chapter_number IS NULL), chapter_number, chapter_title"
            )
            chapters_raw = cur.fetchall()

        # proses grouping di luar lock (gak nyentuh DB lagi, jadi aman)
        chapters_by_book = {}
        for book_id, ch_id, number, title, path in chapters_raw:
            chapters_by_book.setdefault(book_id, []).append({
                "id": ch_id, "chapter_number": number,
                "chapter_title": title, "file_path": path,
            })

        books = []
        for book_id, title, folder_path, cover_path in books_raw:
            chapters = chapters_by_book.get(book_id, [])
            books.append({
                "id": book_id, "title": title, "folder_path": folder_path,
                "cover_path": cover_path, "total_chapters": len(chapters),
                "chapters": chapters,
            })
        return books

    def get_book(self, book_id: int):
        cur = self.conn.cursor()
        cur.execute("SELECT id, title, folder_path, cover_path FROM books WHERE id = ?", (book_id,))
        row = cur.fetchone()
        if not row:
            return None
        book_id, title, folder_path, cover_path = row
        chapters = self._get_chapters(book_id)
        return {
            "id": book_id,
            "title": title,
            "folder_path": folder_path,
            "cover_path": cover_path,
            "total_chapters": len(chapters),
            "chapters": chapters,
        }

    def delete_ocr_document(self, chapter_id: int):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("DELETE FROM ocr_documents WHERE chapter_id = ?", (chapter_id,))
            self.conn.commit()
            return {"deleted": cur.rowcount > 0}

    def get_chapter(self, chapter_id: int):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT id, book_id, chapter_number, chapter_title, file_path "
                "FROM chapters WHERE id = ?",
                (chapter_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "book_id": row[1],
            "chapter_number": row[2],
            "chapter_title": row[3],
            "file_path": row[4],
        }

    def update_cover_path(self, folder_path: str, cover_path: str):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "UPDATE books SET cover_path = ? WHERE folder_path = ?",
                (cover_path, folder_path),
            )
            self.conn.commit()
            return cur.rowcount > 0

    def _get_chapters(self, book_id: int):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, chapter_number, chapter_title, file_path FROM chapters "
            "WHERE book_id = ? ORDER BY (chapter_number IS NULL), chapter_number, chapter_title",
            (book_id,),
        )
        return [
            {"id": r[0], "chapter_number": r[1], "chapter_title": r[2], "file_path": r[3]}
            for r in cur.fetchall()
        ]

    def get_unsorted_chapters(self):
        cur = self.conn.cursor()
        cur.execute("""
            SELECT chapters.id, chapters.chapter_title, chapters.file_path, books.title
            FROM chapters JOIN books ON chapters.book_id = books.id
            WHERE chapters.chapter_number IS NULL
        """)
        return [
            {"id": r[0], "chapter_title": r[1], "file_path": r[2], "book_title": r[3]}
            for r in cur.fetchall()
        ]

    def update_chapter_number(self, chapter_id: int, number: float):
        cur = self.conn.cursor()
        cur.execute("UPDATE chapters SET chapter_number = ? WHERE id = ?", (number, chapter_id))
        self.conn.commit()
        return {"updated": cur.rowcount > 0}

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS library_paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                label TEXT
            );

            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                folder_path TEXT UNIQUE NOT NULL,
                cover_path TEXT
            );

            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                chapter_number REAL,
                chapter_title TEXT,
                file_path TEXT UNIQUE NOT NULL,
                FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS favorite_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id INTEGER NOT NULL,
                page_number INTEGER NOT NULL,
                UNIQUE(chapter_id, page_number),
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS ocr_documents (
                chapter_id INTEGER PRIMARY KEY,
                payload TEXT NOT NULL,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );
        """)
        self.conn.commit()

    def get_favorite_pages(self, chapter_id: int):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT page_number FROM favorite_pages "
                "WHERE chapter_id = ? ORDER BY page_number",
                (chapter_id,),
            )
            return [row[0] for row in cur.fetchall()]

    def toggle_favorite_page(self, chapter_id: int, page_number: int):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT 1 FROM favorite_pages WHERE chapter_id = ? AND page_number = ?",
                (chapter_id, page_number),
            )
            exists = cur.fetchone() is not None
            if exists:
                cur.execute(
                    "DELETE FROM favorite_pages WHERE chapter_id = ? AND page_number = ?",
                    (chapter_id, page_number),
                )
            else:
                cur.execute(
                    "INSERT INTO favorite_pages (chapter_id, page_number) VALUES (?, ?)",
                    (chapter_id, page_number),
                )
            self.conn.commit()
            return {"favorite": not exists, "page": page_number}

    def get_ocr_document(self, chapter_id: int):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT payload FROM ocr_documents WHERE chapter_id = ?",
                (chapter_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def save_ocr_document(self, chapter_id: int, payload: str):
        with self.lock:
            self.conn.execute(
                "INSERT INTO ocr_documents (chapter_id, payload) VALUES (?, ?) "
                "ON CONFLICT(chapter_id) DO UPDATE SET payload = excluded.payload",
                (chapter_id, payload),
            )
            self.conn.commit()

    # --- CRUD buat library_paths ---

    def add_folder(self, path: str, label: str = None):
        cur = self.conn.cursor()
        try:
            cur.execute(
                "INSERT INTO library_paths (path, label) VALUES (?, ?)",
                (path, label or path),
            )
            self.conn.commit()
            return {"added": True, "id": cur.lastrowid}
        except sqlite3.IntegrityError:
            return {"added": False, "reason": "path sudah terdaftar"}

    def get_folders(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id, path, label FROM library_paths ORDER BY label")
        return [{"id": r[0], "path": r[1], "label": r[2]} for r in cur.fetchall()]

    def remove_folder(self, folder_id: int):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM library_paths WHERE id = ?", (folder_id,))
        self.conn.commit()
        return {"removed": cur.rowcount > 0}

    def close(self):
        self.conn.close()