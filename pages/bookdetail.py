import gi

from gi.repository import Adw, Gtk
from pages.page import Page
from pages.reader.readerpage import ReaderPage
from core.images import load_thumbnail
import os
from core.api import LibraryAPI


class BookDetailPage(Page):
    def __init__(self, book, **kwargs):
        super().__init__(book["title"], **kwargs)
        self.book = book
        self.api = LibraryAPI()

        self.is_favorite = self.api.is_book_favorite(book["id"])
        self.history = self.api.get_book_history(book["id"])
        self.chapter_rows = {}   # <-- simpen row per chapter_id, buat di-refresh nanti

        toolbar_view = Adw.ToolbarView()

        header = Adw.HeaderBar()
        if self.is_favorite:
            self.favorite_button = Gtk.Button(icon_name="starred-symbolic")
        else:
            self.favorite_button = Gtk.Button(icon_name="non-starred-symbolic")
        self.favorite_button.set_tooltip_text("Favorite Book")
        self.favorite_button.connect("clicked", self.on_favorite_clicked)
        header.pack_end(self.favorite_button)
        toolbar_view.add_top_bar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        if book["cover_path"] and os.path.exists(book["cover_path"]):
            cover = load_thumbnail(book["cover_path"], 400, 560)
            cover.set_size_request(200, 280)
            box.append(cover)

        self.chapter_group = Adw.PreferencesGroup()
        for chapter in book["chapters"]:
            row = Adw.ActionRow()
            row.set_title(chapter["chapter_title"])
            row.set_activatable(True)
            row.connect("activated", self.onclick_chapter, chapter)
            self.chapter_group.add(row)
            self.chapter_rows[chapter["id"]] = row   # <-- simpen referensinya

        self.apply_history_to_rows()   # set subtitle awal
        box.append(self.chapter_group)

        toolbar_view.set_content(box)
        self.set_content(toolbar_view)

    def apply_history_to_rows(self):
        """Update subtitle tiap row berdasarkan history TERBARU."""
        for chapter_id, row in self.chapter_rows.items():
            if self.history and self.history.get("chapter_id") == chapter_id:
                row.set_subtitle(f"Page {self.history.get('last_page', 1)} • Last Seen")
            else:
                row.set_subtitle("")

    def refresh(self):
        """Dipanggil tiap kali halaman ini kelihatan lagi (termasuk pas balik dari Reader)."""
        self.history = self.api.get_book_history(self.book["id"])
        self.apply_history_to_rows()

    def on_favorite_clicked(self, button):
        res = self.api.toggle_favorite_book(self.book["id"])
        is_fav = res["is_favorite"]
        button.set_icon_name("starred-symbolic" if is_fav else "non-starred-symbolic")

    def onclick_chapter(self, row, chapter):
        # print(self.history.get("last_page"))
        if self.history and self.history.get("chapter_id") == chapter["id"]:
            print("last seen")
            reader_page = ReaderPage(chapter, initial_page=self.history.get("last_page"))
        else:
            print("new chapter")
            reader_page = ReaderPage(chapter)

        nav_page = Adw.NavigationPage(child=reader_page, title=chapter["chapter_title"])
        self.get_root().nav_view.push(nav_page)