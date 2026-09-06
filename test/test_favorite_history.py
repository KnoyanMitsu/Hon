import os
import sys
import unittest

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.api import LibraryAPI
from core.database import LibraryDB


class TestFavoriteAndHistory(unittest.TestCase):
    def setUp(self):
        self.api = LibraryAPI()
        self.db = self.api.db

        # Clean up any leftover data
        with self.db.lock:
            cur = self.db.conn.cursor()
            cur.execute("DELETE FROM reading_history")
            cur.execute("DELETE FROM favorite_books")
            cur.execute("DELETE FROM chapters")
            cur.execute("DELETE FROM books")
            self.db.conn.commit()

        # Insert dummy book and chapter for testing
        with self.db.lock:
            cur = self.db.conn.cursor()
            cur.execute(
                "INSERT INTO books (title, folder_path, cover_path) VALUES (?, ?, ?)",
                ("Test Book 1", "/path/test1", "/path/cover1.jpg"),
            )
            self.book1_id = cur.lastrowid

            cur.execute(
                "INSERT INTO books (title, folder_path, cover_path) VALUES (?, ?, ?)",
                ("Test Book 2", "/path/test2", "/path/cover2.jpg"),
            )
            self.book2_id = cur.lastrowid

            cur.execute(
                "INSERT INTO chapters (book_id, chapter_number, chapter_title, file_path) "
                "VALUES (?, ?, ?, ?)",
                (self.book1_id, 1.0, "Chapter 1", "/path/ch1.cbz"),
            )
            self.ch1_id = cur.lastrowid

            cur.execute(
                "INSERT INTO chapters (book_id, chapter_number, chapter_title, file_path) "
                "VALUES (?, ?, ?, ?)",
                (self.book1_id, 2.0, "Chapter 2", "/path/ch2.cbz"),
            )
            self.ch2_id = cur.lastrowid

            cur.execute(
                "INSERT INTO chapters (book_id, chapter_number, chapter_title, file_path) "
                "VALUES (?, ?, ?, ?)",
                (self.book2_id, 1.0, "Chapter 1", "/path/ch2_1.cbz"),
            )
            self.ch2_1_id = cur.lastrowid

            self.db.conn.commit()

    def tearDown(self):
        with self.db.lock:
            cur = self.db.conn.cursor()
            cur.execute("DELETE FROM reading_history")
            cur.execute("DELETE FROM favorite_books")
            cur.execute("DELETE FROM chapters")
            cur.execute("DELETE FROM books")
            self.db.conn.commit()

    def test_favorite_book(self):
        # Initial check
        self.assertFalse(self.api.is_book_favorite(self.book1_id))

        # Toggle favorite -> True
        res = self.api.toggle_favorite_book(self.book1_id)
        self.assertTrue(res["is_favorite"])
        self.assertTrue(self.api.is_book_favorite(self.book1_id))

        # Get favorite books list
        fav_list = self.api.get_favorite_books()
        self.assertEqual(len(fav_list["books"]), 1)
        self.assertEqual(fav_list["books"][0]["id"], self.book1_id)

        # Toggle favorite -> False
        res = self.api.toggle_favorite_book(self.book1_id)
        self.assertFalse(res["is_favorite"])
        self.assertFalse(self.api.is_book_favorite(self.book1_id))

        # Get favorite books list after removal
        fav_list = self.api.get_favorite_books()
        self.assertEqual(len(fav_list["books"]), 0)

    def test_reading_history(self):
        # Record reading chapter 1, page 5
        res = self.api.record_history(chapter_id=self.ch1_id, page_number=5)
        self.assertIsNotNone(res)
        self.assertEqual(res["book_id"], self.book1_id)
        self.assertEqual(res["chapter_id"], self.ch1_id)
        self.assertEqual(res["last_page"], 5)

        # Get history list
        hist = self.api.get_history()
        self.assertEqual(len(hist["history"]), 1)
        self.assertEqual(hist["history"][0]["book_id"], self.book1_id)
        self.assertEqual(hist["history"][0]["chapter_id"], self.ch1_id)
        self.assertEqual(hist["history"][0]["last_page"], 5)
        self.assertEqual(hist["history"][0]["book_title"], "Test Book 1")
        self.assertEqual(hist["history"][0]["chapter_title"], "Chapter 1")

        # Record reading chapter 2, page 10 (same book - should update upsert!)
        res2 = self.api.record_history(chapter_id=self.ch2_id, page_number=10)
        self.assertEqual(res2["book_id"], self.book1_id)
        self.assertEqual(res2["chapter_id"], self.ch2_id)
        self.assertEqual(res2["last_page"], 10)

        # History list still has length 1 for this book, but updated with chapter 2 & page 10
        hist2 = self.api.get_history()
        self.assertEqual(len(hist2["history"]), 1)
        self.assertEqual(hist2["history"][0]["chapter_id"], self.ch2_id)
        self.assertEqual(hist2["history"][0]["last_page"], 10)

        # Record reading book 2 chapter 1
        self.api.record_history(chapter_id=self.ch2_1_id, page_number=1)

        # History list now has length 2, ordered by updated_at DESC (Book 2 first)
        hist3 = self.api.get_history()
        self.assertEqual(len(hist3["history"]), 2)
        self.assertEqual(hist3["history"][0]["book_id"], self.book2_id)

        # Get book history for book 1
        b1_hist = self.api.get_book_history(self.book1_id)
        self.assertEqual(b1_hist["chapter_id"], self.ch2_id)

        # Delete single history item
        del_res = self.api.delete_history(self.book1_id)
        self.assertTrue(del_res["deleted"])
        hist4 = self.api.get_history()
        self.assertEqual(len(hist4["history"]), 1)

        # Clear history
        clear_res = self.api.clear_history()
        self.assertTrue(clear_res["cleared"])
        hist5 = self.api.get_history()
        self.assertEqual(len(hist5["history"]), 0)


if __name__ == "__main__":
    unittest.main()
