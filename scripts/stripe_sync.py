"""Synchronisation Stripe -> Brevo : tague PREMIUM les contacts dont l'abonnement est actif.

Stripe est la source de vérité des paiements ; pas de webhook ni de serveur :
ce script tourne en CI (job horaire + au début de chaque collecte). Le contact
Brevo est retrouvé par email (celui utilisé au checkout Stripe).

Variables d'environnement : STRIPE_API_KEY (clé restreinte lecture abonnements
et clients suffisante), BREVO_API_KEY, BREVO_LIST_ID.
"""

from __future__ import annotations

import os
import sys

import requests

STRIPE_BASE = "https://api.stripe.com/v1"


def fetch_active_premium_emails(stripe_key: str) -> set[str]:
    """Emails des clients ayant un abonnement actif (ou en période d'essai)."""
    auth = (stripe_key, "")
    emails: set[str] = set()
    for status in ("active", "trialing"):
        params = {"status": status, "limit": 100, "expand[]": "data.customer"}
        url = f"{STRIPE_BASE}/subscriptions"
        while True:
            resp = requests.get(url, params=params, auth=auth, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            for sub in payload.get("data", []):
                customer = sub.get("customer") or {}
                email = (customer.get("email") or "").strip().lower()
                if email:
                    emails.add(email)
            if not payload.get("has_more"):
                break
            params["starting_after"] = payload["data"][-1]["id"]
    return emails


def sync() -> None:
    stripe_key = os.environ.get("STRIPE_API_KEY", "")
    brevo_key = os.environ.get("BREVO_API_KEY", "")
    if not stripe_key or not brevo_key:
        print("Sync premium : STRIPE_API_KEY/BREVO_API_KEY absents, rien à faire.", file=sys.stderr)
        return

    premium_emails = fetch_active_premium_emails(stripe_key)
    print(f"Sync premium : {len(premium_emails)} abonnement(s) Stripe actif(s)", file=sys.stderr)

    headers = {"api-key": brevo_key, "Content-Type": "application/json"}
    list_id = os.environ.get("BREVO_LIST_ID", "5")

    # Contacts existants de la liste.
    contacts, offset = [], 0
    while True:
        resp = requests.get(
            f"https://api.brevo.com/v3/contacts/lists/{list_id}/contacts",
            headers=headers, params={"limit": 500, "offset": offset}, timeout=30,
        )
        resp.raise_for_status()
        page = resp.json().get("contacts", [])
        contacts.extend(page)
        if len(page) < 500:
            break
        offset += 500

    known = {c["email"].lower() for c in contacts}
    updated = 0
    for contact in contacts:
        email = contact["email"].lower()
        is_premium = bool((contact.get("attributes") or {}).get("PREMIUM"))
        should_be = email in premium_emails
        if is_premium != should_be:
            resp = requests.put(
                f"https://api.brevo.com/v3/contacts/{requests.utils.quote(email)}",
                headers=headers, json={"attributes": {"PREMIUM": should_be}}, timeout=30,
            )
            resp.raise_for_status()
            updated += 1
            print(f"  {email} -> PREMIUM={should_be}", file=sys.stderr)

    # Payeurs Stripe sans contact : créés directement (l'alerte fait partie du
    # service acheté ; ils pourront affiner leurs critères via le formulaire).
    created = 0
    for email in premium_emails - known:
        resp = requests.post(
            "https://api.brevo.com/v3/contacts", headers=headers,
            json={"email": email, "attributes": {"PREMIUM": True}, "listIds": [int(list_id)], "updateEnabled": True},
            timeout=30,
        )
        if resp.status_code < 300:
            created += 1
            print(f"  {email} -> contact premium créé", file=sys.stderr)

    print(f"Sync premium : {updated} mis à jour, {created} créés, {len(contacts)} contacts au total", file=sys.stderr)


if __name__ == "__main__":
    sync()
