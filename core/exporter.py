"""Export halaman chapter menjadi JPG dengan teks OCR terjemahan yang di-burn ke gambar, lalu dibungkus ZIP."""
import fnmatch
import glob
import io
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Atur ukuran teks di sini (file: core/exporter.py paling atas):
EXPORT_FONT_SCALE = 0.5  # >1.0 memperbesar, <1.0 memperkecil, misal 1.5 / 2.0
EXPORT_MIN_FONT = 16  # batas bawah font (px) — naikkan kalau masih kecil
EXPORT_MAX_FONT = 26  # batas atas font (px)
# Kalau mau ukuran pasti, isi angka, misal 64. Kalau None = otomatis dari lebar gambar.
EXPORT_FIXED_FONT_SIZE = None
# Kalau mau paksa pakai font tertentu, isi path lengkapnya di sini, misal:
# "/usr/share/fonts/abattis-cantarell-vf-fonts/Cantarell-VF.otf"
# Kalau None = dicari otomatis dari font yang terpasang di sistem.
EXPORT_FONT_PATH = None


_FONT_FILE_CACHE = None  # path file font yang ketemu, di-cache supaya tidak scan disk tiap panggil
_FONT_OBJECT_CACHE = {}  # size -> objek font, di-cache per ukuran


def _find_font_file():
    """Cari file font (.ttf/.otf) yang BENAR-BENAR ada di sistem.

    PERBAIKAN: sebelumnya daftar kandidat cuma path-path DejaVu. Di
    sistem tanpa DejaVu (mis. Fedora minimal, cuma ada Cantarell,
    Adwaita Sans/Mono, Noto, Source Code Pro, dst), semua kandidat
    gagal dan kode selalu jatuh ke ImageFont.load_default() — font
    bitmap kecil yang MENGABAIKAN parameter size. Efeknya: box makin
    besar (sesuai perhitungan), tapi tulisan yang digambar tetap kecil
    terus karena font-nya sama saja setiap saat.

    Sekarang: kalau kandidat hardcoded tidak ada, cari file font apa
    saja yang benar-benar terpasang di /usr/share/fonts (atau folder
    font user), lalu prioritaskan yang enak dibaca untuk teks umum.
    """
    global _FONT_FILE_CACHE
    if _FONT_FILE_CACHE is not None:
        return _FONT_FILE_CACHE

    if EXPORT_FONT_PATH and Path(EXPORT_FONT_PATH).exists():
        _FONT_FILE_CACHE = EXPORT_FONT_PATH
        return _FONT_FILE_CACHE

    hardcoded = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]
    for path in hardcoded:
        if Path(path).exists():
            _FONT_FILE_CACHE = path
            return path

    search_roots = [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        str(Path.home() / ".fonts"),
        str(Path.home() / ".local/share/fonts"),
    ]
    all_fonts = []
    for root in search_roots:
        if Path(root).exists():
            all_fonts += glob.glob(f"{root}/**/*.ttf", recursive=True)
            all_fonts += glob.glob(f"{root}/**/*.otf", recursive=True)

    if not all_fonts:
        _FONT_FILE_CACHE = ""
        return ""

    # Urutan preferensi: font sans yang jelas dulu (dan varian Bold
    # kalau ada), baru fallback ke font apa pun yang ketemu duluan.
    # Ini cocok untuk paket font yang biasa ada di Fedora/GNOME.
    preferred_patterns = [
        "*Cantarell*Bold*",
        "*Cantarell*",
        "*NotoSans-Bold*",
        "*NotoSans*Bold*",
        "*NotoSans*",
        "*AdwaitaSans*Bold*",
        "*AdwaitaSans*",
        "*SourceCodePro*Bold*",
        "*SourceCodePro*",
    ]
    for pattern in preferred_patterns:
        for f in all_fonts:
            if fnmatch.fnmatch(Path(f).name, pattern):
                _FONT_FILE_CACHE = f
                return f

    # Tidak ada yang cocok pola di atas — pakai font pertama yang ketemu
    # saja, itu masih jauh lebih baik daripada load_default() yang kecil.
    _FONT_FILE_CACHE = all_fonts[0]
    return _FONT_FILE_CACHE


