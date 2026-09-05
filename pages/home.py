import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, GLib
from pages.page import Page
from core.api import LibraryAPI
from pages.bookdetail import BookDetailPage

from core.paths import get_db_path
from core.images import load_thumbnail
import threading
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

        # load di background
        thread = threading.Thread(target=self.load_library_in_background)
        thread.daemon = True
        thread.start()


    def show_empty_state(self):
        status = Adw.StatusPage(
            icon_name="folder-symbolic",
            title="Belum ada buku",
            description="Tambahkan folder lewat halaman Path Folder, lalu klik Scan Library.",
        )
        self.set_content(status)

    def load_library_in_background(self):
        library = self.api.get_library()   # jalan di thread lain
        GLib.idle_add(self.on_library_loaded, library)

    def on_library_loaded(self, library):
        books = library["books"]

        if not books:
            self.show_empty_state()
        else:
            self.build_grid(books)

        return False

    
    def build_grid(self, books):
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_max_children_per_line(4)
        self.flowbox.set_min_children_per_line(2)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flowbox.set_column_spacing(16)
        self.flowbox.set_row_spacing(16)
        self.flowbox.set_margin_top(24)
        self.flowbox.set_margin_bottom(24)

        for book in books:
            card = self.create_book_card(
                title=book["title"],
                subtitle=f"{book['total_chapters']} chapters",
                image=book["cover_path"],
                book=book
            )
            self.flowbox.append(card)

        # 1. Bungkus flowbox pakai Clamp (flowbox belum punya parent -> aman)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(1200)
        clamp.set_margin_start(24)
        clamp.set_margin_end(24)
        clamp.set_child(self.flowbox)

        # 2. Clamp masuk ke ScrolledWindow
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

        bp_mobile = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse("max-width: 400px")
        )
        bp_mobile.add_setter(self.flowbox, "max-children-per-line", 2)
        bp_mobile.add_setter(clamp, "margin-start", 12)
        bp_mobile.add_setter(clamp, "margin-end", 12)
        bp_mobile.add_setter(self.flowbox, "column-spacing", 8)
        bp_mobile.add_setter(self.flowbox, "row-spacing", 8)
        bin.add_breakpoint(bp_mobile)

        self.set_content(bin)
        GLib.idle_add(self.restore_scroll_position)

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
        if not self.debug_scroll:
            return
        line = "[HomeScroll] %s\n" % message
        print(line, end="", flush=True)
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