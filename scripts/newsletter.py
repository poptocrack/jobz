"""Newsletter : détection des nouvelles offres, matching des critères, envoi.

Architecture en trois couches pour que le backend d'abonnés soit remplaçable
(Brevo aujourd'hui, Postgres demain) sans toucher au reste :
  1. Détection : diff des IDs d'offres vs le run précédent (data/seen_ids.json,
     reporté entre déploiements comme history.json).
  2. Matching : mêmes sémantiques que les filtres du front.
  3. Provider : get_subscribers() / send_email(), implémentés par provider.

Un abonné = {"email", "criteres": {q, contrats, remote, region, employeur,
salaire_min}, "premium": bool}.

Usage :
    python -m scripts.newsletter --dry-run     # détection + matching, aucun envoi
    python -m scripts.newsletter               # envoi réel (BREVO_API_KEY requis)
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from scripts.http_util import make_session
from scripts.normalize import norm_text

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SITE_URL = os.environ.get("SITE_URL", "https://poptocrack.github.io/jobz/")
SEEN_MAX_AGE_DAYS = 60
MAX_OFFERS_PER_EMAIL = 20


# ---------- Détection des nouvelles offres ----------

def load_jobs() -> list[dict]:
    manifest = json.loads((DATA_DIR / "manifest.json").read_text())
    jobs: list[dict] = []
    for chunk in manifest["chunks"]:
        jobs.extend(json.loads(gzip.decompress((DATA_DIR / chunk["file"]).read_bytes())))
    return jobs


def fetch_previous_seen() -> dict[str, str]:
    """IDs déjà vus -> date de première vue, depuis le déploiement précédent."""
    try:
        resp = make_session().get(SITE_URL.rstrip("/") + "/data/seen_ids.json", timeout=15)
        if resp.ok:
            return resp.json().get("ids", {})
    except Exception:  # noqa: BLE001 - premier run : tout est "déjà vu" (pas de spam initial)
        pass
    return {}


def detect_new(jobs: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """Retourne (nouvelles offres, seen mis à jour). Sans état précédent,
    aucune offre n'est 'nouvelle' (évite d'envoyer 20 000 offres au premier run)."""
    seen = fetch_previous_seen()
    today = date.today().isoformat()
    first_run = not seen

    new_jobs = [] if first_run else [j for j in jobs if j["id"] not in seen]

    cutoff = (date.today() - timedelta(days=SEEN_MAX_AGE_DAYS)).isoformat()
    updated = {jid: d for jid, d in seen.items() if d >= cutoff}
    for job in jobs:
        updated.setdefault(job["id"], today)
    return new_jobs, updated


def write_seen(seen: dict[str, str]) -> None:
    (DATA_DIR / "seen_ids.json").write_text(json.dumps({"ids": seen}))


# ---------- Matching (mêmes règles que le front) ----------

ATS_SOURCES = {"greenhouse", "lever", "ashby", "recruitee", "smartrecruiters", "workable"}


def _search_blob(job: dict) -> str:
    return norm_text(f"{job['titre']} {job['entreprise']} {job['ville']} {' '.join(job['tags'])}")


def job_matches(job: dict, criteres: dict) -> bool:
    q_terms = [norm_text(t) for t in (criteres.get("q") or "").split() if t.strip()]
    if q_terms:
        blob = _search_blob(job)
        if not all(t in blob for t in q_terms):
            return False
    contrats = criteres.get("contrats") or []
    if contrats and job["contrat"] not in contrats:
        return False
    if criteres.get("remote") and job["teletravail"] != criteres["remote"]:
        return False
    if criteres.get("region") and job["region"] != criteres["region"]:
        return False
    employeur = criteres.get("employeur")
    if employeur and (job["employeur_type"] or "inconnu") != employeur:
        return False
    salaire_min = int(criteres.get("salaire_min") or 0) * 1000
    if salaire_min and (job["salaire_max"] or job["salaire_min"] or 0) < salaire_min:
        return False
    return True


# ---------- Rendu de l'email ----------

def _fmt_salary(job: dict) -> str:
    if job.get("tjm_min") or job.get("tjm_max"):
        lo, hi = job.get("tjm_min"), job.get("tjm_max")
        return f"{lo}–{hi} €/j" if lo and hi and lo != hi else f"{lo or hi} €/j"
    lo, hi = job.get("salaire_min"), job.get("salaire_max")
    if lo and hi and lo != hi:
        return f"{lo // 1000}–{hi // 1000} k€"
    if lo or hi:
        return f"{(lo or hi) // 1000} k€"
    return ""


def render_email(matches: list[dict], criteres: dict) -> tuple[str, str]:
    """Retourne (sujet, html)."""
    n = len(matches)
    shown = matches[:MAX_OFFERS_PER_EMAIL]
    label = criteres.get("q") or "votre recherche"
    sujet = f"{n} nouvelle{'s' if n > 1 else ''} offre{'s' if n > 1 else ''} pour « {label} »"

    rows = []
    for job in shown:
        details = " · ".join(filter(None, [
            job["ville"], job["contrat"],
            {"total": "Full remote", "hybride": "Hybride"}.get(job["teletravail"], ""),
            _fmt_salary(job),
            {"client final": "Client final", "esn": "ESN / conseil"}.get(job["employeur_type"], ""),
        ]))
        rows.append(
            f'<tr><td style="padding:10px 0;border-bottom:1px solid #e5e5e0;">'
            f'<a href="{job["url"]}" style="color:#0f4bb8;font-weight:600;text-decoration:none;">{job["titre"]}</a>'
            f'<div style="color:#444;font-size:13px;margin-top:2px;"><strong>{job["entreprise"]}</strong>'
            f'{" · " + details if details else ""}</div></td></tr>'
        )
    more = ""
    if n > len(shown):
        more = f'<p style="color:#666;font-size:13px;">+ {n - len(shown)} autres offres sur le site.</p>'

    html = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:600px;margin:0 auto;padding:16px;">
<p style="font-size:14px;color:#444;">Nouvelles offres correspondant à vos critères,
<strong>en avant-première</strong> (en ligne sur le site dans 1&nbsp;heure) :</p>
<table style="width:100%;border-collapse:collapse;">{''.join(rows)}</table>
{more}
<p style="margin-top:20px;"><a href="{SITE_URL}" style="color:#0f4bb8;">Voir toutes les offres sur jobz</a></p>
</div>"""
    return sujet, html