def _load_font(size: int):
    size = max(1, int(size))
    if size in _FONT_OBJECT_CACHE:
        return _FONT_OBJECT_CACHE[size]

    font = None
    path = _find_font_file()
    if path:
        try:
            font = ImageFont.truetype(path, size)
            # Kalau ini variable font (banyak paket -vf- di Fedora),
            # coba pilih instance Bold supaya lebih tebal/terbaca.
            try:
                for name in font.get_variation_names():
                    if b"bold" in name.lower() if isinstance(name, bytes) else "bold" in name.lower():
                        font.set_variation_by_name(name)
                        break
            except Exception:
                pass
        except Exception:
            font = None

    if font is None:
        # Upaya terakhir. Di Pillow >= 10.1 load_default() punya
        # parameter size (font bitmap yang bisa diskalakan); di versi
        # lama parameter ini tidak ada dan ukurannya akan tetap kecil.
        try:
            font = ImageFont.load_default(size=size)
        except TypeError:
            font = ImageFont.load_default()

    _FONT_OBJECT_CACHE[size] = font
    return font


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int):
    """Bungkus teks per kata agar muat dalam max_width."""
    words = text.split()
    if not words:
        return []
    lines = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), trial, font=font)[2]
        if width <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    # Potong kata yang terlalu panjang per karakter
    wrapped = []
    for line in lines:
        width = draw.textbbox((0, 0), line, font=font)[2]
        if width <= max_width:
            wrapped.append(line)
            continue
        chunk = ""
        for char in line:
            trial = chunk + char
            if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
                chunk = trial
            else:
                if chunk:
                    wrapped.append(chunk)
                chunk = char
        if chunk:
            wrapped.append(chunk)
    return wrapped


