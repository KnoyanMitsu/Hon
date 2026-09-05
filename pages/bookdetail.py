import gi

from gi.repository import Adw, Gtk
from pages.page import Page
from pages.readerpage import ReaderPage
from core.images import load_thumbnail
import os


class BookDetailPage(Page):
    def __init__(self, book, **kwargs):
        super().__init__(book["title"], **kwargs)
        self.book = book

        print("id buku:", book["chapters"])

        toolbar_view = Adw.ToolbarView()

        header = Adw.HeaderBar()
        # title otomatis ngambil dari NavigationPage title kalau gak di-set manual,
        # tapi bisa custom juga kalau perlu:
        # header.set_title_widget(Adw.WindowTitle(title=book["title"]))
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

    def onclick_chapter(self, row, chapter):
        # Navigasi ke halaman detail chapter
        reader_page = ReaderPage(chapter)
        nav_page = Adw.NavigationPage(child=reader_page, title=chapter["chapter_title"])
        self.get_root().nav_view.push(nav_page)