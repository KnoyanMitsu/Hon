import gi

from gi.repository import Adw, Gtk
from pages.page import Page
from pages.readerpage import ReaderPage
from core.images import load_thumbnail
import os
from core.api import LibraryAPI


class BookDetailPage(Page):
    def __init__(self, book, **kwargs):
        super().__init__(book["title"], **kwargs)
        self.book = book

        self.api = LibraryAPI()
        print("id buku:", book["chapters"])

        self.is_favorite = self.api.is_book_favorite(book["id"])

        toolbar_view = Adw.ToolbarView()

        header = Adw.HeaderBar()
        # title otomatis ngambil dari NavigationPage title kalau gak di-set manual,
        # tapi bisa custom juga kalau perlu:
        # header.set_title_widget(Adw.WindowTitle(title=book["title"]))
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

        chapter_group = Adw.PreferencesGroup()
        for chapter in book["chapters"]:
            row = Adw.ActionRow()
            row.set_title(chapter["chapter_title"])
            row.set_activatable(True)
            row.connect("activated", self.onclick_chapter, chapter)
            chapter_group.add(row)
        box.append(chapter_group)

        toolbar_view.set_content(box)

        self.set_content(toolbar_view)

    def on_favorite_clicked(self, button):
        res = self.api.toggle_favorite_book(self.book["id"])
        is_fav = res["is_favorite"]
        button.set_icon_name("starred-symbolic" if is_fav else "non-starred-symbolic")

    def onclick_chapter(self, row, chapter):
        print(f"Navigasi ke chapter: {chapter['chapter_title']} (ID: {chapter['id']})")
        # Navigasi ke halaman detail chapter
        reader_page = ReaderPage(chapter)
        nav_page = Adw.NavigationPage(child=reader_page, title=chapter["chapter_title"])
        self.get_root().nav_view.push(nav_page)