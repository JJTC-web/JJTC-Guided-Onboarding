# Year-End Questionnaire and Engagement Letter

Business clients answer a short questionnaire before their return starts.
Their answers decide what goes on their engagement letter: the base return
plus any cleanup, reclassification, or other work their situation needs.
You review the scope, adjust it if needed, and send the letter for signature
in one click. No signature and payment, no work.

## How it works

1. **Invite.** Each business gets its own questionnaire link, sent from
   **Dashboard → Year-End Engagements**. The annual re-engagement check also
   sends one automatically to every active business client (onboarding
   situation `existing_business`, `payroll` or `startup`) instead of the
   plain TAX-PREP renewal letter.
2. **Client answers.** About 15 plain-language questions. When they finish,
   they see the services their engagement will include and the exact
   documents to upload to their portal. You get an email (if `ADMIN_EMAIL`
   is set).
3. **You review.** The review page shows their answers, preparer notes,
   the services and fees, and a preview of the full letter. You can change
   quantities, remove a service, or add one.
4. **Send.** One click builds the letter in PandaDoc from your approved
   clauses and prices and emails it for signature.
5. **Signed.** The PandaDoc webhook marks every service on the letter as
   covered for the year and creates the invoice in Financial Cents.

## What triggers each service

| Client answer | Service added | Priced by |
| --- | --- | --- |
| Any business return | Business Tax Return Preparation | Entity type |
| Books not kept, or months not reconciled | Bookkeeping Cleanup and Reconciliation | Month |
| Business paid personal expenses | Owner Distribution and Personal Expense Reclassification | Flat |
| Last year's return prepared elsewhere or by the owner | Prior-Year Balance Review and Correction | Flat |
| Sells products, no year-end inventory count | Inventory Reconciliation | Flat |
| S corp owner not on payroll, or owns other businesses | Reasonable Compensation Review | Flat |
| Bought equipment, vehicles or improvements over $2,500 | Fixed Asset and Depreciation Setup | Asset |
| Received IRS or state notices | IRS or State Notice Review and Response | Notice |

Missing statements and other businesses are shown as **preparer notes**
(no fee) so you can follow up.

## Step 1: Set your prices

Open `pricing.py`. Every price is `None` (not set) except the S corporation
return at $825. Fill in a number for each one. Use `0` for anything you want
to include at no charge.

The app will not let you send a letter until every price on it is set.

## Step 2: Approve the clause wording

Open `engagement_clauses.py` and read every clause. These are the only words
that go into a year-end letter. Have your attorney or E&O insurer review them
once. Change anything you want here.

## Step 3: Build the PandaDoc template (one time)

1. **Save each clause as a Content Library Item.** In PandaDoc, go to
   **Content Library → New**, and create one item per service in
   `SCOPE_CLAUSES` (8 total). Paste in the title and text.
   - Where the text says `{qty}`, add a **Text field** named exactly
     `Quantity`.
   - Where it says `{client_name}`, `{entity_name}` or `{tax_year}`, use the
     tokens `[Engagement.ClientName]`, `[Engagement.EntityName]` and
     `[Engagement.TaxYear]`.
   - Where it says `{unit}`, type the word (month, asset, notice).
   - Copy each item's ID into its env var (table below).
2. **Create the template.** **Templates → New Template**, named
   "Year-End Engagement Letter":
   - Paste the intro, fees intro and standard terms from
     `engagement_clauses.py`, using the same tokens.
   - Add a **Content Placeholder** block where the scope clauses go. Copy its
     block ID into `PANDADOC_YEAR_END_SCOPE_BLOCK_ID`.
   - Add a **Pricing Table**. Turn on **data merge** and name its columns
     exactly `Name`, `Description`, `Price`, `QTY`. If you rename the table
     from "Pricing Table 1", put the new name in
     `PANDADOC_YEAR_END_PRICING_TABLE_NAME`.
   - Add a **Signature** and **Date Signed** field for the Client role, and
     one for JJTC.
   - Copy the template ID into `PANDADOC_YEAR_END_TEMPLATE_ID`.
3. **Test it.** Send one letter to yourself. Confirm the clauses, quantities,
   prices and names all fill in, then sign it and check that the dashboard
   shows it as signed.

The review page lists any PandaDoc settings still missing and won't send
until they're all set.

| Env var | What goes in it |
| --- | --- |
| `PANDADOC_YEAR_END_TEMPLATE_ID` | Year-End Engagement Letter template ID |
| `PANDADOC_YEAR_END_SCOPE_BLOCK_ID` | Content Placeholder block ID |
| `PANDADOC_YEAR_END_PRICING_TABLE_NAME` | Pricing table name, if not "Pricing Table 1" |
| `PANDADOC_CLAUSE_TAX_PREP` | Content Library Item ID for that clause |
| `PANDADOC_CLAUSE_CLEANUP` | " |
| `PANDADOC_CLAUSE_DIST_RECLASS` | " |
| `PANDADOC_CLAUSE_PRIOR_YEAR_REVIEW` | " |
| `PANDADOC_CLAUSE_INVENTORY` | " |
| `PANDADOC_CLAUSE_RC_REVIEW` | " |
| `PANDADOC_CLAUSE_ASSETS` | " |
| `PANDADOC_CLAUSE_NOTICE` | " |

## Step 4: Other settings

- `APP_BASE_URL`: your app's address, e.g. `https://onboarding.jjtc.info`,
  so questionnaire links in emails are correct.
- `ADMIN_EMAIL`: where "questionnaire submitted" notices go.
- `RESEND_FROM_EMAIL`: must be a verified address on your Resend domain to
  email clients.
- `YEAR_END_AUTO_SEND`: leave unset while you get comfortable. Set to `true`
  to send letters automatically when every price is set and there are no
  preparer notes. Anything with a note still waits for your review.

## Things to confirm before going live

- **PandaDoc plan.** Content Library Items and pricing tables through the
  API may depend on your PandaDoc plan. Confirm with PandaDoc.
- **Financial Cents invoices.** `create_invoice_for_service` is still a stub
  against a guessed endpoint, same as before. Confirm the real invoice
  endpoint and line-item fields with Financial Cents.
- **One letter per business.** The scope gate tracks services per client per
  year, not per business. For an owner with several companies, check the
  dashboard by business name.
