"""
Supabase Auth integration used to log into the /dashboard admin area.

Docs:
  https://supabase.com/docs/guides/auth/server-side/email-based-auth-with-pkce-flow
  https://supabase.com/docs/reference/api/introduction (PostgREST, for the admins table)

Auth:
  - Sign-in calls use the "apikey" header set to SUPABASE_ANON_KEY.
  - The admins-table lookup uses SUPABASE_SERVICE_ROLE_KEY, which bypasses
    row-level security, since this is a trusted server-side check.

Set environment variables:
   SUPABASE_URL
   SUPABASE_ANON_KEY
   SUPABASE_SERVICE_ROLE_KEY
"""

import os

import requests


def _supabase_url():
    url = os.environ.get("SUPABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_URL is not set")
    return url.rstrip("/")


def sign_in_with_password(email, password):
    """
    Authenticates against Supabase Auth. Returns the user's email on success.
    Raises RuntimeError with a user-facing message on failure.
    """
    anon_key = os.environ.get("SUPABASE_ANON_KEY")
    if not anon_key:
        raise RuntimeError("SUPABASE_ANON_KEY is not set")

    resp = requests.post(
        f"{_supabase_url()}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        json={"email": email, "password": password},
    )
    if not resp.ok:
        raise RuntimeError("Incorrect email or password.")
    return resp.json()["user"]["email"]


def is_admin(email):
    """
    Checks the `admins` table (via the service role key, bypassing RLS) for
    the given email.
    """
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not set")

    resp = requests.get(
        f"{_supabase_url()}/rest/v1/admins",
        params={"email": f"eq.{email}", "select": "email"},
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
        },
    )
    resp.raise_for_status()
    return len(resp.json()) > 0
