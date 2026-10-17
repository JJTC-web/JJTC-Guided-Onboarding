"""
Year-end business return questionnaire and scope rules.

The client answers a short set of plain-language questions. assess() turns
those answers into:
  - the base return fee for their entity type
  - any add-on services their answers trigger (with quantities)
  - the document checklist they need to upload to their portal
  - notes for the preparer (things to watch, no fee attached)

Prices come from pricing.py. Letter wording comes from engagement_clauses.py.
This file only decides WHAT applies, never what it costs or how it's worded.

Question wording rule: keep every question neutral and factual. "Did the
business account pay for anything personal?" gets honest answers. Anything
that sounds like an accusation gets undercounted.
"""

import pricing

ENTITY_TYPES = {
    "s_corp": "S corporation (Form 1120-S)",
    "partnership": "Partnership or multi-member LLC (Form 1065)",
    "c_corp": "C corporation (Form 1120)",
    "schedule_c": "Single-owner business on your personal return (Schedule C)",
}

# Labels for every service code the year-end letter can include.
SERVICE_LABELS = {
    "TAX-PREP": "Business Tax Return Preparation",
    "CLEANUP": "Bookkeeping Cleanup and Reconciliation",
    "DIST-RECLASS": "Owner Distribution and Personal Expense Reclassification",
    "PRIOR-YEAR-REVIEW": "Prior-Year Balance Review and Correction",
    "INVENTORY": "Inventory Reconciliation",
    "RC-REVIEW": "Reasonable Compensation Review",
    "ASSETS": "Fixed Asset and Depreciation Setup",
    "NOTICE": "IRS or State Notice Review and Response",
}

# Each question:
#   id        - key stored in the answers
#   text      - what the client sees
#   type      - "choice" | "yes_no" | "number"
#   options   - for "choice": list of (value, label)
#   help      - optional one-line explanation under the question
#   show_if   - optional {question_id: [values]}; question only applies when
#               every listed question has one of those values
#   max       - for "number": upper limit accepted
QUESTIONS = [
    {
        "id": "entity_type",
        "text": "What kind of business return is this?",
        "type": "choice",
        "options": list(ENTITY_TYPES.items()),
        "help": "Not sure? Pick your best guess and we'll confirm it.",
    },
    {
        "id": "books_method",
        "text": "How did the business keep track of its income and expenses this year?",
        "type": "choice",
        "options": [
            ("software", "Accounting software (QuickBooks, Xero, Wave, or similar)"),
            ("spreadsheet", "A spreadsheet"),
            ("none", "Bank statements only, or nothing set up yet"),
        ],
    },
    {
        "id": "months_unreconciled",
        "text": "How many months of the year are not yet entered and matched to your bank statements?",
        "type": "number",
        "max": 12,
        "help": "Enter 0 if every month is entered and matches the bank.",
        "show_if": {"books_method": ["software", "spreadsheet"]},
    },
    {
        "id": "all_statements",
        "text": "Do you have every bank and credit card statement for the year, including December?",
        "type": "yes_no",
    },
    {
        "id": "personal_paid",
        "text": "Did the business account pay for anything personal, like household bills, family expenses, or personal shopping?",
        "type": "yes_no",
        "help": "This is common and easy to handle. We just need to know so we record it correctly.",
    },
    {
        "id": "owner_on_payroll",
        "text": "Were you (the owner) paid wages through payroll by this business?",
        "type": "yes_no",
        "show_if": {"entity_type": ["s_corp", "c_corp"]},
    },
    {
        "id": "other_businesses",
        "text": "How many other businesses do you own?",
        "type": "number",
        "max": 50,
        "help": "Enter 0 if this is your only business.",
    },
    {
        "id": "prior_preparer",
        "text": "Who prepared last year's return for this business?",
        "type": "choice",
        "options": [
            ("jjtc", "Jehovah Jireh Tax Consultants"),
            ("other", "Another tax preparer or CPA"),
            ("self", "I prepared it myself"),
            ("first_year", "This is the business's first year"),
        ],
    },
    {
        "id": "sells_products",
        "text": "Does the business sell products or keep inventory?",
        "type": "yes_no",
    },
    {
        "id": "inventory_count",
        "text": "Did you count your inventory at the end of the year (on or near December 31)?",
        "type": "yes_no",
        "show_if": {"sells_products": ["yes"]},
    },
    {
        "id": "new_assets",
        "text": "How many pieces of equipment, furniture, vehicles, or building improvements over $2,500 did the business buy this year?",
        "type": "number",
        "max": 100,
        "help": "Enter 0 if none.",
    },
    {
        "id": "notices",
        "text": "How many letters or notices did the business get from the IRS or the state this year?",
        "type": "number",
        "max": 50,
        "help": "Enter 0 if none. Upload a copy of each one to your portal.",
    },
    {
        "id": "has_payroll",
        "text": "Did the business run payroll for anyone (including you)?",
        "type": "yes_no",
    },
    {
        "id": "collects_sales_tax",
        "text": "Does the business collect sales tax?",
        "type": "yes_no",
    },
    {
        "id": "has_loans",
        "text": "Does the business have any loans, lines of credit, or financed equipment?",
        "type": "yes_no",
    },
]

