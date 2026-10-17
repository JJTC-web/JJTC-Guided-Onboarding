"""
Approved clause language for the year-end engagement letter.

These are the ONLY words the app puts in a year-end letter. The app picks
which clauses apply from the client's answers (year_end.py) and fills in
names, years and quantities, but it never writes new legal language.

Keep this file and PandaDoc in sync: each SCOPE_CLAUSES entry is also saved
as a Content Library Item in PandaDoc (see docs/year-end/README.md). If you
change wording here, paste the new wording into the matching PandaDoc item
too, so the preview you approve and the letter the client signs match.

Have your attorney or E&O insurer review this language once before going
live. After that, clients only ever see approved wording.

Placeholders in {braces} are filled automatically:
  {client_name} {entity_name} {tax_year} {qty} {unit}
"""

import policy

LETTER_TITLE = "Year-End Engagement Letter"

INTRO = (
    "This Engagement Letter (\"Agreement\") is entered into by and between "
    "Jehovah Jireh Tax Consultants (\"JJTC,\" \"we,\" \"us\") and {client_name}, "
    "on behalf of {entity_name} (\"Client,\" \"you\"), for tax year {tax_year}. "
    "The services and fees below are based on your answers to our year-end "
    "questionnaire. If what we find in your records differs materially from "
    "those answers, we will send an addendum before doing the additional work."
)

# One approved clause per service code. Title is the heading; text is the body.
SCOPE_CLAUSES = {
    "TAX-PREP": {
        "title": "Business Tax Return Preparation",
        "text": (
            "JJTC will prepare the {tax_year} federal business income tax return for "
            "{entity_name}, and the related state return where one is required, from the "
            "records you provide. This includes the balance sheet, the reconciliation of "
            "book income to taxable income, and owner schedules (such as Schedule K-1) "
            "required by the return. It does not include the additional services listed "
            "below unless they appear in this letter."
        ),
    },
    "CLEANUP": {
        "title": "Bookkeeping Cleanup and Reconciliation",
        "text": (
            "JJTC will enter, categorize and reconcile up to {qty} {unit}(s) of business "
            "transactions to your bank and credit card statements so the return can be "
            "prepared from accurate books. You agree to provide every statement for the "
            "period. If statements are missing and must be reconstructed, or the volume "
            "of transactions is substantially higher than expected, we will tell you "
            "before continuing and any additional time will be covered by an addendum."
        ),
    },
    "DIST-RECLASS": {
        "title": "Owner Distribution and Personal Expense Reclassification",
        "text": (
            "Personal expenses paid from a business account are not deductible business "
            "expenses. JJTC will identify these payments from your records and report them "
            "according to tax law, which is generally as owner distributions or draws. "
            "You agree to identify personal payments truthfully when asked. We will not "
            "report personal expenses as business expenses or omit them from the return."
        ),
    },
    "PRIOR-YEAR-REVIEW": {
        "title": "Prior-Year Balance Review and Correction",
        "text": (
            "Because last year's return was not prepared by JJTC, we will review its "
            "ending balance sheet and owner account balances against your records before "
            "using them as this year's starting point. If we find errors, we will correct "
            "the opening balances on this year's return and explain the correction to you. "
            "Amending a prior-year return is not included and would require a separate "
            "addendum."
        ),
    },
    "INVENTORY": {
        "title": "Inventory Reconciliation",
        "text": (
            "Because no year-end inventory count is available, JJTC will work with you to "
            "establish the December 31 inventory value from purchase records, sales "
            "records and your best information about goods on hand. The value used on the "
            "return will be based on the records and information you provide, and you are "
            "responsible for its accuracy."
        ),
    },
    "RC-REVIEW": {
        "title": "Reasonable Compensation Review",
        "text": (
            "Owners who work in an S corporation must be paid reasonable wages before "
            "taking distributions. JJTC will review your duties, time spent and the "
            "business's results, compare them to typical pay for similar work, and give "
            "you a written recommendation for your wages going forward. Payroll changes "
            "and any correction of prior payroll filings are not included. JJTC cannot "
            "guarantee how the IRS will view your compensation."
        ),
    },
    "ASSETS": {
        "title": "Fixed Asset and Depreciation Setup",
        "text": (
            "JJTC will add up to {qty} new {unit}(s) to the business's depreciation "
            "schedule, choose the depreciation method that fits your situation and "
            "explain the choice to you. You agree to provide the purchase receipt or "
            "invoice and the date each asset was placed in service."
        ),
    },
    "NOTICE": {
        "title": "IRS or State Notice Review and Response",
        "text": (
            "JJTC will review up to {qty} {unit}(s) the business received from the IRS or "
            "a state agency, explain what each one means, and prepare a written response "
            "where one is needed. Representation in an audit, appeal or collection matter "
            "is not included and would require a separate engagement and power of "
            "attorney."
        ),
    },
}

FEES_INTRO = (
    "Fees for the services above are listed below. An invoice will be issued once "
    "this Agreement is signed. Work begins after this Agreement is signed and the "
    "invoice is paid. JJTC reserves the right to withhold filing until all fees are "
    "paid in full."
)

STANDARD_TERMS = [
    ("Document Submission", policy.PORTAL_DOCUMENT_POLICY),
    ("Additional Services", policy.SCOPE_AND_PAYMENT_POLICY),
    (
        "Client Responsibilities",
        "You are responsible for the accuracy and completeness of the information and "
        "records you provide, and for timely responses to our requests. Delays in "
        "receiving your records may delay filing. JJTC is not responsible for penalties "
        "or interest caused by late or incomplete information.",
    ),
    (
        "Confidentiality",
        "JJTC will keep your information confidential and will not disclose it except "
        "as needed to perform these services or as required by law.",
    ),
    (
        "Limitation of Liability",
        "JJTC's liability for any claim arising from this engagement is limited to the "
        "fees paid for the services giving rise to the claim.",
    ),
    (
        "Term",
        "This Agreement covers tax year {tax_year} only. Services for a later year "
        "require a new signed engagement letter.",
    ),
]


def _fill(text, **values):
    return text.format(**values)


def build_letter(scope, client_name, entity_name, tax_year):
    """
    Assembles the letter preview from approved clauses only. Returns a dict
    the review template renders, and that matches what PandaDoc assembles
    from the same clauses saved as Content Library Items.
    """
    from pricing import UNIT_LABELS
    from year_end import format_money

    base = {"client_name": client_name, "entity_name": entity_name, "tax_year": tax_year}
    scope_sections = []
    for item in scope["items"]:
        clause = SCOPE_CLAUSES[item["code"]]
        scope_sections.append({
            "code": item["code"],
            "title": clause["title"],
            "text": _fill(clause["text"], qty=item["qty"], unit=UNIT_LABELS.get(item["unit"], ""), **base),
        })

    fee_rows = []
    for item in scope["items"]:
        unit = UNIT_LABELS.get(item["unit"], "")
        qty_text = f"{item['qty']} {unit}(s) x {format_money(item['unit_price'])}" if unit else ""
        fee_rows.append({
            "label": item["label"],
            "detail": qty_text,
            "amount": format_money(item["amount"]),
        })

    return {
        "title": LETTER_TITLE,
        "intro": _fill(INTRO, **base),
        "scope": scope_sections,
        "fees_intro": FEES_INTRO,
        "fee_rows": fee_rows,
        "total": format_money(scope["total"]),
        "terms": [(title, _fill(text, **base)) for title, text in STANDARD_TERMS],
    }
