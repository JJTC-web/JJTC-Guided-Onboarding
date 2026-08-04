"""
Canonical client-facing policy language (Section 5 of the JJTC System
Tightening spec). Shown in the portal welcome flow and progress page, and
should also be pasted into the master PandaDoc engagement letter template -
this module is the single source of truth for the wording so the app and the
signed letter never drift apart.
"""

PORTAL_DOCUMENT_POLICY = (
    "All documents for your engagement must be submitted through your Financial "
    "Cents client portal. Documents sent by email or text will not be treated as "
    "received and will not begin any turnaround timeline."
)

SCOPE_AND_PAYMENT_POLICY = (
    "Our engagement letter covers the specific services listed at signing. Any "
    "additional work — including bookkeeping, records cleanup, annual report "
    "renewals, or additional tax filings — requires a signed addendum and "
    "payment before work begins. This protects both of us: you know exactly what "
    "you're paying for, and we can give your file the attention it needs without "
    "delay."
)
