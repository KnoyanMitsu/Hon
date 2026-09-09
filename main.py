import sys
import gi
from window import Window

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import GLib, Adw


class MyApplication(Adw.Application):
    """Mewakili aplikasi GTK utama dan mengelola jendela aplikasinya."""

    def __init__(self):
        """Menginisialisasi aplikasi dengan ID aplikasi yang unik."""
        super().__init__(application_id="my.Knoyan.Hon")


    def do_activate(self):
        """Membuat dan menampilkan jendela ketika aplikasi diaktifkan."""
        window = Window(application=self)
        window.present()


if __name__ == "__main__":
    app = MyApplication()
    app.run(sys.argv)