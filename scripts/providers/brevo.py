"""Provider Brevo : lecture des contacts (abonnés + critères) et envoi transactionnel.

Variables d'environnement :
    BREVO_API_KEY       clé API v3
    BREVO_LIST_ID       id de la liste d'abonnés (créée avec le formulaire double opt-in)
    BREVO_SENDER_EMAIL  expéditeur vérifié dans Brevo
    BREVO_SENDER_NAME   nom d'affichage (défaut : jobz)
    BREVO_UNSUB_URL     URL du formulaire de désinscription hébergé par Brevo

Attributs de contact attendus (créés dans Brevo, remplis par le formulaire) :
    Q (texte), CONTRATS (texte, séparés par des virgules), REMOTE, REGION,
    EMPLOYEUR, SALAIRE_MIN (nombre), PREMIUM (booléen, posé plus tard par Stripe).
"""

from __future__ import annotations

import os
import time

import requests

BASE = "https://api.brevo.com/v3"


def _headers(api_key: str) -> dict:
    return {"api-key": api_key, "Accept": "application/json", "Content-Type": "application/json"}


def fetch_subscribers(api_key: str) -> list[dict]:
    list_id = os.environ.get("BREVO_LIST_ID", "")
    subscribers, offset = [], 0
    while True:
        url = f"{BASE}/contacts/lists/{list_id}/contacts" if list_id else f"{BASE}/contacts"
        resp = requests.get(url, headers=_headers(api_key), params={"limit": 500, "offset": offset}, timeout=30)
        resp.raise_for_status()
        contacts = resp.json().get("contacts", [])
        for contact in contacts:
            if contact.get("emailBlacklisted"):
                continue
            attrs = contact.get("attributes") or {}
            # Les critères arrivent sérialisés dans CRITERES ("Q=react|CONTRATS=CDI,CDD|...")
            # avec repli sur d'éventuels attributs séparés (migration future).
            parsed = {}
            for part in (attrs.get("CRITERES") or "").split("|"):
                if "=" in part:
                    key, _, value = part.partition("=")
                    parsed[key.strip().upper()] = value.strip()
            get = lambda key: parsed.get(key) or attrs.get(key) or ""  # noqa: E731
            subscribers.append({
                "email": contact["email"],
                "premium": bool(attrs.get("PREMIUM")),
                "criteres": {
                    "q": get("Q"),
                    "contrats": [c.strip() for c in get("CONTRATS").split(",") if c.strip()],
                    "remote": get("REMOTE"),
                    "region": get("REGION"),
                    "employeur": get("EMPLOYEUR"),
                    "salaire_min": get("SALAIRE_MIN") or 0,
                },
            })
        if len(contacts) < 500:
            return subscribers
        offset += 500


def send_transactional(api_key: str, to: str, sujet: str, html: str) -> None:
    # {{ unsubscribe }} est rendu par Brevo en lien de désinscription individuel.
    html += (
        '<p style="color:#999;font-size:11px;margin-top:24px;">'
        '<a href="{{ unsubscribe }}" style="color:#999;">Se désinscrire de ces alertes</a></p>'
    )
    payload = {
        "sender": {
            "email": os.environ["BREVO_SENDER_EMAIL"],
            "name": os.environ.get("BREVO_SENDER_NAME", "jobz"),
        },
        "to": [{"email": to}],
        "subject": sujet,
        "htmlContent": html,
    }
    resp = requests.post(f"{BASE}/smtp/email", headers=_headers(api_key), json=payload, timeout=30)
    if resp.status_code == 429:
        time.sleep(2)
        resp = requests.post(f"{BASE}/smtp/email", headers=_headers(api_key), json=payload, timeout=30)
    resp.raise_for_status()
