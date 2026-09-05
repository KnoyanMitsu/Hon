import json
from .scanner import scan_library
from .database import LibraryDB
from core.paths import get_db_path
from .connection import Connection
from .reader import list_pages, read_page, read_pages
from .ocr import decode, encode, empty_document
from .manga_ocr import recognize, recognize_all
from .manga_ocr import recognize, recognize_all, recognize_crop
from .deepl import is_available as deepl_available, translate_document

class LibraryAPI:
    """Ini yang dipanggil dari GTK — semua fungsi return dict/list JSON-ready."""

    def __init__(self):
        self.db = LibraryDB()

    def is_first_run(self):
        return Connection().is_first_run

    def get_library(self):
        if self.is_first_run():
            return {"books": []}   # <-- skip, langsung balikin kosong tanpa query
        return {"books": self.db.get_all_books()}

    def scan_and_import(self, root_path: str):
        books = scan_library(root_path)
        result = self.db.save_books(books)
        self._update_covers(books)
        return result

    def _update_covers(self, books):
        for book in books:
            if book.get("cover_path"):
                self.db.update_cover_path(book["folder_path"], book["cover_path"])

    def get_library(self):
        return {"books": self.db.get_all_books()}

    def get_library_json(self):
        return json.dumps(self.get_library(), indent=2, ensure_ascii=False)

    def get_book(self, book_id: int):
        return self.db.get_book(book_id)

    def get_chapter_pages(self, chapter_id: int):
        chapter = self.db.get_chapter(chapter_id)
        if chapter is None:
            return None

        result = read_pages(chapter["file_path"])
        return {
            "chapter": chapter,
            **result,
        }

    def get_chapter_pages_json(self, chapter_id: int):
        return json.dumps(self.get_chapter_pages(chapter_id), indent=2, ensure_ascii=False)

    def get_chapter_page_list(self, chapter_id: int):
        chapter = self.db.get_chapter(chapter_id)
        if chapter is None:
            return None
        return {"chapter": chapter, **list_pages(chapter["file_path"])}

    def get_chapter_page(self, chapter_id: int, page_number: int):
        chapter = self.db.get_chapter(chapter_id)
        if chapter is None:
            return None
        return {"chapter": chapter, **read_page(chapter["file_path"], page_number)}

    def get_ocr_document(self, chapter_id: int):
        stored = self.db.get_ocr_document(chapter_id)
        return decode(stored) if stored else None

    def get_favorite_pages(self, chapter_id: int):
        return self.db.get_favorite_pages(chapter_id)

    def toggle_favorite_page(self, chapter_id: int, page_number: int):
        return self.db.toggle_favorite_page(chapter_id, page_number)

    def export_ocr(self, chapter_id: int):
        chapter = self.db.get_chapter(chapter_id)
        if chapter is None:
            return None
        existing = self.db.get_ocr_document(chapter_id)
        if existing:
            return encode(decode(existing))
        page_list = self.get_chapter_page_list(chapter_id)
        return encode(empty_document(chapter, page_list["total_pages"]))

    def import_ocr(self, chapter_id: int, text: str):
        document = decode(text)
        if document["chapter_id"] != chapter_id:
            raise ValueError("OCR ini bukan untuk chapter yang sedang dibuka")
        chapter = self.db.get_chapter(chapter_id)
        page_list = self.get_chapter_page_list(chapter_id)
        if chapter is None or document["total_pages"] != page_list["total_pages"]:
            raise ValueError("Jumlah halaman OCR tidak cocok dengan chapter")
        self.db.save_ocr_document(chapter_id, encode(document))
        return document

    def run_manga_ocr(self, chapter_id: int, page_number: int):
        page = self.get_chapter_page(chapter_id, page_number)
        if page is None:
            raise ValueError("Halaman tidak ditemukan")
        text = recognize(page["image_path"])
        document_text = self.db.get_ocr_document(chapter_id)
        document = decode(document_text) if document_text else None
        if document is None:
            chapter = self.db.get_chapter(chapter_id)
            document = empty_document(chapter, self.get_chapter_page_list(chapter_id)["total_pages"])
        document["pages"][page_number - 1]["blocks"] = [{
            "x": 0,
            "y": 0,
            "width": 1,
            "height": 1,
            "original": text,
            "translated": "",
        }]
        # Translation sementara dinonaktifkan agar API DeepL tidak terpakai.
        self.db.save_ocr_document(chapter_id, encode(document))
        return text

    def run_manga_ocr_selection(self, chapter_id: int, page_number: int, box):
        page = self.get_chapter_page(chapter_id, page_number)
        if page is None:
            raise ValueError("Halaman tidak ditemukan")
        left, top, right, bottom = [int(value) for value in box]
        text = recognize_crop(page["image_path"], (left, top, right, bottom)).strip()
        if not text:
            raise ValueError("Tidak ada teks yang terbaca di area pilihan")

        document_text = self.db.get_ocr_document(chapter_id)
        document = decode(document_text) if document_text else None
        if document is None:
            chapter = self.db.get_chapter(chapter_id)
            document = empty_document(chapter, self.get_chapter_page_list(chapter_id)["total_pages"])
        document["pages"][page_number - 1].setdefault("blocks", []).append({
            "x": left,
            "y": top,
            "width": right - left,
            "height": bottom - top,
            "original": text,
            "translated": "",
            "confidence": 1.0,
        })
        self.db.save_ocr_document(chapter_id, encode(document))
        return text

    def run_manga_ocr_all(self, chapter_id: int):
        chapter = self.db.get_chapter(chapter_id)
        if chapter is None:
            raise ValueError("Chapter tidak ditemukan")
        page_list = self.get_chapter_page_list(chapter_id)
        page_paths = [
            self.get_chapter_page(chapter_id, page["page"])["image_path"]
            for page in page_list["pages"]
        ]
        pages = recognize_all(page_paths)
        document = empty_document(chapter, len(pages))
        document["pages"] = pages
        # Translation sementara dinonaktifkan agar API DeepL tidak terpakai.
        self.db.save_ocr_document(chapter_id, encode(document))
        return document

    def translate_ocr(self, chapter_id: int):
        if not deepl_available():
            raise RuntimeError("Translation sementara dinonaktifkan")
        stored = self.db.get_ocr_document(chapter_id)
        if not stored:
            raise ValueError("Belum ada hasil OCR untuk chapter ini")

        document = decode(stored)
        translated_count = translate_document(document)

        self.db.save_ocr_document(chapter_id, encode(document))
        return {"document": document, "translated": translated_count}

    def clear_ocr_page(self, chapter_id: int, page_number: int):
        """Hapus semua blocks OCR di 1 halaman tertentu, halaman lain gak kesentuh."""
        stored = self.db.get_ocr_document(chapter_id)
        if not stored:
            return None

        document = decode(stored)
        for page in document["pages"]:
            if page["page"] == page_number:
                page["blocks"] = []
                break

        self.db.save_ocr_document(chapter_id, encode(document))
        return document


    def clear_ocr_document(self, chapter_id: int):
        """Reset blocks OCR di SEMUA halaman jadi kosong (dokumen tetap ada, cuma bersih)."""
        stored = self.db.get_ocr_document(chapter_id)
        if not stored:
            return None

        document = decode(stored)
        for page in document["pages"]:
            page["blocks"] = []

        self.db.save_ocr_document(chapter_id, encode(document))
        return document

    def delete_ocr_document(self, chapter_id: int):
        return self.db.delete_ocr_document(chapter_id)

    def delete_ocr_document(self, chapter_id: int):
        """Hapus dokumen OCR sepenuhnya dari database (bukan cuma blocks-nya)."""
        return self.db.delete_ocr_document(chapter_id)

    def get_unsorted(self):
        return self.db.get_unsorted_chapters()

    def set_chapter_number(self, chapter_id: int, number: float):
        return self.db.set_chapter_number(chapter_id, number)

    def add_folder(self, path: str, label: str = None):
        return self.db.add_folder(path, label)

    def get_folders(self):
        return self.db.get_folders()

    def remove_folder(self, folder_id: int):
        return self.db.remove_folder(folder_id)

    def scan_all(self):
        folders = self.db.get_folders()
        total_imported = 0
        total_skipped = 0
        errors = []

        for folder in folders:
            try:
                books = scan_library(folder["path"])       # scan 1 path
                result = self.db.save_books(books)          # simpan hasilnya
                self._update_covers(books)
                total_imported += result["imported"]
                total_skipped += result["skipped"]
            except Exception as e:
                errors.append({"path": folder["path"], "error": str(e)})

        return {
            "folders_scanned": len(folders),
            "imported": total_imported,
            "skipped": total_skipped,
            "errors": errors,
        }

    def get_library(self):
        return {"books": self.db.get_all_books()}

    def close(self):
        self.db.close()