QUESTIONS_BY_ID = {q["id"]: q for q in QUESTIONS}

BASE_DOCUMENTS = [
    "December 31 bank statement for every business account",
    "January statements for every business account (shows December bills paid in January)",
    "December 31 credit card statements",
    "Your profit and loss report and balance sheet for the year, if you keep books",
    "A list of owner draws and any personal expenses the business paid",
]


def question_applies(question, answers):
    """Whether a question's show_if conditions are met by the answers so far."""
    for other_id, allowed in question.get("show_if", {}).items():
        if answers.get(other_id) not in allowed:
            return False
    return True


def clean_answers(form):
    """
    Turns raw form input into a clean answers dict: only known questions,
    only questions that apply, numbers clamped to 0..max, choices checked
    against their options. Returns (answers, errors).
    """
    answers, errors = {}, []
    for q in QUESTIONS:
        if not question_applies(q, answers):
            continue
        raw = (form.get(q["id"]) or "").strip()
        if raw == "":
            errors.append(q["text"])
            continue
        if q["type"] == "number":
            try:
                value = int(raw)
            except ValueError:
                errors.append(q["text"])
                continue
            answers[q["id"]] = max(0, min(value, q.get("max", 999)))
        elif q["type"] == "yes_no":
            if raw not in ("yes", "no"):
                errors.append(q["text"])
                continue
            answers[q["id"]] = raw
        else:
            if raw not in {value for value, _ in q["options"]}:
                errors.append(q["text"])
                continue
            answers[q["id"]] = raw
    return answers, errors


def _add_on(code, qty, reason):
    fee = pricing.ADD_ON_FEES[code]
    unit_price = fee["price"]
    return {
        "code": code,
        "label": SERVICE_LABELS[code],
        "reason": reason,
        "qty": qty,
        "unit": fee["unit"],
        "unit_price": unit_price,
        "amount": None if unit_price is None else unit_price * qty,
    }


