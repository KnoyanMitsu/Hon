import hashlib
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path


IMAGE_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


def _natural_sort_key(value: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def _cache_directory(file_path: Path):
    fingerprint = hashlib.sha256(
        f"{file_path.resolve()}:{file_path.stat().st_mtime_ns}:{file_path.stat().st_size}".encode()
    ).hexdigest()[:16]
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "hon" / "pages"
    directory = cache_root / fingerprint
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _page_result(page_number: int, image_path: Path, name: str):
    mime_type = IMAGE_EXTENSIONS.get(image_path.suffix.lower()) or mimetypes.guess_type(name)[0]
    return {
        "page": page_number,
        "name": name,
        "image_path": str(image_path),
        "mime_type": mime_type or "application/octet-stream",
    }


def _read_archive(file_path: Path):
    output_directory = _cache_directory(file_path)
    pages = []

    with zipfile.ZipFile(file_path) as archive:
        entries = [
            entry for entry in archive.infolist()
            if not entry.is_dir() and Path(entry.filename).suffix.lower() in IMAGE_EXTENSIONS
        ]
        entries.sort(key=lambda entry: _natural_sort_key(entry.filename))

        for page_number, entry in enumerate(entries, start=1):
            extension = Path(entry.filename).suffix.lower()
            output_path = output_directory / f"{page_number:05d}{extension}"
            if not output_path.exists():
                with archive.open(entry) as source, output_path.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
            pages.append(_page_result(page_number, output_path, entry.filename))

    return pages


def _archive_entries(file_path: Path):
    with zipfile.ZipFile(file_path) as archive:
        entries = [
            entry for entry in archive.infolist()
            if not entry.is_dir() and Path(entry.filename).suffix.lower() in IMAGE_EXTENSIONS
        ]
    entries.sort(key=lambda entry: _natural_sort_key(entry.filename))
    return entries


def list_pages(file_path: str):
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"File chapter tidak ditemukan: {path}")

    extension = path.suffix.lower()
    if extension in {".cbz", ".zip"}:
        entries = _archive_entries(path)
        names = [entry.filename for entry in entries]
    elif extension == ".pdf":
        result = subprocess.run(
            ["pdfinfo", str(path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        page_count = next(
            int(line.split(":", 1)[1].strip())
            for line in result.stdout.splitlines()
            if line.startswith("Pages:")
        )
        names = [f"page-{page_number}.png" for page_number in range(1, page_count + 1)]
    else:
        raise ValueError(f"Format tidak didukung: {extension}")

    return {
        "file_path": str(path),
        "format": extension.removeprefix("."),
        "total_pages": len(names),
        "pages": [
            {"page": number, "name": name}
            for number, name in enumerate(names, start=1)
        ],
    }


def read_page(file_path: str, page_number: int):
    path = Path(file_path).expanduser()
    if page_number < 1:
        raise ValueError("Nomor halaman harus dimulai dari 1")

    output_directory = _cache_directory(path)
    extension = path.suffix.lower()

    if extension in {".cbz", ".zip"}:
        entries = _archive_entries(path)
        try:
            entry = entries[page_number - 1]
        except IndexError as error:
            raise IndexError(f"Halaman tidak ditemukan: {page_number}") from error
        output_path = output_directory / f"{page_number:05d}{Path(entry.filename).suffix.lower()}"
        if not output_path.exists():
            with zipfile.ZipFile(path) as archive:
                with archive.open(entry) as source, output_path.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
        name = entry.filename
    elif extension == ".pdf":
        output_path = output_directory / f"page-{page_number}.png"
        if not output_path.exists():
            subprocess.run(
                [
                    "pdftoppm", "-png", "-r", "150", "-f", str(page_number),
                    "-l", str(page_number), "-singlefile", str(path),
                    str(output_path.with_suffix("")),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        name = output_path.name
    else:
        raise ValueError(f"Format tidak didukung: {extension}")

    return _page_result(page_number, output_path, name)


def _read_pdf(file_path: Path):
    output_directory = _cache_directory(file_path)
    marker = output_directory / ".complete"

    if not marker.exists():
        with tempfile.TemporaryDirectory(dir=output_directory) as temporary_directory:
            prefix = Path(temporary_directory) / "page"
            subprocess.run(
                ["pdftoppm", "-png", "-r", "150", str(file_path), str(prefix)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for rendered_page in sorted(Path(temporary_directory).glob("page-*.png"), key=lambda path: _natural_sort_key(path.name)):
                shutil.move(str(rendered_page), output_directory / rendered_page.name)
        marker.touch()

    rendered_pages = sorted(output_directory.glob("page-*.png"), key=lambda path: _natural_sort_key(path.name))
    return [_page_result(index, path, path.name) for index, path in enumerate(rendered_pages, start=1)]


def read_pages(file_path: str):
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"File chapter tidak ditemukan: {path}")

    extension = path.suffix.lower()
    if extension in {".cbz", ".zip"}:
        pages = _read_archive(path)
    elif extension == ".pdf":
        pages = _read_pdf(path)
    else:
        raise ValueError(f"Format tidak didukung: {extension}")

    return {
        "file_path": str(path),
        "format": extension.removeprefix("."),
        "total_pages": len(pages),
        "pages": pages,
    }