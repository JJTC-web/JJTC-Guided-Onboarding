"""
PandaDoc integration for e-signature steps (Engagement Letter, Records Release)
and for the phase-specific engagement letter addenda described in Section 3
of the JJTC System Tightening spec (BOOKKEEPING, CLEANUP, ANNUAL-REPORT,
SALES-TAX). Per Section 3.3, these don't need to be full standalone letters -
short one-page addenda referencing the master engagement letter by client
name/date work fine.

Docs: https://developers.pandadoc.com/reference/about
Auth: header "Authorization: API-Key {PANDADOC_API_KEY}"

Setup required before this works live:
1. Create a PandaDoc account and build a template for each document
   (Engagement Letter, Records Release Authorization, and one addendum
   template per out-of-scope service code) in the PandaDoc template editor.
   SALES-TAX and ANNUAL-REPORT can share a single short-form template.
2. Grab each template's ID from the PandaDoc dashboard (Templates -> click template -> URL/ID).
3. Set environment variables:
   PANDADOC_API_KEY
   PANDADOC_ENGAGEMENT_LETTER_TEMPLATE_ID
   PANDADOC_RECORDS_RELEASE_TEMPLATE_ID
   PANDADOC_BOOKKEEPING_TEMPLATE_ID
   PANDADOC_CLEANUP_TEMPLATE_ID
   PANDADOC_ANNUAL_REPORT_TEMPLATE_ID
   PANDADOC_SALES_TAX_TEMPLATE_ID
4. In PandaDoc, add a webhook (Settings -> API & Integrations -> Webhooks) for
   the "document_state_changed" event pointing at this app's
   /webhooks/pandadoc/signed route, and set PANDADOC_WEBHOOK_SHARED_KEY to
   the shared key PandaDoc signs requests with so the route can verify them.
"""

import hashlib
import hmac
import os

import requests

PANDADOC_API_BASE = "https://api.pandadoc.com/public/v1"

TEMPLATE_IDS = {
    "engagement_letter": os.environ.get("PANDADOC_ENGAGEMENT_LETTER_TEMPLATE_ID"),
    "records_release": os.environ.get("PANDADOC_RECORDS_RELEASE_TEMPLATE_ID"),
}

# Phase addendum templates, keyed by service code (Section 3.1). Each of
# these is a short PandaDoc addendum referencing the master engagement
# letter, generated on demand when a client's requested work isn't covered
# by an already-signed engagement letter for the current year.
SERVICE_CODE_TEMPLATE_IDS = {
    "BOOKKEEPING": os.environ.get("PANDADOC_BOOKKEEPING_TEMPLATE_ID"),
    "CLEANUP": os.environ.get("PANDADOC_CLEANUP_TEMPLATE_ID"),
    "ANNUAL-REPORT": os.environ.get("PANDADOC_ANNUAL_REPORT_TEMPLATE_ID"),
    "SALES-TAX": os.environ.get("PANDADOC_SALES_TAX_TEMPLATE_ID"),
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


def generate_addendum(service_code, client_name, client_email):
    """
    Generates and sends a phase-specific engagement letter addendum for an
    out-of-scope service request (Section 3.2: "auto-generates a phase
    addendum in PandaDoc before the agent marks the request as 'in
    progress'"). Returns the PandaDoc document ID.
    """
    template_id = SERVICE_CODE_TEMPLATE_IDS.get(service_code)
    if not template_id:
        raise RuntimeError(f"No PandaDoc addendum template configured for service code '{service_code}'")

    payload = {
        "name": f"{service_code} Addendum - {client_name}",
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
    document_id = resp.json()["id"]

    send_resp = requests.post(
        f"{PANDADOC_API_BASE}/documents/{document_id}/send",
        json={
            "message": (
                "This additional work is outside your current engagement letter. "
                "Please review and sign this addendum so we can begin - "
                "Jehovah Jireh Tax Consultants."
            )
        },
        headers=_headers(),
    )
    send_resp.raise_for_status()

    return document_id


def verify_webhook_signature(request_body, signature_header):
    """
    Verifies an inbound PandaDoc webhook actually came from PandaDoc, using
    the shared key configured on the webhook (HMAC-SHA256 of the raw request
    body, hex-encoded). Returns True if PANDADOC_WEBHOOK_SHARED_KEY isn't
    set (local/dev use only - always set it in production).
    """
    shared_key = os.environ.get("PANDADOC_WEBHOOK_SHARED_KEY")
    if not shared_key:
        return True
    if not signature_header:
        return False
    expected = hmac.new(shared_key.encode(), request_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)
