"""
PandaDoc integration for e-signature steps (Engagement Letter, Records Release).

Docs: https://developers.pandadoc.com/reference/about
Auth: header "Authorization: API-Key {PANDADOC_API_KEY}"

Setup required before this works live:
1. Create a PandaDoc account and build a template for each document
   (Engagement Letter, Records Release Authorization) in the PandaDoc template editor.
2. Grab each template's ID from the PandaDoc dashboard (Templates -> click template -> URL/ID).
3. Set environment variables:
   PANDADOC_API_KEY
   PANDADOC_ENGAGEMENT_LETTER_TEMPLATE_ID
   PANDADOC_RECORDS_RELEASE_TEMPLATE_ID
"""

import os
import requests

PANDADOC_API_BASE = "https://api.pandadoc.com/public/v1"

TEMPLATE_IDS = {
    "engagement_letter": os.environ.get("PANDADOC_ENGAGEMENT_LETTER_TEMPLATE_ID"),
    "records_release": os.environ.get("PANDADOC_RECORDS_RELEASE_TEMPLATE_ID"),
}


def _headers():
    api_key = os.environ.get("PANDADOC_API_KEY")
    if not api_key:
        raise RuntimeError("PANDADOC_API_KEY is not set")
    return {
        "Authorization": f"API-Key {api_key}",
        "Content-Type": "application/json",
    }


def create_document_from_template(step_id, client_name, client_email):
    """
    Creates a PandaDoc document from the appropriate template and sends it
    to the client for signature. Returns the PandaDoc document ID.
    """
    template_id = TEMPLATE_IDS.get(step_id)
    if not template_id:
        raise RuntimeError(f"No PandaDoc template configured for step '{step_id}'")

    payload = {
        "name": f"{step_id.replace('_', ' ').title()} - {client_name}",
        "template_uuid": template_id,
        "recipients": [
            {
                "email": client_email,
                "first_name": client_name.split(" ")[0] if client_name else "Client",
                "last_name": client_name.split(" ")[-1] if client_name and " " in client_name else "",
                "role": "Client",
            }
        ],
    }

    resp = requests.post(f"{PANDADOC_API_BASE}/documents", json=payload, headers=_headers())
    resp.raise_for_status()
    doc = resp.json()
    document_id = doc["id"]

    # Send the document for signature
    send_resp = requests.post(
        f"{PANDADOC_API_BASE}/documents/{document_id}/send",
        json={"message": "Please review and sign your document from Jehovah Jireh Tax Consultants."},
        headers=_headers(),
    )
    send_resp.raise_for_status()

    return document_id


def get_document_status(document_id):
    """
    Returns the PandaDoc document status string, e.g.
    'document.draft', 'document.sent', 'document.viewed', 'document.completed'.
    """
    resp = requests.get(f"{PANDADOC_API_BASE}/documents/{document_id}", headers=_headers())
    resp.raise_for_status()
    return resp.json().get("status")


def is_signed(document_id):
    status = get_document_status(document_id)
    return status == "document.completed"
