import threading
from PIL import Image
from gi.repository import Gio, Gtk, GLib


class ReaderPageOCRMixin:
    """Mixin class for ReaderPage containing Manga OCR, DeepL translation, JSON export/import, and text overlay rendering."""

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
            target=self.clear_ocr_in_background,
            daemon=True,
        ).start()

    def clear_ocr_in_background(self):
        try:
            self.reader_api.clear_ocr_document(self.chapter["id"])
            GLib.idle_add(self.on_clear_ocr_finished, None)
        except Exception as error:
            GLib.idle_add(self.on_clear_ocr_finished, str(error))

    def on_clear_ocr_finished(self, error):
        self.set_ocr_running(False)
        if error:
            print(f"Clear OCR gagal: {error}")
        else:
            self.ocr_document = None
            self.render_ocr_overlays()

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
            self.debug_log(f"page={page_index+1} jumlah blocks={len(blocks)}")
            for block in blocks:
                text = block.get("original", "").strip()
                self.debug_log(f"  block text='{text}'")
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
