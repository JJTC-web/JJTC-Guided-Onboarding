"""
Defines the ordered onboarding steps for each of the six client situations.
Each step has:
  id            - unique key used in the DB and URLs
  type          - "video" | "intake" | "esign" | "financial_cents" | "portal_confirm" | "upload"
  title         - shown on the checklist
  description   - shown on the checklist and step detail page
  required_docs - only for type "upload": list of document labels required
"""

import os

# Service codes an engagement letter / addendum can cover (Section 3.1 of the
# JJTC System Tightening spec). TAX-PREP and BACK-TAX have a standing signed
# letter already; the rest require a phase-specific PandaDoc addendum before
# any work in that scope can start.
SERVICE_CODES = {
    "TAX-PREP": "Standard Tax Preparation",
    "BOOKKEEPING": "Bookkeeping / Transaction Categorization",
    "CLEANUP": "Records Cleanup",
    "ANNUAL-REPORT": "Annual Report Renewal",
    "SALES-TAX": "Sales Tax Return Filing",
    "BACK-TAX": "Back Tax Recovery & Resolution",
}

# Out-of-scope service codes: not covered by the standing engagement letter,
# so each one always needs its own signed addendum (Section 3.1/3.2).
OUT_OF_SCOPE_SERVICE_CODES = ("BOOKKEEPING", "CLEANUP", "ANNUAL-REPORT", "SALES-TAX")

# A single upload batch (or a Financial Cents portal upload) at or above this
# many files is flagged as "possible cleanup/bookkeeping scope" rather than
# silently filed as standard document intake (Section 2.2).
FILE_COUNT_ANOMALY_THRESHOLD = int(os.environ.get("FILE_COUNT_ANOMALY_THRESHOLD", "10"))

# Keyword -> service code mapping used when polling Financial Cents client
# portal tasks for scope-triggering requests (Section 6.5,
# `map_task_to_service_code`). Matched case-insensitively against the task
# label; first match wins.
TASK_LABEL_SERVICE_CODE_KEYWORDS = [
    ("bookkeeping", "BOOKKEEPING"),
    ("catch up", "BOOKKEEPING"),
    ("cleanup", "CLEANUP"),
    ("clean up", "CLEANUP"),
    ("annual report", "ANNUAL-REPORT"),
    ("sales tax", "SALES-TAX"),
]


def map_task_to_service_code(task_label):
    """
    Maps a Financial Cents client-portal task label (e.g. "I need help
    sorting these - bookkeeping cleanup") to a service code, or None if the
    task isn't scope-triggering. Used by the scheduled poll in
    app.check_for_scope_triggers().
    """
    if not task_label:
        return None
    label = task_label.lower()
    for keyword, service_code in TASK_LABEL_SERVICE_CODE_KEYWORDS:
        if keyword in label:
            return service_code
    return None


BASE_INTAKE = {
    "id": "intake",
    "type": "intake",
    "title": "Client Intake Form",
    "description": "Tell us about yourself and your business so we can prepare your file.",
}

BASE_ESIGN = {
    "id": "engagement_letter",
    "type": "esign",
    "title": "Sign Engagement Letter",
    "description": "Review and sign your engagement letter with Jehovah Jireh Tax Consultants.",
}

BASE_FINANCIAL_CENTS = {
    "id": "connect_financial_cents",
    "type": "financial_cents",
    "title": "Connect Financial Cents",
    "description": "Connect your Financial Cents account so we can track your invoice and payment status.",
}

BASE_PORTAL_CONFIRM = {
    "id": "portal_upload_confirmed",
    "type": "portal_confirm",
    "title": "Portal Upload Confirmed",
    "description": (
        "Documents you send by email or text aren't considered received. We confirm "
        "directly with Financial Cents that your documents were uploaded to your "
        "client portal — this step can't be checked off by hand."
    ),
}

RECORDS_RELEASE_ESIGN = {
    "id": "records_release",
    "type": "esign",
    "title": "Records Release Authorization",
    "description": "Authorize the release of your passwords, files, and Power of Attorney from your prior accountant, and confirm all open items with them are closed.",
}

SITUATIONS = {
    "startup": {
        "label": "Start-up",
        "steps": [
            BASE_INTAKE,
            BASE_ESIGN,
            BASE_FINANCIAL_CENTS,
            BASE_PORTAL_CONFIRM,
            {
                "id": "upload_formation_docs",
                "type": "upload",
                "title": "Upload Formation Documents",
                "description": "Upload your business formation documents.",
                "required_docs": ["Articles of Incorporation / Organization", "EIN Confirmation Letter"],
            },
        ],
    },
    "nonprofit": {
        "label": "Nonprofit",
        "steps": [
            BASE_INTAKE,
            BASE_ESIGN,
            BASE_FINANCIAL_CENTS,
            BASE_PORTAL_CONFIRM,
            {
                "id": "upload_nonprofit_docs",
                "type": "upload",
                "title": "Upload Governance & Formation Documents",
                "description": "Upload your nonprofit's formation and governance documents.",
                "required_docs": ["Articles of Incorporation", "501(c)(3) Determination Letter", "Bylaws"],
            },
        ],
    },
    "existing_business": {
        "label": "Existing Business",
        "steps": [
            BASE_INTAKE,
            BASE_ESIGN,
            BASE_FINANCIAL_CENTS,
            BASE_PORTAL_CONFIRM,
            {
                "id": "upload_prior_returns",
                "type": "upload",
                "title": "Upload Prior-Year Returns & Financials",
                "description": "Upload your most recent tax returns and financial statements.",
                "required_docs": ["Prior-Year Tax Return", "Current Financial Statements"],
            },
        ],
    },
    "never_filed": {
        "label": "Never Filed",
        "steps": [
            BASE_INTAKE,
            BASE_ESIGN,
            BASE_FINANCIAL_CENTS,
            BASE_PORTAL_CONFIRM,
            {
                "id": "upload_income_records",
                "type": "upload",
                "title": "Upload Available Income Records",
                "description": "Upload whatever income records you have available, even if incomplete.",
                "required_docs": ["Income Records (any available)", "Government-Issued ID"],
            },
        ],
    },
    "payroll": {
        "label": "Payroll",
        "steps": [
            BASE_INTAKE,
            BASE_ESIGN,
            BASE_FINANCIAL_CENTS,
            BASE_PORTAL_CONFIRM,
            {
                "id": "upload_payroll_docs",
                "type": "upload",
                "title": "Upload Payroll Documents",
                "description": "Upload employee and prior payroll information.",
                "required_docs": ["Employee List", "Prior Payroll Reports"],
            },
        ],
    },
    "switching_accountants": {
        "label": "Switching Accountants",
        "steps": [
            BASE_INTAKE,
            RECORDS_RELEASE_ESIGN,
            BASE_ESIGN,
            BASE_FINANCIAL_CENTS,
            BASE_PORTAL_CONFIRM,
            {
                "id": "upload_prior_returns_switch",
                "type": "upload",
                "title": "Upload Available Prior Records",
                "description": "Upload any prior-year returns or financials you already have.",
                "required_docs": ["Prior-Year Tax Return (if available)"],
            },
        ],
    },
}


def get_steps(situation_key):
    return SITUATIONS[situation_key]["steps"]


def get_step(situation_key, step_id):
    for step in get_steps(situation_key):
        if step["id"] == step_id:
            return step
    return None