def assess(answers):
    """
    Applies the scope rules to a cleaned answers dict. Returns a dict with
    items (base return first), flags, documents, total and unpriced codes.
    """
    entity = answers.get("entity_type")
    items, flags = [], []

    base_price = pricing.BASE_RETURN_FEES.get(entity)
    items.append({
        "code": "TAX-PREP",
        "label": SERVICE_LABELS["TAX-PREP"],
        "reason": ENTITY_TYPES.get(entity, "Business return"),
        "qty": 1,
        "unit": "flat",
        "unit_price": base_price,
        "amount": base_price,
    })

    # Bookkeeping cleanup: unreconciled months, or no books at all.
    if answers.get("books_method") == "none":
        items.append(_add_on("CLEANUP", 12, "No bookkeeping system for the year; all 12 months need to be entered and reconciled."))
    elif answers.get("months_unreconciled", 0) > 0:
        months = answers["months_unreconciled"]
        items.append(_add_on("CLEANUP", months, f"{months} month(s) not yet entered and reconciled to the bank."))

    if answers.get("all_statements") == "no":
        flags.append("Missing bank or credit card statements. Chase these before starting; reconstructing them adds cleanup time.")

    if answers.get("personal_paid") == "yes":
        items.append(_add_on(
            "DIST-RECLASS", 1,
            "Business account paid personal expenses; these must be identified and recorded as owner distributions or draws.",
        ))

    other = answers.get("other_businesses", 0)
    if entity == "s_corp" and (answers.get("owner_on_payroll") == "no" or other > 0):
        if answers.get("owner_on_payroll") == "no":
            reason = "Owner took no W-2 wages from this S corporation."
        else:
            reason = f"Owner works across {other + 1} businesses; wages here need to be supportable."
        items.append(_add_on("RC-REVIEW", 1, reason))
    if other > 0:
        flags.append(
            f"Owner has {other} other business(es). Each one needs its own questionnaire and engagement letter."
        )

    if answers.get("prior_preparer") in ("other", "self"):
        who = "another preparer" if answers["prior_preparer"] == "other" else "the owner"
        items.append(_add_on(
            "PRIOR-YEAR-REVIEW", 1,
            f"Last year's return was prepared by {who}; opening balances must be reviewed before they can be relied on.",
        ))

    if answers.get("sells_products") == "yes" and answers.get("inventory_count") == "no":
        items.append(_add_on("INVENTORY", 1, "Business keeps inventory but has no year-end count."))

    if answers.get("new_assets", 0) > 0:
        n = answers["new_assets"]
        items.append(_add_on("ASSETS", n, f"{n} new asset(s) to add to the depreciation schedule."))

    if answers.get("notices", 0) > 0:
        n = answers["notices"]
        items.append(_add_on("NOTICE", n, f"{n} IRS or state notice(s) to review and answer."))

    documents = list(BASE_DOCUMENTS)
    if answers.get("prior_preparer") != "jjtc" and answers.get("prior_preparer") != "first_year":
        documents.append("Last year's complete business tax return, including the balance sheet (Schedule L)")
    if answers.get("sells_products") == "yes":
        documents.append("Year-end inventory count, or your best list of what was on hand December 31")
    if answers.get("new_assets", 0) > 0:
        documents.append("Receipts or invoices for each equipment, vehicle, or improvement purchase")
    if answers.get("has_payroll") == "yes":
        documents.append("Payroll reports: W-2s, W-3, all four quarterly Forms 941, and state unemployment returns")
    if answers.get("collects_sales_tax") == "yes":
        documents.append("Sales tax returns for the year, including December")
    if answers.get("has_loans") == "yes":
        documents.append("December 31 loan and line-of-credit statements")
    if answers.get("notices", 0) > 0:
        documents.append("A copy of every IRS or state notice")

    unpriced = [i["code"] for i in items if i["unit_price"] is None]
    total = None if unpriced else sum(i["amount"] for i in items)

    return {
        "entity_type": entity,
        "items": items,
        "flags": flags,
        "documents": documents,
        "total": total,
        "unpriced": unpriced,
    }


def reprice(scope):
    """
    Recomputes amounts and totals for a scope after the preparer edits
    quantities or removes items on the review page. Uses each item's own
    unit_price, so a letter already priced keeps its prices.
    """
    for item in scope["items"]:
        item["amount"] = None if item["unit_price"] is None else item["unit_price"] * item["qty"]
    scope["unpriced"] = [i["code"] for i in scope["items"] if i["unit_price"] is None]
    scope["total"] = None if scope["unpriced"] else sum(i["amount"] for i in scope["items"])
    return scope


def refresh_prices(scope):
    """
    Pulls current prices from pricing.py into a scope that hasn't been sent
    yet, so setting a price after a client submits still updates their
    draft letter. Never call this on a letter that was already sent.
    """
    for item in scope["items"]:
        if item["code"] == "TAX-PREP":
            item["unit_price"] = pricing.BASE_RETURN_FEES.get(scope.get("entity_type"))
        elif item["code"] in pricing.ADD_ON_FEES:
            item["unit_price"] = pricing.ADD_ON_FEES[item["code"]]["price"]
    return reprice(scope)


def format_money(value):
    if value is None:
        return "Price not set"
    if value == 0:
        return "Included"
    return f"${value:,.2f}"


# Onboarding situations (situations.SITUATIONS) treated as business clients:
# at annual re-engagement they get this questionnaire instead of a flat
# TAX-PREP renewal letter.
BUSINESS_SITUATIONS = ("existing_business", "payroll", "startup")
