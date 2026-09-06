import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib
from pages.page import Page
from core.api import LibraryAPI
from core.images import load_thumbnail
from pages.readerpage import ReaderPage


class HistoryPage(Page):
    def __init__(self, **kwargs):
        super().__init__("History", **kwargs)
        self.api = LibraryAPI()
        self.connect("notify::mapped", self.on_mapped)
        self.load_history()

    def on_mapped(self, widget, param_spec):
        if self.get_mapped():
            self.load_history()

    def show_empty_state(self):
        status = Adw.StatusPage(
            icon_name="document-open-recent-symbolic",
            title="Nothing in your history yet",
            description="Go read some books and your reading history will appear here.",
        )
        self.set_content(status)

    def load_history(self):
        res = self.api.get_history(limit=50)
        history_list = res.get("history", [])

        if not history_list:
            self.show_empty_state()
            return

        # Gunakan PreferencesGroup untuk list bergaya native Libadwaita
        group = Adw.PreferencesGroup()
        group.set_title("Recently Read")
        group.set_margin_top(16)
        group.set_margin_bottom(16)
        group.set_margin_start(16)
        group.set_margin_end(16)

        for item in history_list:
            row = Adw.ActionRow()
            row.set_title(item["book_title"])
            
            # Format Subtitle: Chapter & Halaman Terakhir
            row.set_subtitle(f"{item['chapter_title']} • Halaman {item['last_page']}")
            row.set_activatable(True)

            # 1. Tambahkan Cover Buku di sebelah Kiri (Prefix)
            if item.get("cover_path") and os.path.exists(item["cover_path"]):
                cover = load_thumbnail(item["cover_path"], 45, 60)
                cover.set_size_request(45, 60)
                cover.add_css_class("card")
                row.add_prefix(cover)
            else:
                icon = Gtk.Image.new_from_icon_name("book-open-symbolic")
                icon.set_pixel_size(32)
                row.add_prefix(icon)

            # 2. Tambahkan Ikon Play di sebelah Kanan (Suffix)
            play_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
            row.add_suffix(play_icon)

            # 3. Klik baris -> Buka chapter langsung
            row.connect("activated", self.on_click_history, item)
            group.add(row)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(800)
        clamp.set_child(group)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_child(clamp)

        self.set_content(scrolled)

    def on_click_history(self, row, item):
        # Ambil data chapter dari ID
        chapter = self.api.db.get_chapter(item["chapter_id"])
        if chapter:
            reader_page = ReaderPage(chapter, initial_page=item.get("last_page", 1))
            nav_page = Adw.NavigationPage(child=reader_page, title=chapter["chapter_title"])
            self.get_root().nav_view.push(nav_page)
