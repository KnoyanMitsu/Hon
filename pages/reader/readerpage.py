import os
import threading
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib, Gdk
from pages.page import Page
from pages.reader.reader_ocr import ReaderPageOCRMixin
from core.api import LibraryAPI
from core.images import thumbnail_path
from core.manga_ocr import is_available
from core.deepl import is_available as deepl_available




class ReaderPage(Page, ReaderPageOCRMixin):
    """Main comic/manga reader page handling Carousel layout, image loading, favorites, and history tracking."""

    def __init__(self, chapter, initial_page=None, **kwargs):
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

        if initial_page is None:
            book_id = chapter.get("book_id")
            if book_id:
                history = self.reader_api.get_book_history(book_id)
                if history and history.get("chapter_id") == chapter["id"]:
                    print("last seen")
                    initial_page = history.get("last_page")
                else:
                    print("new chapter")
                    initial_page = 1
            else:
                print("new chapter but error")
                initial_page = 1

        print(initial_page)
        self.current_page = max(0, min(initial_page - 1, len(self.page_data) - 1)) if self.page_data else 0
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

            container.set_hexpand(True)
            container.set_vexpand(True)
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
        if self.page_data and self.current_page > 0:
            target = self.carousel.get_nth_page(self.current_page)
            if target:
                self.carousel.scroll_to(target, False)

        self.load_nearby_pages(self.current_page)
        self.update_favorite_button()
        self.reader_api.record_history(self.chapter["id"], self.current_page + 1)

        toolbar_view.set_content(self.reader_overlay)

        indicator = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        indicator.set_margin_top(8)
        indicator.set_margin_bottom(8)
        indicator.set_margin_start(12)
        indicator.set_margin_end(12)

        self.page_label = Gtk.Label(label=self.page_text(self.current_page + 1))
        self.page_label.set_width_chars(len(self.page_text(len(self.page_data))))
        indicator.append(self.page_label)

        self.page_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            0,
            max(0, len(self.page_data) - 1),
            1,
        )
        self.page_scale.set_value(self.current_page)
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


    def on_page_changed(self, carousel, param_spec):
        page_number = round(carousel.get_position())
        if page_number != self.current_page:
            self.current_page = page_number
            self.reader_api.record_history(self.chapter["id"], page_number + 1)
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
                        "discard stale page=%s current Current=%s"
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
