# Isi simpel pages/page.py agar tidak double HeaderBar
import gi

from gi.repository import Adw


class Page(Adw.Bin):

    def __init__(self, title, **kwargs):
        super().__init__(**kwargs)
        # Biarkan kosong/hanya inisialisasi dasar karena shell-nya sudah diatur oleh window.py

    def set_content(self, child_widget):
        self.set_child(child_widget)