# ---------- Providers ----------

def get_subscribers() -> list[dict]:
    """Backend actuel : Brevo. Remplaçable par une base de données plus tard."""
    api_key = os.environ.get("BREVO_API_KEY", "")
    if not api_key:
        return []
    from scripts.providers.brevo import fetch_subscribers
    return fetch_subscribers(api_key)


def send_email(to: str, sujet: str, html: str) -> None:
    from scripts.providers.brevo import send_transactional
    send_transactional(os.environ["BREVO_API_KEY"], to, sujet, html)


# ---------- Orchestration ----------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="détection et matching sans envoi")
    args = parser.parse_args()

    jobs = load_jobs()
    new_jobs, seen = detect_new(jobs)
    write_seen(seen)
    print(f"Newsletter : {len(new_jobs)} nouvelles offres depuis le dernier run", file=sys.stderr)
    if not new_jobs:
        return

    subscribers = get_subscribers()
    if not subscribers and not args.dry_run:
        print("Newsletter : aucun abonné (ou BREVO_API_KEY absent), rien à envoyer.", file=sys.stderr)
        return

    sent = 0
    for sub in subscribers:
        matches = [j for j in new_jobs if job_matches(j, sub["criteres"])]
        if not matches:
            continue
        matches.sort(key=lambda j: (j["employeur_type"] != "client final", -(j["salaire_max"] or 0)))
        sujet, html = render_email(matches, sub["criteres"])
        if args.dry_run:
            print(f"  [dry-run] {sub['email']} <- {len(matches)} offres : {sujet}", file=sys.stderr)
        else:
            send_email(sub["email"], sujet, html)
        sent += 1
    mode = "simulé(s)" if args.dry_run else "envoyé(s)"
    print(f"Newsletter : {sent} email(s) {mode} sur {len(subscribers)} abonné(s)", file=sys.stderr)


if __name__ == "__main__":
    main()
