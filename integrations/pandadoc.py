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
import time

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
#
# TAX-PREP reuses the standing engagement letter template (the same one the
# "engagement_letter" onboarding step sends) - the annual portal-compliance
# checkpoint (Section 2.2) uses this to send that year's renewal letter.
SERVICE_CODE_TEMPLATE_IDS = {
    "TAX-PREP": os.environ.get("PANDADOC_ENGAGEMENT_LETTER_TEMPLATE_ID"),
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


def _raise_for_status_with_detail(resp):
    """
    Like resp.raise_for_status(), but includes PandaDoc's actual response
    body in the error. Plain requests.HTTPError only says e.g. "400 Client
    Error: Bad Request for url: ..." - it drops the response body, which is
    where PandaDoc actually explains what's wrong (e.g. an unknown
    recipient role).
    """
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} error from PandaDoc: {resp.text}")


def _wait_for_draft(document_id, timeout_seconds=30):
    """
    PandaDoc creates documents asynchronously: a new document starts as
    'document.uploaded' and can only be sent once it reaches 'document.draft'.
    Sending too early fails, so wait (briefly) for draft first.
    """
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if get_document_status(document_id) == "document.draft":
            return
        time.sleep(1)
    raise RuntimeError(
        f"PandaDoc document {document_id} was created but wasn't ready to send after "
        f"{timeout_seconds} seconds. It's saved in PandaDoc as a draft - open it there and send it manually."
    )


def _recipient(client_name, client_email):
    return {
        "email": client_email,
        "first_name": client_name.split(" ")[0] if client_name else "Client",
        "last_name": client_name.split(" ")[-1] if client_name and " " in client_name else "",
        "role": "Client",
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
    _raise_for_status_with_detail(resp)
    doc = resp.json()
    document_id = doc["id"]
    _wait_for_draft(document_id)

    # Send the document for signature
    send_resp = requests.post(
        f"{PANDADOC_API_BASE}/documents/{document_id}/send",
        json={"message": "Please review and sign your document from Jehovah Jireh Tax Consultants."},
        headers=_headers(),
    )
    _raise_for_status_with_detail(send_resp)

    return document_id


def get_document_status(document_id):
    """
    Returns the PandaDoc document status string, e.g.
    'document.draft', 'document.sent', 'document.viewed', 'document.completed'.
    """
    resp = requests.get(f"{PANDADOC_API_BASE}/documents/{document_id}", headers=_headers())
    _raise_for_status_with_detail(resp)
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
    _raise_for_status_with_detail(resp)
    document_id = resp.json()["id"]
    _wait_for_draft(document_id)

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
    _raise_for_status_with_detail(send_resp)

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


# --- Year-end engagement letter ---------------------------------------------
# One PandaDoc template ("Year-End Engagement Letter") with:
#   - a Content Placeholder block where the approved scope clauses go. Each
#     clause in engagement_clauses.SCOPE_CLAUSES is saved once as a PandaDoc
#     Content Library Item; its ID goes in PANDADOC_CLAUSE_<CODE>.
#   - a pricing table with data merge columns Name, Description, Price, QTY.
#   - tokens [Engagement.EntityName], [Engagement.TaxYear], [Engagement.Total].
# Setup steps: docs/year-end/README.md

def _clause_env_name(service_code):
    return "PANDADOC_CLAUSE_" + service_code.replace("-", "_")


def missing_year_end_setup(service_codes):
    """Names of env vars still missing for a year-end letter with these codes."""
    needed = ["PANDADOC_API_KEY", "PANDADOC_YEAR_END_TEMPLATE_ID", "PANDADOC_YEAR_END_SCOPE_BLOCK_ID"]
    needed += [_clause_env_name(code) for code in service_codes]
    return [name for name in needed if not os.environ.get(name)]


def create_year_end_letter(client_name, client_email, entity_name, tax_year, scope, total_text):
    """
    Builds the year-end engagement letter from the PandaDoc template: the
    approved clauses for each service in scope, a pricing table row per
    service, and the client/entity/year tokens. Sends it for signature and
    returns the PandaDoc document ID.
    """
    codes = [item["code"] for item in scope["items"]]
    missing = missing_year_end_setup(codes)
    if missing:
        raise RuntimeError("PandaDoc year-end setup is incomplete. Set: " + ", ".join(missing))

    clause_items = []
    for item in scope["items"]:
        clause_items.append({
            "id": os.environ[_clause_env_name(item["code"])],
            "fields": {"Quantity": {"value": str(item["qty"])}},
        })

    rows = []
    for item in scope["items"]:
        rows.append({
            "options": {"optional": False, "qty_editable": False},
            "data": {
                "Name": item["label"],
                "Description": item.get("reason", ""),
                "Price": item["unit_price"],
                "QTY": item["qty"],
            },
        })

    payload = {
        "name": f"{tax_year} Year-End Engagement Letter - {entity_name}",
        "template_uuid": os.environ["PANDADOC_YEAR_END_TEMPLATE_ID"],
        "recipients": [_recipient(client_name, client_email)],
        "tokens": [
            {"name": "Engagement.ClientName", "value": client_name},
            {"name": "Engagement.EntityName", "value": entity_name},
            {"name": "Engagement.TaxYear", "value": str(tax_year)},
            {"name": "Engagement.Total", "value": total_text},
        ],
        "pricing_tables": [{
            "name": os.environ.get("PANDADOC_YEAR_END_PRICING_TABLE_NAME", "Pricing Table 1"),
            "data_merge": True,
            "sections": [{"title": "Services", "default": True, "rows": rows}],
        }],
        "content_placeholders": [{
            "block_id": os.environ["PANDADOC_YEAR_END_SCOPE_BLOCK_ID"],
            "content_library_items": clause_items,
        }],
    }

    resp = requests.post(f"{PANDADOC_API_BASE}/documents", json=payload, headers=_headers())
    _raise_for_status_with_detail(resp)
    document_id = resp.json()["id"]
    _wait_for_draft(document_id)

    send_resp = requests.post(
        f"{PANDADOC_API_BASE}/documents/{document_id}/send",
        json={
            "message": (
                f"Here is your {tax_year} engagement letter for {entity_name}, based on your year-end "
                "questionnaire. Please review and sign so we can get started - Jehovah Jireh Tax Consultants."
            )
        },
        headers=_headers(),
    )
    _raise_for_status_with_detail(send_resp)
    return document_id
