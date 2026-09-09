import json
import os
from urllib.error import HTTPError
from urllib import parse, request
from .settings import get_setting


# Aktifkan kembali saat fitur translation siap digunakan.
TRANSLATION_ENABLED = True


def is_available():
    return TRANSLATION_ENABLED and bool(
        get_setting("deepl_api_key") or os.environ.get("DEEPL_API_KEY")
    )


def translate_text(text: str, target_language: str = None):
    api_key = get_setting("deepl_api_key") or os.environ.get("DEEPL_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPL_API_KEY belum diatur")
    if not text.strip():
        return ""

    target_language = target_language or get_setting("deepl_target_lang") or os.environ.get("DEEPL_TARGET_LANG", "VI")
    configured_endpoint = os.environ.get("DEEPL_API_URL")
    if configured_endpoint:
        endpoint = configured_endpoint
    else:
        endpoint = (
            "https://api-free.deepl.com/v2/translate"
            if api_key.endswith(":fx")
            else "https://api.deepl.com/v2/translate"
        )
    payload = parse.urlencode({
        "text": text,
        "target_lang": target_language.upper(),
    }).encode("utf-8")
    request_object = request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
    )
    try:
        with request.urlopen(request_object, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"DeepL HTTP {error.code}: {details or 'permintaan ditolak'}"
        ) from error
    except Exception as error:
        raise RuntimeError(f"DeepL request gagal: {error}") from error

    translations = result.get("translations", [])
    if not translations:
        raise RuntimeError("DeepL tidak mengembalikan hasil terjemahan")
    return translations[0]["text"]


def translate_document(document):
    translated_count = 0
    for page in document.get("pages", []):
        for block in page.get("blocks", []):
            original = block.get("original", "").strip()
            if not original:
                continue
            block["translated"] = translate_text(original)
            translated_count += 1
    return translated_count