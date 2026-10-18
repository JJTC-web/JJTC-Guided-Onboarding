"""
Resend integration used to email the NPS digest to the admin.

Docs: https://resend.com/docs/api-reference/emails/send-email
Auth: header "Authorization: Bearer {RESEND_API_KEY}"

Set environment variables:
   RESEND_API_KEY
   RESEND_FROM_EMAIL   (defaults to Resend's onboarding@resend.dev test sender)
"""

import os
from html import escape

import requests

from integrations import google_translate

RESEND_API_BASE = "https://api.resend.com"


def _headers():
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not set")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def send_email(to, subject, html):
    from_email = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")
    payload = {
        "from": from_email,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    resp = requests.post(f"{RESEND_API_BASE}/emails", json=payload, headers=_headers())
    if not resp.ok:
        raise RuntimeError(f"Resend API error {resp.status_code}: {resp.text}")
    return resp.json()


def send_nps_digest(summary, to_email):
    """
    Emails the current NPS summary (score, response count, and the three
    most recent comments) to the given admin address.
    """
    if summary["recent_comments"]:
        items = []
        for c in summary["recent_comments"]:
            text = escape(c.get("comment_en") or c["comment"])
            note = ""
            lang = c.get("comment_lang")
            if lang and lang != "en":
                lang_name = escape(google_translate.language_name(lang))
                original = escape(c["comment"])
                note = f' <em>(translated from {lang_name}; original: &ldquo;{original}&rdquo;)</em>'
            items.append(f"<li><strong>{c['score']}/10</strong> &mdash; {text}{note}</li>")
        comments_html = "".join(items)
    else:
        comments_html = "<li>No comments yet.</li>"

    html = f"""
    <h2>NPS Digest &mdash; JJTC Guided Onboarding</h2>
    <p><strong>NPS Score:</strong> {summary['score']}</p>
    <p><strong>Responses:</strong> {summary['response_count']}</p>
    <p><strong>Most recent comments:</strong></p>
    <ul>{comments_html}</ul>
    """

    return send_email(to=to_email, subject="NPS Digest - JJTC Guided Onboarding", html=html)


def send_year_end_invite(to, client_name, entity_name, tax_year, link):
    """Emails a client their year-end questionnaire link."""
    first = escape((client_name or "there").split(" ")[0])
    html = f"""
    <p>Hi {first},</p>
    <p>It's time to get your {tax_year} business return started for <strong>{escape(entity_name)}</strong>.</p>
    <p>Please answer a few quick questions about your business year. It takes about five minutes,
    and it tells us exactly what your return will need so there are no surprises later.</p>
    <p><a href="{escape(link)}">Start your year-end questionnaire</a></p>
    <p>Once you're done, we'll send your engagement letter for signature and a list of the
    documents to upload to your client portal.</p>
    <p>Lady Emily<br>Jehovah Jireh Tax Consultants<br><em>Your Vision Is Our Mission.</em></p>
    """
    return send_email(to=to, subject=f"Your {tax_year} year-end questionnaire for {entity_name}", html=html)


def send_year_end_submitted_notice(to, client_name, entity_name, tax_year, review_link, flags):
    """Tells the admin a client finished the questionnaire and their letter is ready to review."""
    flags_html = "".join(f"<li>{escape(f)}</li>" for f in flags) or "<li>None</li>"
    html = f"""
    <p><strong>{escape(client_name or 'A client')}</strong> finished the {tax_year} year-end questionnaire
    for <strong>{escape(entity_name)}</strong>.</p>
    <p>Preparer notes:</p>
    <ul>{flags_html}</ul>
    <p><a href="{escape(review_link)}">Review scope and send the engagement letter</a></p>
    """
    return send_email(to=to, subject=f"Year-end questionnaire submitted: {entity_name}", html=html)
