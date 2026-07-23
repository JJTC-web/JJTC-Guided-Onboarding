"""
Defines the ordered onboarding steps for each of the six client situations.
Each step has:
  id            - unique key used in the DB and URLs
  type          - "video" | "intake" | "esign" | "financial_cents" | "upload"
  title         - shown on the checklist
  description   - shown on the checklist and step detail page
  required_docs - only for type "upload": list of document labels required
"""

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
