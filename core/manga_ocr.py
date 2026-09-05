import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import threading


_ocr_instance = None
_ocr_lock = threading.Lock()


def is_available():
    try:
        from manga_ocr import MangaOcr  # noqa: F401
    except ImportError:
        return False
    return True


def recognize(image_path: str):
    global _ocr_instance

    try:
        from manga_ocr import MangaOcr
    except ImportError as error:
        raise RuntimeError(
            "manga-ocr belum terpasang. Jalankan: pip install manga-ocr"
        ) from error

    if _ocr_instance is None:
        with _ocr_lock:
            if _ocr_instance is None:
                _ocr_instance = MangaOcr()

    return _ocr_instance(image_path)

def recognize_crop(image_path: str, box):
    from PIL import Image

    image = Image.open(image_path).convert("RGB")
    crop = image.crop(box)
    with tempfile.NamedTemporaryFile(suffix=".png") as temporary_file:
        crop.save(temporary_file.name)
        return recognize(temporary_file.name)


def recognize_all(page_paths):
    workspace = Path(__file__).resolve().parent.parent
    ocr_python = workspace / ".venv-ocr" / "bin" / "python"
    if not ocr_python.exists():
        raise RuntimeError("Environment OCR tidak ditemukan di .venv-ocr")

    with tempfile.TemporaryDirectory(prefix="hon-ocr-") as directory:
        directory = Path(directory)
        paths_file = directory / "paths.json"
        output_file = directory / "pages.json"
        paths_file.write_text(json.dumps(page_paths), encoding="utf-8")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(workspace)
        process = subprocess.run(
            [
                str(ocr_python), str(workspace / "core" / "ocr_pipeline.py"),
                "--paths", str(paths_file), "--output", str(output_file),
            ],
            cwd=str(workspace),
            env=environment,
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            details = process.stderr.strip() or process.stdout.strip()
            raise RuntimeError(f"OCR pipeline gagal: {details}")
        if not output_file.exists():
            details = process.stderr.strip() or "pipeline selesai tanpa membuat output"
            raise RuntimeError(f"OCR pipeline tidak menghasilkan JSON: {details}")
        return json.loads(output_file.read_text(encoding="utf-8"))