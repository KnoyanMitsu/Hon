import gi

from gi.repository import Adw, Gtk
from pages.home import HomePage
from pages.path_folder import PathFolderPage


class Window(Adw.ApplicationWindow):
    """Jendela utama aplikasi yang berisi navigasi berbasis halaman."""

    def __init__(self, application, **kwargs):
        super().__init__(application=application, **kwargs)

        self.set_title("Hon")
        self.set_default_size(1000, 800)

        # 1. Toolbar menjadi wadah utama untuk header dan navigasi aplikasi.
        toolbar = Adw.ToolbarView()

        # 2. Header menampilkan switcher halaman pada bagian atas jendela.
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        # 3. View stack menyimpan seluruh halaman yang dapat dipilih pengguna.
        self.stack = Adw.ViewStack()
        toolbar.set_content(self.stack)

        # 4. View switcher menyediakan navigasi antarhalaman melalui header.
        self.topbar = Adw.ViewSwitcher()
        self.topbar.set_stack(self.stack)
        self.topbar.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(self.topbar)

        # 5. Switcher bar menjadi navigasi alternatif pada area bawah window.
        self.bottombar = Adw.ViewSwitcherBar()
        self.bottombar.set_stack(self.stack)
        self.bottombar.set_reveal(False)
        toolbar.add_bottom_bar(self.bottombar)

        # 6. Breakpoint mengubah navigasi agar tetap nyaman pada layar kecil.
        breakpoint = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse("max-width: 600px")
        )
        breakpoint.add_setter(self.topbar, "visible", False)
        breakpoint.add_setter(self.bottombar, "reveal", True)
        self.add_breakpoint(breakpoint)

        # 7. Daftarkan halaman Anda
        home_page = HomePage()
        pref_page = PathFolderPage()
        header.pack_end(home_page.refresh_button)
        self.page(home_page, "home", "Home", "go-home-symbolic")
        self.page(pref_page, "setting", "Settings", "preferences-system-symbolic")
        self.stack.connect("notify::visible-child", self.on_visible_child_changed, home_page.refresh_button, home_page)
        self.stack.set_visible_child_name("home")

        # --- BARU: bungkus toolbar (tab Home/Settings) sebagai root NavigationView ---
        self.nav_view = Adw.NavigationView()

        root_page = Adw.NavigationPage(child=toolbar, title="Hon")
        self.nav_view.push(root_page)

        self.set_content(self.nav_view)   # ganti dari self.set_content(toolbar)

    def page(self, content, name, title, icon_name):
        self.stack.add_titled(content, name, title)
        page = self.stack.get_page(content)
        page.set_icon_name(icon_name=icon_name)

    def on_visible_child_changed(self, stack, param_spec, refresh_button, home_page):
        refresh_button.set_visible(stack.get_visible_child() is home_page)