import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib, Gio, GObject
from pages.page import Page
from core.api import LibraryAPI
from pages.bookdetail import BookDetailPage

from core.paths import get_db_path
from core.debug import debug_print
from core.images import load_thumbnail
import threading

class BookItem(GObject.Object):
    __gtype_name__ = "BookItem"
    def __init__(self, book):
        super().__init__()
        self.book = book

class HomePage(Page):
    def __init__(self, **kwargs):
        super().__init__("Home", **kwargs)

        self.api = LibraryAPI() 
        self.scroll_position = 0.0
        self.preserve_scroll_position = False
        self.debug_scroll = os.environ.get("HON_DEBUG_SCROLL") == "1"
        self.connect("notify::mapped", self.on_mapped)

        # tampilin spinner dulu, sementara data belum ada
        self.spinner = Adw.Spinner(halign="center", valign="center",width_request=48,height_request=48)
        self.set_content(self.spinner)
        self.refresh_button = Gtk.Button(icon_name="view-refresh-symbolic")
        self.refresh_button.set_tooltip_text("Refresh library")
        self.refresh_button.connect("clicked", self.on_refresh_clicked)
        self._visible_items = 0
        self._fps_frame_count = 0
        self._fps_last_check = None
        self._setup_count = 0
        self._bind_count = 0
        self._unbind_count = 0
        self._bound_positions = set()
        # load di background
        thread = threading.Thread(target=self.load_library_in_background)
        thread.daemon = True
        thread.start()


    def show_empty_state(self):
        status = Adw.StatusPage(
            icon_name="folder-symbolic",
            title="No one Books in this library",
            description="Add your book path in the settings page to see your book here.",
        )
        self.set_content(status)

    def load_library_in_background(self):
        library = self.api.get_library()   # jalan di thread lain
        GLib.idle_add(self.on_library_loaded, library)

    def reload(self):
        """Reload ringan tanpa scan filesystem — hanya query DB."""
        threading.Thread(target=self.load_library_in_background, daemon=True).start()

    def refresh(self):
        """Alias untuk auto-refresh dari Window."""
        self.reload()

    def on_library_loaded(self, library):
        books = library["books"]

        if not books:
            self.show_empty_state()
        else:
            self.build_grid(books)

        return False

    

    def build_grid(self, books):
        self._books = books
        self.store = Gio.ListStore.new(BookItem)
        for b in books:
            self.store.append(BookItem(b))

        selection = Gtk.SingleSelection.new(self.store)
        selection.set_autoselect(False)
        selection.set_can_unselect(True)
        self.selection = selection

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_factory_setup)
        factory.connect("bind", self._on_factory_bind)
        factory.connect("unbind", self._on_factory_unbind)

        self.gridview = Gtk.GridView.new(selection, factory)
        self.gridview.set_single_click_activate(True)
        self.gridview.connect("activate", self._on_grid_activate)
        self.gridview.set_max_columns(4)
        self.gridview.set_min_columns(2)
        self.gridview.set_valign(Gtk.Align.START)

        clamp = Adw.ClampScrollable()
        clamp.set_maximum_size(1200)
        clamp.set_child(self.gridview)

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.scrolled.set_child(clamp)
        scroll_controller = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.VERTICAL
        )
        scroll_controller.connect("scroll", self.on_user_scroll)
        self.scrolled.add_controller(scroll_controller)
        drag_controller = Gtk.GestureDrag()
        drag_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        drag_controller.connect("drag-begin", self.on_user_drag)
        self.scrolled.add_controller(drag_controller)
        adjustment = self.scrolled.get_vadjustment()
        adjustment.connect("value-changed", self.on_scroll_value_changed)
        adjustment.connect("notify::upper", self.on_scroll_size_changed)
        adjustment.connect("notify::page-size", self.on_scroll_size_changed)

        # 3. ScrolledWindow masuk ke BreakpointBin
        bin = Adw.BreakpointBin()
        bin.set_size_request(300, 200)
        bin.set_child(self.scrolled)
        bp_mobile = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 400px"))
        bp_mobile.add_setter(self.gridview, "max-columns", 2)
        bp_mobile.add_setter(self.gridview, "min-columns", 2)
        bp_mobile.add_setter(self.gridview, "margin-start", 12)
        bp_mobile.add_setter(self.gridview, "margin-end", 12)
        bin.add_breakpoint(bp_mobile)

        self.set_content(bin)
        GLib.idle_add(self.restore_scroll_position)
        #self._start_perf_tracker() 


    
    def _start_perf_tracker(self):
        if os.environ.get("DEBUG_ENABLE") != "1":
            return
        self.add_tick_callback(self._on_tick)
        GLib.timeout_add(1000, self._log_perf)

    def _on_tick(self, widget, frame_clock):
        self._fps_frame_count += 1
        return True   # True = terus jalan tiap frame, False = berhenti



    def _on_factory_setup(self, factory, list_item):
        self._setup_count += 1
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_size_request(120, 320)
        box.set_valign(Gtk.Align.START)
        box.set_margin_top(8)      # <-- tambahin ini
        box.set_margin_bottom(8)   # <-- dan ini
        box.set_margin_start(8)    # <-- dan ini
        box.set_margin_end(8)      # <-- dan ini
        thumb_box = Gtk.Box()
        thumb_box.set_size_request(120, 180)
        thumb_box.set_valign(Gtk.Align.START)
        thumb_box.set_overflow(Gtk.Overflow.HIDDEN)   # jaga-jaga, sesuai fix kemarin
        box.append(thumb_box)

        title_label = Gtk.Label(wrap=True, lines=2, ellipsize=True, xalign=0)
        title_label.add_css_class("caption-heading")
        box.append(title_label)

        subtitle_label = Gtk.Label(xalign=0)
        subtitle_label.add_css_class("caption")
        subtitle_label.add_css_class("dim-label")
        box.append(subtitle_label)

        list_item.set_child(box)
        list_item._thumb_box = thumb_box
        list_item._title = title_label
        list_item._subtitle = subtitle_label

    def _on_factory_bind(self, factory, list_item):
        position = list_item.get_position()
        self._bound_positions.add(position)
        self._bind_count += 1
        item = list_item.get_item()
        if not item:
            return
        book = item.book
        list_item._title.set_label(book["title"])
        list_item._subtitle.set_label(f"{book['total_chapters']} chapters")

        thumb_box = list_item._thumb_box
        if book.get("cover_path") and os.path.exists(book["cover_path"]):
            cover = load_thumbnail(book["cover_path"], 240, 700)
            cover.set_content_fit(Gtk.ContentFit.COVER)
            cover.set_size_request(120, 180)   # eksplisit di widget-nya sendiri, bukan cuma wrapper
        else:
            icon = Gtk.Image.new_from_icon_name("image-x-generic-symbolic")
            icon.set_pixel_size(48)
            icon.set_halign(Gtk.Align.CENTER)   # <-- tambahin ini
            icon.set_valign(Gtk.Align.CENTER)   # <-- pastiin ini juga ada
            cover = icon

        thumb_box.append(cover)
        list_item._cover = cover   # simpen referensi buat dibersihin di unbind


    def _on_factory_unbind(self, factory, list_item):
        position = list_item.get_position()
        self._bound_positions.discard(position)
        self._unbind_count += 1
        if hasattr(list_item, "_cover") and list_item._cover:
            list_item._thumb_box.remove(list_item._cover)
            list_item._cover = None

    def _log_perf(self):
        total = len(getattr(self, "_books", []))
        window_height = self.get_root().get_height() if self.get_root() else 0
        positions = sorted(self._bound_positions)
        pos_summary = f"min={positions[0]} max={positions[-1]}" if positions else "kosong"
        debug_print(
            f"[Perf:Home] fps={self._fps_frame_count} "
            f"bind={self._bind_count} unbind={self._unbind_count} "
            f"currently_bound={len(self._bound_positions)} {pos_summary} "
            f"total={total} window_h={window_height}\n"
        )
        self._fps_frame_count = 0
        return True

    def _on_grid_activate(self, gridview, position):
        item = self.store.get_item(position)
        if item:
            self.on_click_book(item.book)

    def on_refresh_clicked(self, button):
        self.refresh_button.set_sensitive(False)
        self.refresh_button.set_tooltip_text("Refreshing...")
        threading.Thread(target=self.refresh_in_background, daemon=True).start()

    def refresh_in_background(self):
        result = self.api.scan_all()
        library = self.api.get_library()
        GLib.idle_add(self.on_refresh_finished, result, library)

    def on_refresh_finished(self, result, library):
        self.refresh_button.set_sensitive(True)
        self.refresh_button.set_tooltip_text("Refresh library")
        self.build_grid(library["books"])
        return False

    def restore_scroll_position(self):
        if hasattr(self, "scrolled"):
            adjustment = self.scrolled.get_vadjustment()
            maximum = max(0, adjustment.get_upper() - adjustment.get_page_size())
            self.debug_log(
                "restore position=%s upper=%s page_size=%s maximum=%s"
                % (self.scroll_position, adjustment.get_upper(), adjustment.get_page_size(), maximum)
            )
            adjustment.set_value(min(self.scroll_position, maximum))
        return False

    def on_scroll_size_changed(self, adjustment, param_spec):
        maximum = adjustment.get_upper() - adjustment.get_page_size()
        self.debug_log(
            "size changed upper=%s page_size=%s value=%s saved=%s"
            % (adjustment.get_upper(), adjustment.get_page_size(), adjustment.get_value(), self.scroll_position)
        )
        if self.scroll_position > 0 and maximum > 0:
            adjustment.set_value(min(self.scroll_position, maximum))

    def on_scroll_value_changed(self, adjustment):
        if self.preserve_scroll_position:
            self.debug_log(
                "value ignored while preserving value=%s saved=%s"
                % (adjustment.get_value(), self.scroll_position)
            )
            GLib.idle_add(self.restore_scroll_position)
            return
        self.scroll_position = adjustment.get_value()
        self.debug_log("value changed value=%s" % self.scroll_position)

    def on_user_scroll(self, controller, delta_x, delta_y):
        if self.preserve_scroll_position:
            self.preserve_scroll_position = False
            self.debug_log("user scroll resumed; preserve disabled")
        return False

    def on_user_drag(self, gesture, start_x, start_y):
        if self.preserve_scroll_position:
            self.preserve_scroll_position = False
            self.debug_log("user drag resumed; preserve disabled")

    def debug_log(self, message):
        if not self.debug_scroll and not os.environ.get("DEBUG_ENABLE") == "1":
            return
        line = "[HomeScroll] %s\n" % message
        debug_print(line, end="")
        if self.debug_scroll:
            with open("/tmp/hon-scroll.log", "a", encoding="utf-8") as log_file:
                log_file.write(line)

    def on_mapped(self, widget, param_spec):
        self.debug_log("mapped=%s saved=%s" % (self.get_mapped(), self.scroll_position))
        if self.get_mapped():
            GLib.idle_add(self.finish_scroll_restore)

    def finish_scroll_restore(self):
        self.restore_scroll_position()
        self.preserve_scroll_position = False
        self.debug_log("restore finished value=%s" % self.scroll_position)
        return False

    def on_click_book(self, book):
        self.scroll_position = self.scrolled.get_vadjustment().get_value()
        self.preserve_scroll_position = True
        self.debug_log("book clicked id=%s value=%s" % (book.get("id"), self.scroll_position))
        # Navigasi ke halaman detail buku
        book_detail_page = BookDetailPage(book)
        nav_page = Adw.NavigationPage(child=book_detail_page, title=book["title"])
        nav_page.connect("shown", lambda page: book_detail_page.refresh()) 
        self.get_root().nav_view.push(nav_page)

    def create_book_card(self, title, subtitle, image, book):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_size_request(120, 360)

        if image and os.path.exists(image):
            cover = load_thumbnail(image, 240, 700)
            cover.set_content_fit(Gtk.ContentFit.COVER)
        else:
            cover = Gtk.Image.new_from_icon_name("image-x-generic-symbolic")
            cover.set_pixel_size(64)
            cover.set_valign(Gtk.Align.CENTER)

        cover.add_css_class("card")
        cover.set_size_request(120, 350)
        box.append(cover)

        title_label = Gtk.Label(label=title)
        title_label.set_wrap(True)
        title_label.set_lines(2)
        title_label.set_ellipsize(True)
        title_label.set_xalign(0)
        title_label.add_css_class("caption-heading")
        box.append(title_label)

        subtitle_label = Gtk.Label(label=subtitle)
        subtitle_label.set_xalign(0)
        subtitle_label.add_css_class("caption")
        subtitle_label.add_css_class("dim-label")
        box.append(subtitle_label)

        clicked = Gtk.GestureClick()
        clicked.connect("released", lambda *_: self.on_click_book(book))
        box.add_controller(clicked)

        return box