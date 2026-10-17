"""
Standard price points for the year-end engagement letter.

This is the ONE place to set your prices. The year-end questionnaire
(year_end.py) decides WHICH services a client needs and HOW MANY units;
this file decides WHAT EACH ONE COSTS.

How the values work:
  None  -> price not set yet. The app will build the scope, but it will NOT
           let you send the engagement letter until every price on it is set.
  0     -> included at no extra charge. Shows on the letter as "Included".
  number -> the price in US dollars.

Change a number here, redeploy, and every new letter uses it. Letters that
were already sent keep the price they were sent with.
"""

# Base fee for preparing the business return itself, by entity type.
BASE_RETURN_FEES = {
    "s_corp": 825,        # Form 1120-S - your current fee; raise it here when you're ready
    "partnership": None,  # Form 1065
    "c_corp": None,       # Form 1120
    "schedule_c": None,   # Single-owner business reported on Schedule C
}

# Add-on services the questionnaire can trigger. "unit" says what one unit
# is, so the letter can show "3 months x $___" instead of a lump sum.
ADD_ON_FEES = {
    "CLEANUP": {"unit": "month", "price": None},            # per month of unreconciled books
    "DIST-RECLASS": {"unit": "flat", "price": None},        # owner personal expenses reclassified
    "PRIOR-YEAR-REVIEW": {"unit": "flat", "price": None},   # review of another preparer's prior-year balances
    "INVENTORY": {"unit": "flat", "price": None},           # inventory reconciliation, no year-end count
    "RC-REVIEW": {"unit": "flat", "price": None},           # reasonable compensation review, per entity
    "ASSETS": {"unit": "asset", "price": None},             # per new asset added to the depreciation schedule
    "NOTICE": {"unit": "notice", "price": None},            # per IRS/state notice reviewed and answered
}

UNIT_LABELS = {
    "flat": "",
    "month": "month",
    "asset": "asset",
    "notice": "notice",
}
