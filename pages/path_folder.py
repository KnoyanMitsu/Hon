import gi

from gi.repository import Adw, Gtk
from pages.page import Page
import os
from core.api import LibraryAPI
from core.paths import get_db_path
from core.settings import get_setting, set_setting
class PathFolderPage(Page):
    """Halaman pengaturan folder yang digunakan untuk menyimpan buku."""

    def __init__(self, **kwargs):
        super().__init__("Path Folder", **kwargs)
        self.api = LibraryAPI()
        pref_page = Adw.PreferencesPage()

        # --- Group folder ---
        self.group = Adw.PreferencesGroup(
            title="Book Path Folder", description="Where your book? location"
        )

        content_button = Adw.ButtonContent()
        content_button.set_label("Add Path")
        content_button.set_icon_name("list-add-symbolic")

        add_button = Gtk.Button()
        add_button.set_child(content_button)
        add_button.add_css_class("flat")
        add_button.connect("clicked", self.on_add_clicked)

        self.group.set_header_suffix(add_button)
        for folder in self.api.get_folders():
                    self.pathGroup(os.path.basename(folder["path"]) or folder["path"], folder["path"])
        pref_page.add(self.group)


        button_group = Adw.PreferencesGroup()

        # Group Scan
        scan_button = Adw.ButtonRow(title="Scan Library")
        scan_button.connect("activated", self.on_scan_clicked)
        scan_button.add_css_class("suggested-action")
        button_group.add(scan_button)

        # --- Group About (row terpisah) ---
        about_row = Adw.ButtonRow(title="About")
        about_row.connect("activated", self.on_about_activated)
        button_group.add(about_row)





        pref_page.add(button_group)

        deepl_group = Adw.PreferencesGroup(
            title="Translation",
            description="DeepL API settings",
        )
        self.deepl_key_row = Adw.PasswordEntryRow(title="DeepL API key")
        self.deepl_key_row.set_text(get_setting("deepl_api_key", ""))
        deepl_group.add(self.deepl_key_row)

        self.deepl_language_row = Adw.EntryRow(title="Target language")
        self.deepl_language_row.set_text(get_setting("deepl_target_lang", "VI"))
        deepl_group.add(self.deepl_language_row)

        save_translation = Adw.ButtonRow(title="Save translation settings")
        save_translation.connect("activated", self.on_save_translation_settings)
        save_translation.add_css_class("suggested-action")
        deepl_group.add(save_translation)
        pref_page.add(deepl_group)


        # set_content cukup sekali, di akhir
        self.set_content(pref_page)

    def on_save_translation_settings(self, row):
        api_key = self.deepl_key_row.get_text().strip()
        target_language = self.deepl_language_row.get_text().strip().upper() or "VI"
        set_setting("deepl_api_key", api_key)
        set_setting("deepl_target_lang", target_language)
        print("DeepL settings saved")

    def pathGroup(self, title, subtitle):
        row = Adw.ActionRow(title=title)
        row.set_subtitle(subtitle)
        row.set_icon_name("folder-symbolic")
        self.group.add(row)

    def on_add_clicked(self, button):
        dialog = Gtk.FileDialog()
        dialog.set_title("Where your directory book")
        dialog.select_folder(self.get_root(), None, self.on_folder_selected)

    def on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if not folder:
                return
            path = folder.get_path()

            result = self.api.add_folder(path)   # <-- simpan ke DB
            if result["added"]:
                self.pathGroup(os.path.basename(path), path)
            else:
                print("Folder sudah terdaftar:", path)
        except Exception as e:
            print("Gagal pilih folder:", e)


    def on_about_activated(self, row):
        self.about()

    def about(self):
        about = Adw.AboutDialog(
            application_name="Hon",
            application_icon="me.knoyan.Hon",
            developer_name="Knoyan",
            version="0.1.0",
            developers=["Knoyan"],
        )
        about.set_website("https://github.com/kha-white/manga-ocr")
        about.add_credit_section(
            "Credits",
            [
                "Manga OCR - Japanese manga text recognition",
                "DeepL - Translation service",
                "GTK4 and Libadwaita - Desktop interface",
            ],
        )
        about.add_link(
            "Manga OCR GitHub",
            "https://github.com/kha-white/manga-ocr",
        )
        about.present(self.get_root())

    def on_scan_clicked(self, button):
        result = self.api.scan_all()   # <-- ini yang trigger scan semua path
        print("Hasil scan:", result)
        # TODO: nanti bisa diganti toast/notifikasi biar user liat progressnya