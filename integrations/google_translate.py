"""
Google Cloud Translation (Basic v2) integration used to translate client
NPS comments into English for the admin dashboard and digest email.

Docs: https://cloud.google.com/translate/docs/reference/rest/v2/translate
Auth: API key passed as a query parameter.

Set environment variable:
   GOOGLE_TRANSLATE_API_KEY
"""

import os

import requests

TRANSLATE_API_BASE = "https://translation.googleapis.com/language/translate/v2"

LANGUAGE_NAMES = {
    "en": "English",
    "es": "Spanish",
    "ar": "Arabic",
}


def language_name(code):
    if not code:
        return None
    return LANGUAGE_NAMES.get(code, code)


def translate_to_english(text):
    """
    Translates the given text to English.
    Returns (translated_text, detected_source_language_code).
    """
    api_key = os.environ.get("GOOGLE_TRANSLATE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_TRANSLATE_API_KEY is not set")

    resp = requests.post(
        TRANSLATE_API_BASE,
        params={"key": api_key},
        json={"q": text, "target": "en", "format": "text"},
    )
    resp.raise_for_status()
    translation = resp.json()["data"]["translations"][0]
    return translation["translatedText"], translation.get("detectedSourceLanguage")
