# PandaDoc Addendum Templates

Section 3.1 of the JJTC System Tightening spec calls for a short-form
engagement letter addendum per out-of-scope service code. These can't be
built from code — PandaDoc templates are authored in PandaDoc's own template
editor — so this folder holds ready-to-paste drafts for each one.

## What's here

| File | Service code(s) | Env var(s) |
|---|---|---|
| `bookkeeping.md` | `BOOKKEEPING` | `PANDADOC_BOOKKEEPING_TEMPLATE_ID` |
| `cleanup.md` | `CLEANUP` | `PANDADOC_CLEANUP_TEMPLATE_ID` |
| `annual-report-and-sales-tax.md` | `ANNUAL-REPORT`, `SALES-TAX` | `PANDADOC_ANNUAL_REPORT_TEMPLATE_ID`, `PANDADOC_SALES_TAX_TEMPLATE_ID` |

`TAX-PREP` and `BACK-TAX` already have standing templates and aren't included
here.

Per Section 3.3, `ANNUAL-REPORT` and `SALES-TAX` share one document with a
checkbox for which service it covers — build it once in PandaDoc and point
both `PANDADOC_ANNUAL_REPORT_TEMPLATE_ID` and `PANDADOC_SALES_TAX_TEMPLATE_ID`
at the same template ID. Split it into two templates later if you ever want
them to diverge.

## How to turn a draft into a working template

1. In PandaDoc: **Templates → New Template**, paste the draft's body in.
2. Every `[Bracketed]` placeholder becomes a PandaDoc **Field** (Content
   Editing → Fields) or **Token** bound to the recipient/sender role, so it
   auto-fills instead of needing hand-editing per client:
   - `[Client Full Name]`, `[Client Email]` → bind to the **Client** recipient
     role's name/email token (the same role `generate_addendum()` in
     `integrations/pandadoc.py` assigns the client to when it creates the
     document).
   - `[Master Engagement Letter Date]`, `[Period(s) Covered]`,
     `[Estimated Fee]`, and similar scope-specific blanks → make these
     editable **Fields** so staff can fill them in per addendum before
     sending (or per-client via the API's `content_placeholders`/`fields`
     payload later, if you want to automate it further).
   - `[Date]` next to each signature → PandaDoc's built-in **Date Signed**
     field, not a manual field.
3. Add a **Signature** field for the Client role and an **Initials/Signature**
   field for the JJTC preparer, then set the document to require both.
4. Save as a template, open it, and copy the template ID out of the URL
   (`/templates/<id>/edit`) into the matching env var above.
5. Confirm PandaDoc's webhook (Settings → API & Integrations → Webhooks) is
   pointed at this app's `/webhooks/pandadoc/signed` route for the
   `document_state_changed` event, so a completed signature here actually
   flips the addendum to "signed" and fires the invoice — see
   `integrations/pandadoc.py` and `PANDADOC_WEBHOOK_SHARED_KEY` in
   `env.example`.

The `{{ policy.SCOPE_AND_PAYMENT_POLICY }}` and
`{{ policy.PORTAL_DOCUMENT_POLICY }}` lines quoted in each draft come
verbatim from `policy.py` — if that wording ever changes, update it there
and re-paste into these templates so the app and the signed paperwork don't
drift apart.
