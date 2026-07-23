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