def _choose_readable_font(draw, text, box_width, box_height, image_width):
    """Pilih ukuran font + wrapping teks.

    PERBAIKAN: sebelumnya ukuran font hanya dihitung dari LEBAR GAMBAR,
    sama sekali tidak melihat box_height. Akibatnya untuk box hasil
    deteksi yang tinggi (mis. balon bicara besar), teks cuma jadi 1
    baris kecil nyempil di tengah box raksasa — persis kasus di
    screenshot kamu.

    Sekarang: kita cari font TERBESAR yang, kalau di-wrap selebar
    box_width, tinggi hasil wrap-nya masih <= box_height. Jadi teks
    benar-benar mengisi box, bukan cuma numpang di tengah.
    Lebar gambar tetap dipakai sebagai batas BAWAH (baseline), supaya
    box kecil seperti SFX ("Click") tetap dapat font minimal yang
    layak dibaca (box-nya nanti yang diperbesar mengikuti teks, ini
    ditangani di render_page_with_ocr).
    """
    if EXPORT_FIXED_FONT_SIZE:
        size = int(EXPORT_FIXED_FONT_SIZE)
        font = _load_font(size)
        wrap_width = max(box_width, int(box_width * 1.4))
        lines = _wrap_text(draw, text, font, max(20, wrap_width - 8))
        return size, font, lines, wrap_width

    # Baseline: ukuran minimum yang layak dibaca, dari lebar gambar.
    base = max(EXPORT_MIN_FONT, min(EXPORT_MAX_FONT, image_width // 20))
    baseline_size = int(base * EXPORT_FONT_SCALE)
    baseline_size = max(EXPORT_MIN_FONT, min(EXPORT_MAX_FONT * 2, baseline_size))

    baseline_font = _load_font(baseline_size)
    best_size = baseline_size
    best_font = baseline_font
    best_lines = _wrap_text(draw, text, baseline_font, max(20, box_width - 16))

    # Coba font lebih besar dari baseline, selama hasil wrap (selebar
    # box_width) masih muat di box_height. Cari yang terbesar.
    upper = max(baseline_size, EXPORT_MAX_FONT * 2)
    for size in range(upper, baseline_size - 1, -2):
        font = _load_font(size)
        lines = _wrap_text(draw, text, font, max(20, box_width - 16))
        if not lines:
            continue
        ascent, descent = font.getmetrics()
        line_height = ascent + descent + 2
        total_height = line_height * len(lines)
        if total_height <= max(4, box_height - 16):
            best_size, best_font, best_lines = size, font, lines
            break  # size terbesar yang muat, langsung pakai

    size, font, lines = best_size, best_font, best_lines
    if not lines:
        lines = _wrap_text(draw, text, font, max(20, box_width - 16))

    line_widths = [draw.textbbox((0, 0), line, font=font)[2] for line in lines] or [box_width]
    text_w = max(line_widths)
    wrap_width = max(box_width, text_w + 16)
    return size, font, lines, wrap_width


def render_page_with_ocr(image_path: str, blocks: list, prefer_translated: bool = True):
    """Buka gambar dan burn teks OCR ke dalamnya. Return PIL Image RGB.

    Font dipilih agar mengisi box hasil deteksi (lihat _choose_readable_font).
    Kalau teks tetap tidak muat walau sudah pakai font sebesar mungkin,
    box putih di-expand mengikuti ukuran teks dengan tetap menutupi box asli.
    """
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    for block in blocks or []:
        translated = (block.get("translated") or "").strip()
        original = (block.get("original") or "").strip()
        if prefer_translated:
            text = translated or original
        else:
            text = original or translated
        if not text:
            continue
        try:
            x = int(block.get("x", 0))
            y = int(block.get("y", 0))
            w = int(block.get("width", 0))
            h = int(block.get("height", 0))
        except (TypeError, ValueError):
            continue
        if w <= 0 or h <= 0:
            continue
        x = max(0, x)
        y = max(0, y)
        w = min(w, image.width - x)
        h = min(h, image.height - y)
        if w <= 0 or h <= 0:
            continue
        text = " ".join(text.split())

        _size, font, lines, _wrap = _choose_readable_font(draw, text, w, h, image.width)
        if not lines:
            continue
        ascent, descent = font.getmetrics()
        line_height = ascent + descent + 2
        line_widths = [draw.textbbox((0, 0), line, font=font)[2] for line in lines]
        text_w = max(line_widths) if line_widths else 0
        text_h = line_height * len(lines)
        pad_x = max(8, _size // 3)
        pad_y = max(8, _size // 3)
        exp_w = max(text_w + pad_x * 2, w)
        exp_h = max(text_h + pad_y * 2, h)
        exp_w = min(exp_w, image.width)
        exp_h = min(exp_h, image.height)
        cx = x + w // 2
        cy = y + h // 2
        exp_x = max(0, min(cx - exp_w // 2, image.width - exp_w))
        exp_y = max(0, min(cy - exp_h // 2, image.height - exp_h))
        draw.rectangle(
            [exp_x, exp_y, exp_x + exp_w, exp_y + exp_h],
            fill="white",
            outline="black",
            width=max(2, _size // 12),
        )
        cursor_y = exp_y + (exp_h - text_h) // 2
        for line in lines:
            line_width = draw.textbbox((0, 0), line, font=font)[2]
            cursor_x = exp_x + (exp_w - line_width) // 2
            draw.text((cursor_x, cursor_y), line, fill="black", font=font)
            cursor_y += line_height
    return image


def export_pages_to_zip(rendered: list, output_zip: str, quality: int = 92):
    """rendered: list of (filename, PIL.Image). Tulis sebagai JPG ke dalam ZIP."""
    output_path = Path(output_zip).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, image in rendered:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality)
            archive.writestr(filename, buffer.getvalue())
    return str(output_path)