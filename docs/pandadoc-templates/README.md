# PandaDoc Master Templates

These are the two foundational documents every client signs during
onboarding — everything in `docs/pandadoc-addenda/` refers back to the
Engagement Letter by client name and date. Build these two first.

## What's here

| File | Service code / step | Env var | Onboarding step it powers |
|---|---|---|---|
| `engagement-letter.md` | `TAX-PREP` | `PANDADOC_ENGAGEMENT_LETTER_TEMPLATE_ID` | "Sign Engagement Letter" (`engagement_letter`) — every situation |
| `records-release-authorization.md` | n/a (not a billable service code) | `PANDADOC_RECORDS_RELEASE_TEMPLATE_ID` | "Records Release Authorization" (`records_release`) — Switching Accountants only |

## How to turn a draft into a working template

Same process as `docs/pandadoc-addenda/`:

1. In PandaDoc: **Templates → New Template**, paste the draft's body in.
2. Turn every `[Bracketed]` placeholder into a PandaDoc **Field** or
   **Token**:
   - `[Client Full Name]` / `[Business Name, if applicable]` → bind to the
     **Client** recipient role's name token (the role
     `create_document_from_template()` in `integrations/pandadoc.py`
     assigns the client to).
   - `[Date]`, `[Tax Year]`, fee blanks, `[Prior Accountant / Firm Name]`,
     etc. → editable **Fields** staff fill in per client before sending.
   - `[Date]` next to each signature → PandaDoc's built-in **Date Signed**
     field.
3. Add a **Signature** field for the Client role and one for the JJTC
   preparer; require both.
4. Save as a template, then copy its ID out of the URL
   (`/templates/<id>/edit`) into the matching env var above.
5. Confirm the PandaDoc webhook (Settings → API & Integrations →
   Webhooks, `document_state_changed` event) points at this app's
   `/webhooks/pandadoc/signed` route — same webhook the addenda use, no
   separate one needed. See `PANDADOC_WEBHOOK_SHARED_KEY` in
   `env.example`.

The Section 2/5 policy language quoted in `engagement-letter.md` matches
`policy.py`'s `PORTAL_DOCUMENT_POLICY` and `SCOPE_AND_PAYMENT_POLICY`
verbatim — if that wording changes in the app, update it here too so the
signed letter and the app never drift apart.
