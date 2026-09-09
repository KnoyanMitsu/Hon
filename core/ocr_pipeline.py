import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageEnhance


def _box_coordinates(box, width, height):
    left = max(0, int(min(point[0] for point in box)))
    top = max(0, int(min(point[1] for point in box)))
    right = min(width, int(max(point[0] for point in box)))
    bottom = min(height, int(max(point[1] for point in box)))
    return left, top, right, bottom


def _overlap(first, second):
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0, right - left) * max(0, bottom - top)
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0


def _rotated_box_to_original(box, width, height, rotation):
    points = []
    for x, y in box:
        if rotation == 90:
            points.append((width - 1 - y, x))
        else:
            points.append((y, height - 1 - x))
    return points


def recognize_pages(page_paths):
    # Saat file ini dijalankan langsung, folder core berada di depan sys.path
    # dan bisa menimpa package eksternal bernama manga_ocr.
    core_directory = str(Path(__file__).resolve().parent)
    sys.path[:] = [path for path in sys.path if Path(path or ".").resolve() != Path(core_directory)]
    import easyocr
    from manga_ocr import MangaOcr
    import numpy as np
    import torch

    detector = easyocr.Reader(["ja", "en"], gpu=torch.cuda.is_available())
    manga_ocr = MangaOcr()
    pages = []

    for page_number, page_path in enumerate(page_paths, start=1):
        image = Image.open(page_path).convert("RGB")
        width, height = image.size
        detection_sets = []
        for rotation in (0, 90, 270):
            detection_image = image.rotate(rotation, expand=True)
            if rotation:
                detection_image = detection_image.resize(
                    (detection_image.width * 2, detection_image.height * 2),
                    Image.Resampling.LANCZOS,
                )
                detection_image = ImageEnhance.Contrast(detection_image).enhance(1.25)
            detection_sets.append((detection_image, rotation))
        detections = []
        for detection_image, rotation in detection_sets:
            for box, _, confidence in detector.readtext(
                np.asarray(detection_image),
                detail=1,
                paragraph=False,
                min_size=8,
                text_threshold=0.45,
                low_text=0.25,
                link_threshold=0.25,
                width_ths=0.35,
                height_ths=0.35,
            ):
                if rotation:
                    box = [(point[0] / 2, point[1] / 2) for point in box]
                original_box = box
                if rotation:
                    original_box = _rotated_box_to_original(
                        box, width, height, rotation
                    )
                detections.append((original_box, confidence))

        blocks = []
        detected_boxes = []
        for box, confidence in detections:
            if confidence < 0.25:
                continue
            left, top, right, bottom = _box_coordinates(box, width, height)
            if right <= left or bottom <= top:
                continue
            coordinates = (left, top, right, bottom)
            if any(_overlap(coordinates, previous) > 0.7 for previous in detected_boxes):
                continue
            detected_boxes.append(coordinates)

            padding = max(4, int(min(right - left, bottom - top) * 0.08))
            crop = image.crop((
                max(0, left - padding),
                max(0, top - padding),
                min(width, right + padding),
                min(height, bottom + padding),
            ))
            text = manga_ocr(crop).strip()
            if text:
                blocks.append({
                    "x": left,
                    "y": top,
                    "width": right - left,
                    "height": bottom - top,
                    "original": text,
                    "translated": "",
                    "confidence": round(float(confidence), 4),
                })

        pages.append({
            "page": page_number,
            "width": width,
            "height": height,
            "blocks": blocks,
        })

    return pages


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--paths", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    page_paths = json.loads(Path(args.paths).read_text(encoding="utf-8"))
    pages = recognize_pages(page_paths)
    Path(args.output).write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()