import gi
import os
import threading
from PIL import Image
from gi.repository import Gio, Gdk
from gi.repository import Adw, Gtk
from gi.repository import GLib
from pages.page import Page
from core.api import LibraryAPI
from core.images import thumbnail_path
from core.manga_ocr import is_available
from core.deepl import is_available as deepl_available


class ReaderPage(Page):
    def __init__(self, chapter, **kwargs):
        super().__init__("Reader", **kwargs)

        self.chapter = chapter
        self.debug_reader = os.environ.get("HON_DEBUG_READER") == "1"
        self.preview_width = 720
        self.preview_height = 1080
        self.show_original_overlay = False

        self.reader_api = LibraryAPI()
        data = self.reader_api.get_chapter_page_list(chapter["id"])
        self.page_data = data["pages"] if data is not None else []
        self.loaded_pages = set()
        self.loading_pages = set()
        self.worker_limit = threading.BoundedSemaphore(2)
        self.current_page = 0
        self.favorite_pages = set(self.reader_api.get_favorite_pages(chapter["id"]))
        self.page_containers = []
        self.ocr_document = self.reader_api.get_ocr_document(chapter["id"])
        self.ocr_action = None
        self.all_ocr_action = None
        self.translate_action = None
        self.manga_ocr_available = is_available()
        self.deepl_available = deepl_available()
        self.updating_indicator = False
        self.ocr_running = False
        self.selection_enabled = False
        self.selection_start = None
        self.selection_box = None
        self.debug_log(
            "initialized chapter=%s pages=%s format=%s"
            % (
                chapter.get("id"),
                len(self.page_data),
                data.get("format") if data else "none",
            )
        )
        toolbar_view = Adw.ToolbarView()

        header = Adw.HeaderBar()
        self.setup_ocr_menu(header)
        self.favorite_button = Gtk.Button(icon_name="non-starred-symbolic")
        self.favorite_button.set_tooltip_text("Add page to favorites")
        self.favorite_button.connect("clicked", self.on_favorite_clicked)
        header.pack_end(self.favorite_button)
        toolbar_view.add_top_bar(header)

        self.carousel = Adw.Carousel()
        self.carousel.set_vexpand(True)
        self.carousel.set_hexpand(True)
        self.reader_overlay = Gtk.Overlay()
        self.reader_overlay.set_child(self.carousel)
        self.ocr_spinner = Adw.Spinner(
            halign="center",
            valign="center",
            width_request=48,
            height_request=48,
        )
        self.ocr_spinner.set_visible(False)
        self.reader_overlay.add_overlay(self.ocr_spinner)
        self.selection_layer = Gtk.Fixed()
        self.selection_layer.set_hexpand(True)
        self.selection_layer.set_vexpand(True)
        self.selection_layer.set_can_target(False)
        self.reader_overlay.add_overlay(self.selection_layer)
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(
            ".ocr-selection-box { "
            "background-color: rgba(80, 150, 255, 0.20); "
            "border: 2px solid #4d9cff; "
            "}"
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self.selection_gesture = Gtk.GestureDrag()
        self.selection_gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.selection_gesture.connect("drag-begin", self.on_selection_begin)
        self.selection_gesture.connect("drag-update", self.on_selection_update)
        self.selection_gesture.connect("drag-end", self.on_selection_end)
        self.reader_overlay.add_controller(self.selection_gesture)
        self.selection_button = Gtk.Button(icon_name="edit-select-symbolic")
        self.selection_button.set_tooltip_text("Select area for Manga OCR")
        self.selection_button.connect("clicked", self.toggle_selection)
        header.pack_end(self.selection_button)

        for page in self.page_data:
            container = Gtk.Overlay()

            container.set_hexpand(True)     # <-- tambah ini
            container.set_vexpand(True)     # <-- dan ini
            placeholder = Gtk.Box()
            placeholder.add_css_class("reader-page-placeholder")
            placeholder.set_vexpand(True)
            placeholder.set_hexpand(True)
            container.set_child(placeholder)
            marker = Gtk.Image.new_from_icon_name("starred-symbolic")
            marker.set_halign(Gtk.Align.END)
            marker.set_valign(Gtk.Align.START)
            marker.set_margin_top(12)
            marker.set_margin_end(12)
            marker.set_visible(page["page"] in self.favorite_pages)
            container.add_overlay(marker)
            text_layer = Gtk.Fixed()
            text_layer.set_halign(Gtk.Align.FILL)
            text_layer.set_valign(Gtk.Align.FILL)
            text_layer.set_hexpand(True)
            text_layer.set_vexpand(True)
            container.add_overlay(text_layer)
            page_index = len(self.page_containers)
            container.connect(
                "notify::width",
                lambda widget, spec, index=page_index: self.update_page_overlay(index),
            )
            container.connect(
                "notify::height",
                lambda widget, spec, index=page_index: self.update_page_overlay(index),
            )
            self.page_containers.append((container, marker, text_layer, []))
            self.carousel.append(container)

        self.carousel.connect("notify::position", self.on_page_changed)
        self.load_nearby_pages(0)
        self.update_favorite_button()

        toolbar_view.set_content(self.reader_overlay)


        indicator = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        indicator.set_margin_top(8)
        indicator.set_margin_bottom(8)
        indicator.set_margin_start(12)
        indicator.set_margin_end(12)

        self.page_label = Gtk.Label(label=self.page_text(1))
        self.page_label.set_width_chars(len(self.page_text(len(self.page_data))))
        indicator.append(self.page_label)

        self.page_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            0,
            max(0, len(self.page_data) - 1),
            1,
        )
        self.page_scale.set_draw_value(False)
        self.page_scale.set_hexpand(True)
        self.page_scale.set_sensitive(bool(self.page_data))
        self.page_scale.connect("value-changed", self.on_indicator_changed)
        self.update_favorite_marks()
        indicator.append(self.page_scale)
        toolbar_view.add_bottom_bar(indicator)

        self.set_content(toolbar_view)
        self.connect("notify::width", self.on_width_changed)
        GLib.idle_add(self.render_ocr_overlays)
        GLib.idle_add(self.update_ocr_action)

    def setup_ocr_menu(self, header):
        actions = Gio.SimpleActionGroup()

        toggle_action = Gio.SimpleAction.new_stateful(
            "toggle-original",
            None,
            GLib.Variant.new_boolean(self.show_original_overlay),
        )



        self.toggle_original_action = toggle_action
        ocr_action = Gio.SimpleAction.new("run-manga-ocr", None)
        all_ocr_action = Gio.SimpleAction.new("run-manga-ocr-all", None)
        translate_action = Gio.SimpleAction.new("translate-ocr", None)
        export_action = Gio.SimpleAction.new("export-ocr", None)
        import_action = Gio.SimpleAction.new("import-ocr", None)
        select_action = Gio.SimpleAction.new("select-ocr-area", None)
        clear_ocr_action = Gio.SimpleAction.new("clear-ocr", None)
        ocr_action.connect("activate", self.on_run_manga_ocr)
        all_ocr_action.connect("activate", self.on_run_manga_ocr_all)
        translate_action.connect("activate", self.on_translate_ocr)
        export_action.connect("activate", self.on_export_ocr)
        import_action.connect("activate", self.on_import_ocr)
        select_action.connect("activate", self.on_select_ocr_area)
        clear_ocr_action.connect("activate", self.on_clear_ocr)
        toggle_action.connect("activate", self.on_toggle_original)
        actions.add_action(toggle_action)
        actions.add_action(ocr_action)
        actions.add_action(all_ocr_action)
        actions.add_action(translate_action)
        actions.add_action(export_action)
        actions.add_action(import_action)
        actions.add_action(select_action)
        actions.add_action(clear_ocr_action)
        self.ocr_action = ocr_action
        self.all_ocr_action = all_ocr_action
        self.translate_action = translate_action
        header.insert_action_group("reader", actions)

        menu = Gio.Menu()
        menu.append("Show Original Text", "reader.toggle-original")
        menu.append("Run Manga OCR (current page)", "reader.run-manga-ocr")
        menu.append("Run Manga OCR (all pages)", "reader.run-manga-ocr-all")
        menu.append("Translate OCR", "reader.translate-ocr")
        menu.append("Export OCR JSON", "reader.export-ocr")
        menu.append("Import OCR JSON", "reader.import-ocr")
        menu.append("Select OCR Area", "reader.select-ocr-area")
        menu.append("Clear OCR", "reader.clear-ocr")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_button.set_tooltip_text("OCR menu")
        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)

    def on_select_ocr_area(self, action, parameter):
        self.toggle_selection(self.selection_button)

    def on_width_changed(self, widget, param_spec):
        self.update_ocr_action()

    def toggle_selection(self, button):
        self.selection_enabled = not self.selection_enabled
        self.selection_layer.set_can_target(self.selection_enabled)
        button.set_active(self.selection_enabled) if hasattr(button, "set_active") else None
        if not self.selection_enabled and self.selection_box:
            self.selection_layer.remove(self.selection_box)
            self.selection_box = None

    def on_selection_begin(self, gesture, start_x, start_y):
        if not self.selection_enabled:
            return
        self.selection_start = (start_x, start_y)
        if self.selection_box:
            self.selection_layer.remove(self.selection_box)
        self.selection_box = Gtk.Box()
        self.selection_box.add_css_class("ocr-selection-box")
        self.selection_layer.put(self.selection_box, int(start_x), int(start_y))

    def on_selection_update(self, gesture, offset_x, offset_y):
        if not self.selection_enabled or not self.selection_box or not self.selection_start:
            return
        start_x, start_y = self.selection_start
        left, top = min(start_x, start_x + offset_x), min(start_y, start_y + offset_y)
        width, height = abs(offset_x), abs(offset_y)
        self.selection_layer.move(self.selection_box, int(left), int(top))
        self.selection_box.set_size_request(max(1, int(width)), max(1, int(height)))

    def on_selection_end(self, gesture, offset_x, offset_y):
        if not self.selection_enabled or not self.selection_start:
            return
        start_x, start_y = self.selection_start
        self.selection_start = None
        self.run_selection_ocr(start_x, start_y, start_x + offset_x, start_y + offset_y)

    def on_toggle_original(self, action, parameter):
        self.show_original_overlay = not self.show_original_overlay
        action.set_state(GLib.Variant.new_boolean(self.show_original_overlay))
        self.render_ocr_overlays() 

    def run_selection_ocr(self, x1, y1, x2, y2):
        page_number = self.current_page + 1
        page = self.reader_api.get_chapter_page(self.chapter["id"], page_number)
        if not page:
            return
        image = Image.open(page["image_path"])
        container = self.page_containers[self.current_page][0]
        scale = min(container.get_width() / image.width, container.get_height() / image.height)
        offset_x = (container.get_width() - image.width * scale) / 2
        offset_y = (container.get_height() - image.height * scale) / 2
        left = max(0, int((min(x1, x2) - offset_x) / scale))
        top = max(0, int((min(y1, y2) - offset_y) / scale))
        right = min(image.width, int((max(x1, x2) - offset_x) / scale))
        bottom = min(image.height, int((max(y1, y2) - offset_y) / scale))
        if right <= left or bottom <= top:
            return
        self.set_ocr_running(True)
        threading.Thread(
            target=self.run_selection_ocr_background,
            args=(page_number, (left, top, right, bottom)),
            daemon=True,
        ).start()

    def run_selection_ocr_background(self, page_number, box):
        try:
            self.reader_api.run_manga_ocr_selection(self.chapter["id"], page_number, box)
            GLib.idle_add(self.on_selection_ocr_finished, None)
        except Exception as error:
            GLib.idle_add(self.on_selection_ocr_finished, str(error))

    def on_selection_ocr_finished(self, error):
        self.set_ocr_running(False)
        if error:
            print(f"Manga OCR selection gagal: {error}")
        else:
            self.ocr_document = self.reader_api.get_ocr_document(self.chapter["id"])
            self.render_ocr_overlays()
            print("Manga OCR selection selesai")
        return False

    def update_ocr_action(self):
        if self.ocr_action is not None:
            is_mobile = self.get_width() > 0 and self.get_width() <= 600
            self.ocr_action.set_enabled(
                not is_mobile and self.manga_ocr_available
            )
            self.all_ocr_action.set_enabled(
                not is_mobile and self.manga_ocr_available
            )
            self.translate_action.set_enabled(
                not is_mobile and self.deepl_available
            )
        return False
    def on_clear_ocr(self, action, parameter):
        self.set_ocr_running(True)
        threading.Thread(
            target=self.clear_ocr_in_background,   # <-- method ini gak ada
            daemon=True,
        ).start()

    def clear_ocr_in_background(self):
        try:
            self.reader_api.clear_ocr_document(self.chapter["id"])   # <-- bukan delete_ocr_document
            GLib.idle_add(self.on_clear_ocr_finished, None)
        except Exception as error:
            GLib.idle_add(self.on_clear_ocr_finished, str(error))

    def on_clear_ocr_finished(self, error):
        self.set_ocr_running(False)
        if error:
            print(f"Clear OCR gagal: {error}")
        else:
            self.ocr_document = None
            self.render_ocr_overlays()   # akan otomatis skip karena self.ocr_document None

            # bersihin label yang udah kepasang di layar (kalau ada)
            for container, marker, text_layer, labels in self.page_containers:
                for label in labels:
                    text_layer.remove(label)
                labels.clear()

            print("OCR berhasil dihapus")
        return False
        
    def on_translate_ocr(self, action, parameter):
        self.debug_log("manual DeepL translation requested")
        self.set_ocr_running(True)
        threading.Thread(
            target=self.translate_ocr_in_background,
            daemon=True,
        ).start()

    def translate_ocr_in_background(self):
        try:
            result = self.reader_api.translate_ocr(self.chapter["id"])
            GLib.idle_add(self.on_translate_finished, result["translated"], None)
        except Exception as error:
            GLib.idle_add(self.on_translate_finished, 0, str(error))

    def on_translate_finished(self, translated_count, error):
        self.set_ocr_running(False)
        if error:
            print(f"DeepL translation gagal: {error}")
        else:
            print(f"DeepL translation selesai: {translated_count} block")
            self.ocr_document = self.reader_api.get_ocr_document(self.chapter["id"])
            self.render_ocr_overlays()
        return False

    def on_export_ocr(self, action, parameter):
        dialog = Gtk.FileDialog()
        dialog.set_initial_name(f"chapter-{self.chapter['id']}-ocr.json")
        dialog.save_text_file(self.get_root(), None, self.on_export_finished)

    def on_export_finished(self, dialog, result):
        try:
            file, encoding, line_ending = dialog.save_text_file_finish(result)
            payload = self.reader_api.export_ocr(self.chapter["id"])
            file.replace_contents(
                payload.encode("utf-8"),
                None,
                False,
                Gio.FileCreateFlags.REPLACE_DESTINATION,
                None,
            )
            print("OCR berhasil di-export")
        except Exception as error:
            print(f"Gagal export OCR: {error}")

    def on_import_ocr(self, action, parameter):
        dialog = Gtk.FileDialog()
        dialog.open_text_file(self.get_root(), None, self.on_import_finished)

    def on_import_finished(self, dialog, result):
        try:
            file, encoding = dialog.open_text_file_finish(result)
            success, contents, _ = file.load_contents()
            if not success:
                raise RuntimeError("file OCR tidak bisa dibaca")
            self.reader_api.import_ocr(
                self.chapter["id"],
                contents.decode("utf-8"),
            )
            print("OCR berhasil di-import")
        except Exception as error:
            print(f"Gagal import OCR: {error}")

    def on_run_manga_ocr_all(self, action, parameter):
        self.debug_log("manual manga OCR all pages requested")
        self.set_ocr_running(True)
        threading.Thread(
            target=self.run_manga_ocr_all_in_background,
            daemon=True,
        ).start()

    def run_manga_ocr_all_in_background(self):
        try:
            document = self.reader_api.run_manga_ocr_all(self.chapter["id"])
            GLib.idle_add(
                self.on_manga_ocr_all_finished,
                len(document["pages"]),
                None,
            )
        except Exception as error:
            GLib.idle_add(self.on_manga_ocr_all_finished, 0, str(error))

    def on_manga_ocr_all_finished(self, page_count, error):
        self.set_ocr_running(False)
        if error:
            print(f"Manga OCR semua halaman gagal: {error}")
        else:
            print(f"Manga OCR selesai untuk {page_count} halaman")
        return False

    def on_run_manga_ocr(self, action, parameter):
        page_number = self.current_page + 1
        self.debug_log("manual manga OCR requested page=%s" % page_number)
        self.set_ocr_running(True)
        threading.Thread(
            target=self.run_manga_ocr_in_background,
            args=(page_number,),
            daemon=True,
        ).start()

    def run_manga_ocr_in_background(self, page_number):
        try:
            text = self.reader_api.run_manga_ocr(self.chapter["id"], page_number)
            GLib.idle_add(self.on_manga_ocr_finished, page_number, text, None)
        except Exception as error:
            GLib.idle_add(self.on_manga_ocr_finished, page_number, None, str(error))

    def on_manga_ocr_finished(self, page_number, text, error):
        self.set_ocr_running(False)
        if error:
            print(f"Manga OCR gagal halaman {page_number}: {error}")
        else:
            print(f"Manga OCR selesai halaman {page_number}: {text}")
            self.ocr_document = self.reader_api.get_ocr_document(self.chapter["id"])
            self.render_ocr_overlays()
        return False

    def set_ocr_running(self, running):
        self.ocr_running = running
        self.ocr_spinner.set_visible(running)
        if self.ocr_action:
            self.ocr_action.set_enabled(not running and self.manga_ocr_available)
        if self.all_ocr_action:
            self.all_ocr_action.set_enabled(not running and self.manga_ocr_available)
        if self.translate_action:
            self.translate_action.set_enabled(not running and self.deepl_available)

    def render_ocr_overlays(self):
        if not self.ocr_document:
            return
        for page_index, page in enumerate(self.ocr_document.get("pages", [])):
            if page_index >= len(self.page_containers):
                break
            container, marker, text_layer, labels = self.page_containers[page_index]
            for label in labels:
                text_layer.remove(label)
            labels.clear()
            blocks = page.get("blocks", [])
            self.debug_log(f"page={page_index+1} jumlah blocks={len(blocks)}")   # <-- tambahin ini
            for block in blocks:
                text = block.get("original", "").strip()
                self.debug_log(f"  block text='{text}'")   # <-- dan ini
                if not text:
                    continue
                label = Gtk.Label()
            for block in page.get("blocks", []):
                text = (
                    block.get("original", "")
                    if self.show_original_overlay
                    else block.get("translated", "")
                ).strip()
                if not text:
                    continue
                label = Gtk.Label()
                label.set_markup(
                    '<span background="white" foreground="black">%s</span>'
                    % GLib.markup_escape_text(text)
                )
                label.set_wrap(True)
                label.set_xalign(0)
                label.set_valign(Gtk.Align.START)
                label.set_halign(Gtk.Align.START)
                label.add_css_class("ocr-translation")
                text_layer.put(label, 0, 0)
                labels.append(label)
            self.update_page_overlay(page_index)

    def update_page_overlay(self, page_index):
        if not self.ocr_document or page_index >= len(self.ocr_document.get("pages", [])):
            return
        page = self.ocr_document["pages"][page_index]
        container, marker, text_layer, labels = self.page_containers[page_index]
        source_width = page.get("width", 1)
        source_height = page.get("height", 1)

        self.debug_log(
            f"update_page_overlay page={page_index+1} "
            f"container=({container.get_width()}x{container.get_height()}) "
            f"source=({source_width}x{source_height}) labels={len(labels)}"
        )


        scale = min(container.get_width() / source_width, container.get_height() / source_height)
        if container.get_width() <= 0 or container.get_height() <= 0:
            GLib.idle_add(self.update_page_overlay, page_index)
            return
        offset_x = (container.get_width() - source_width * scale) / 2
        offset_y = (container.get_height() - source_height * scale) / 2
        label_index = 0
        for block in page.get("blocks", []):
            text = (
                block.get("original", "")
                if self.show_original_overlay
                else block.get("translated", "")
            ).strip()
            if not text:
                continue
            if label_index >= len(labels):
                break
            label = labels[label_index]
            label.set_size_request(
                max(1, int(block["width"] * scale)),
                max(1, int(block["height"] * scale)),
            )
            text_layer.move(
                label,
                int(offset_x + block["x"] * scale),
                int(offset_y + block["y"] * scale),
            )
            label_index += 1

    def on_page_changed(self, carousel, param_spec):
        page_number = round(carousel.get_position())
        self.current_page = page_number
        self.debug_log(
            "position=%s page=%s loaded=%s loading=%s"
            % (carousel.get_position(), page_number + 1, sorted(self.loaded_pages), sorted(self.loading_pages))
        )
        self.load_nearby_pages(page_number)
        self.update_indicator(page_number)
        self.update_favorite_button()

    def page_text(self, page_number):
        total = len(self.page_data)
        return f"{min(page_number, total)} / {total}" if total else "0 / 0"

    def update_indicator(self, page_number):
        self.page_label.set_text(self.page_text(page_number + 1))
        self.updating_indicator = True
        self.page_scale.set_value(page_number)
        self.updating_indicator = False

    def on_indicator_changed(self, scale):
        if self.updating_indicator or not self.page_data:
            return
        page_number = round(scale.get_value())
        self.debug_log("indicator target page=%s" % (page_number + 1))
        page = self.carousel.get_nth_page(page_number)
        self.carousel.scroll_to(page, True)

    def on_favorite_clicked(self, button):
        page_number = self.current_page + 1
        result = self.reader_api.toggle_favorite_page(self.chapter["id"], page_number)
        if result["favorite"]:
            self.favorite_pages.add(page_number)
        else:
            self.favorite_pages.discard(page_number)
        self.update_favorite_marker(self.current_page)
        self.update_favorite_button()
        self.update_favorite_marks()

    def update_favorite_button(self):
        page_number = self.current_page + 1
        favorite = page_number in self.favorite_pages
        self.favorite_button.set_icon_name(
            "starred-symbolic" if favorite else "non-starred-symbolic"
        )
        self.favorite_button.set_tooltip_text(
            "Remove page from favorites" if favorite else "Add page to favorites"
        )

    def update_favorite_marks(self):
        self.page_scale.clear_marks()
        for page_number in self.favorite_pages:
            self.page_scale.add_mark(
                page_number - 1,
                Gtk.PositionType.BOTTOM,
                None,
            )

    def update_favorite_marker(self, page_number):
        if 0 <= page_number < len(self.page_containers):
            self.page_containers[page_number][1].set_visible(
                page_number + 1 in self.favorite_pages
            )

    def load_nearby_pages(self, center):
        page_numbers = [center]
        if center > 0:
            page_numbers.append(center - 1)
        if center + 1 < len(self.page_data):
            page_numbers.append(center + 1)

        for page_number in page_numbers:
            if page_number in self.loaded_pages or page_number in self.loading_pages:
                continue
            if len(self.loading_pages) >= 4:
                if page_number != center:
                    self.debug_log("queue full skip neighbor page=%s" % (page_number + 1))
                    continue
                self.debug_log("queue full but prioritizing current page=%s" % (page_number + 1))
            self.loading_pages.add(page_number)
            self.debug_log(
                "queue page=%s loaded=%s loading=%s"
                % (page_number + 1, sorted(self.loaded_pages), sorted(self.loading_pages))
            )
            threading.Thread(
                target=self.load_page_in_background,
                args=(page_number,),
                daemon=True,
            ).start()

    def load_page_in_background(self, page_number):
        self.debug_log("worker waiting page=%s" % (page_number + 1))
        with self.worker_limit:
            try:
                if abs(page_number - self.current_page) > 1:
                    self.loading_pages.discard(page_number)
                    self.debug_log(
                        "discard stale page=%s current=%s"
                        % (page_number + 1, self.current_page + 1)
                    )
                    return
                self.debug_log("worker started page=%s" % (page_number + 1))
                result = self.reader_api.get_chapter_page(
                    self.chapter["id"], page_number + 1
                )
                if result is None:
                    raise RuntimeError("chapter tidak ditemukan di database")
                image_path = result.get("image_path")
                if not image_path:
                    raise RuntimeError("image_path kosong")
                cached_path = thumbnail_path(
                    image_path,
                    self.preview_width,
                    self.preview_height,
                )
                self.debug_log(
                    "page=%s source=%s cache=%s cache_hit=%s"
                    % (page_number + 1, image_path, cached_path, cached_path.exists())
                )
                if not cached_path.exists():
                    from gi.repository import GdkPixbuf
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        image_path,
                        self.preview_width,
                        self.preview_height,
                        True,
                    )
                    pixbuf.savev(str(cached_path), "png", [], [])
                    self.debug_log("thumbnail created page=%s" % (page_number + 1))
                self.debug_log("worker finished page=%s" % (page_number + 1))
                GLib.idle_add(self.show_loaded_page, page_number, str(cached_path))
            except Exception as error:
                self.debug_log("worker failed page=%s error=%s" % (page_number + 1, error))
                GLib.idle_add(self.page_load_failed, page_number, str(error))

    def show_loaded_page(self, page_number, image_path):
        if page_number in self.loaded_pages:
            return False
        image = Gtk.Picture.new_for_filename(image_path)
        image.set_content_fit(Gtk.ContentFit.CONTAIN)
        image.set_vexpand(True)
        image.set_hexpand(True)
        self.page_containers[page_number][0].set_child(image)
        GLib.idle_add(self.update_page_overlay, page_number)
        self.loaded_pages.add(page_number)
        self.loading_pages.discard(page_number)
        self.debug_log("image attached page=%s path=%s" % (page_number + 1, image_path))
        return False

    def page_load_failed(self, page_number, error):
        self.loading_pages.discard(page_number)
        self.debug_log("load failed page=%s error=%s" % (page_number + 1, error))
        print(
            f"Gagal memuat halaman {page_number + 1} "
            f"chapter {self.chapter.get('id')}: {error}"
        )
        return False

    def debug_log(self, message):
        if not self.debug_reader:
            return
        line = "[Reader] %s\n" % message
        print(line, end="", flush=True)
        with open("/tmp/hon-reader.log", "a", encoding="utf-8") as log_file:
            log_file.write(line)


