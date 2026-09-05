import re
from pathlib import Path
import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf

from .reader import read_page

SUPPORTED_EXT = (".pdf", ".cbz", ".zip")
COVER_NAMES = ("cover.jpg", "cover.jpeg", "cover.png", "cover.webp")


def extract_chapter_number(filename: str):
    match = re.search(r"(\d+(\.\d+)?)", filename)
    return float(match.group(1)) if match else None


def find_cover(folder: Path):
    for item in folder.iterdir():
        if item.is_file() and item.name.lower() in COVER_NAMES:
            return str(item)
    return None


def create_cover_from_first_page(folder: Path, chapters):
    existing_cover = find_cover(folder)
    if existing_cover or not chapters:
        return existing_cover

    try:
        first_page = read_page(chapters[0]["file_path"], 1)
        cover_path = folder / "cover.jpg"
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            first_page["image_path"], 600, 800, True
        )
        pixbuf.savev(str(cover_path), "jpeg", ["quality"], ["85"])
        return str(cover_path)
    except Exception:
        return None


def resolve_duplicate_numbers(chapters):
    used = set()
    for ch in chapters:
        num = ch["chapter_number"]
        if num is None:
            continue
        while num in used:
            num += 1
        ch["chapter_number"] = num
        used.add(num)
    return chapters


def scan_chapter_folders(title_folder: Path):
    chapters = []
    for chapter_folder in title_folder.iterdir():
        if not chapter_folder.is_dir():
            continue
        files = [f for f in chapter_folder.iterdir() if f.suffix.lower() in SUPPORTED_EXT]
        if not files:
            continue
        chapters.append({
            "chapter_number": extract_chapter_number(chapter_folder.name),
            "chapter_title": chapter_folder.name,
            "file_path": str(files[0]),
        })
    return chapters


def scan_flat_files(title_folder: Path):
    chapters = []
    for f in title_folder.iterdir():
        if not f.is_file() or f.suffix.lower() not in SUPPORTED_EXT:
            continue
        chapters.append({
            "chapter_number": extract_chapter_number(f.stem),
            "chapter_title": f.stem,
            "file_path": str(f),
        })
    return chapters


def scan_book_folder(title_folder: Path):
    subitems = list(title_folder.iterdir())
    has_subfolders = any(item.is_dir() for item in subitems)

    chapters = scan_chapter_folders(title_folder) if has_subfolders else scan_flat_files(title_folder)

    numbered = [c for c in chapters if c["chapter_number"] is not None]
    unnumbered = [c for c in chapters if c["chapter_number"] is None]

    numbered.sort(key=lambda c: (c["chapter_number"], c["chapter_title"]))
    numbered = resolve_duplicate_numbers(numbered)
    unnumbered.sort(key=lambda c: c["chapter_title"])

    return numbered + unnumbered


def scan_library(root_path: str):
    root = Path(root_path)
    if not root.exists():
        return []

    books = []
    for title_folder in root.iterdir():
        if not title_folder.is_dir():
            continue

        chapters = scan_book_folder(title_folder)
        if not chapters:
            continue  # book kosong -> skip

        books.append({
            "title": title_folder.name,
            "folder_path": str(title_folder),
            "cover_path": create_cover_from_first_page(title_folder, chapters),
            "chapters": chapters,
        })

    return books