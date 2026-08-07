"""
Financial Cents integration for the "Connect Financial Cents" step.

Docs: https://financial-cents.gitbook.io/public-api-documentation
Base URL: https://app.financial-cents.com/api/v1
Auth: this API is only available on Financial Cents' Scale Plan.
      Generate the API key from Settings inside your Financial Cents account.

Set environment variable:
   FINANCIAL_CENTS_API_KEY

Note: Financial Cents' Open API is oriented around Projects and Clients
already created inside Financial Cents (it does not have a public
"connect your account" OAuth flow for end clients). The practical pattern
used here: JJTC staff create the client's record in Financial Cents ahead
of time (or via Step "intake"), and this step confirms that record exists
and pulls its invoice/payment status to verify the step.
"""

import os
import requests

FC_API_BASE = "https://app.financial-cents.com/api/v1"


def _headers():
    api_key = os.environ.get("FINANCIAL_CENTS_API_KEY")
    if not api_key:
        raise RuntimeError("FINANCIAL_CENTS_API_KEY is not set")
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }


def find_client_by_email(email):
    """
    Searches Financial Cents clients by email to confirm the client record
    exists and is connected. Returns the client dict or None.
    """
    resp = requests.get(
        f"{FC_API_BASE}/clients",
        params={"search[field]": "email", "search[operation]": "equals", "search[value]": email},
        headers=_headers(),
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return data[0] if data else None


def get_project_status(project_id):
    """
    Returns the Financial Cents project dict, which includes invoice/payment
    related status fields used to verify the "Connect Financial Cents" step.
    """
    resp = requests.get(f"{FC_API_BASE}/projects/{project_id}", headers=_headers())
    resp.raise_for_status()
    return resp.json()


def is_connected_and_current(email):
    """
    Verification check for the onboarding step: the client must exist in
    Financial Cents (meaning the connection/record is live) to mark this
    step complete. Payment/invoice status can be layered in once JJTC's
    Financial Cents project structure per client is finalized.
    """
    client = find_client_by_email(email)
    return client is not None, client


def get_portal_upload_count(email):
    """
    "Portal Upload Confirmed" verification (Section 2.2): pulls how many
    files the client has uploaded to their Financial Cents client portal,
    instead of relying on a self-reported checkbox.

    NOTE: Financial Cents' public Open API docs do not (as of this writing)
    document a dedicated "list uploaded files/documents for a client"
    endpoint. This assumes a `/clients/{id}/documents` collection matching
    the shape of their other list endpoints (`{"data": [...]}`) - confirm
    the real endpoint against the current API docs before going live and
    adjust the request below if it differs.

    Returns (client, file_count). client is None if no Financial Cents
    record exists yet for this email.
    """
    client = find_client_by_email(email)
    if not client:
        return None, 0
    resp = requests.get(f"{FC_API_BASE}/clients/{client['id']}/documents", headers=_headers())
    resp.raise_for_status()
    documents = resp.json().get("data", [])
    return client, len(documents)


def get_completed_client_tasks(since=None):
    """
    Polls completed client-portal tasks/checklist items, used to detect
    scope-triggering requests a client makes inside their own portal (e.g.
    checking "I need help sorting these - bookkeeping cleanup") - Section
    6.5's `check_for_scope_triggers`.

    NOTE: stubbed against a plausible `/client_tasks` collection - confirm
    the real endpoint/field names against Financial Cents' current Open API
    docs before wiring this up to run on a schedule.
    """
    params = {"completed_since": since} if since else {}
    resp = requests.get(f"{FC_API_BASE}/client_tasks", params=params, headers=_headers())
    resp.raise_for_status()
    return resp.json().get("data", [])


def create_invoice_for_service(fc_client_id, service_code, description=None):
    """
    Creates an invoice for out-of-scope work once its addendum is signed
    (Section 4: "no addendum signature -> no invoice -> no work starts").

    NOTE: stubbed against a plausible `/invoices` endpoint - confirm the
    real endpoint/payload shape against Financial Cents' current Open API
    docs before wiring this up.
    """
    payload = {
        "client_id": fc_client_id,
        "description": description or f"{service_code} services",
    }
    resp = requests.post(f"{FC_API_BASE}/invoices", json=payload, headers=_headers())
    resp.raise_for_status()
    return resp.json()
