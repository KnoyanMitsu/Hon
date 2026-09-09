import json


def empty_document(chapter, total_pages):
    return {
        "version": 1,
        "chapter_id": chapter["id"],
        "chapter_title": chapter.get("chapter_title"),
        "total_pages": total_pages,
        "pages": [
            {"page": page_number, "blocks": []}
            for page_number in range(1, total_pages + 1)
        ],
    }


def encode(document):
    return json.dumps(document, indent=2, ensure_ascii=False)


def decode(text):
    document = json.loads(text)
    required = {"version", "chapter_id", "total_pages", "pages"}
    missing = required.difference(document)
    if missing:
        raise ValueError(f"Format OCR kurang field: {', '.join(sorted(missing))}")
    if not isinstance(document["pages"], list):
        raise ValueError("Field pages harus berupa list")
    return document