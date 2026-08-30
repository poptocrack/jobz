"""Source Adzuna — API officielle (developer.adzuna.com), marché France, catégorie IT.

Variables d'environnement requises : ADZUNA_APP_ID, ADZUNA_APP_KEY.
Le palier gratuit est limité (quelques centaines d'appels/jour) : on trie par
date et on plafonne le nombre de pages, le run quotidien rattrape le flux.
"""

from __future__ import annotations

import os
import sys
import time

from scripts.http_util import make_session
from scripts.normalize import (
    SALARY_ANNUAL_MAX,
    SALARY_ANNUAL_MIN,
    make_job,
    normalize_contract,
    normalize_remote,
)


def _plausible(value) -> int | None:
    if not value:
        return None
    value = int(value)
    return value if SALARY_ANNUAL_MIN <= value <= SALARY_ANNUAL_MAX else None

BASE_URL = "https://api.adzuna.com/v1/api/jobs/fr/search"
RESULTS_PER_PAGE = 50
MAX_PAGES = 60  # 3000 offres max par run, ~60 appels (marge quota gratuit avec 3 runs/jour)

_CONTRACT_MAP = {"permanent": "CDI", "contract": "CDD"}


def _convert(raw: dict) -> dict:
    contrat = _CONTRACT_MAP.get(raw.get("contract_type", ""), "")
    if not contrat:
        contrat = normalize_contract(raw.get("title", ""))
    location = raw.get("location") or {}
    area = location.get("area") or []
    # area = ["France", "Région", "Département", "Ville"...]
    region = area[1] if len(area) > 1 else ""
    ville = area[-1] if len(area) > 2 else location.get("display_name", "")
    description = raw.get("description") or ""

    return make_job(
        source="adzuna",
        ref=str(raw.get("id", "")),
        titre=raw.get("title", ""),
        entreprise=(raw.get("company") or {}).get("display_name", ""),
        url=raw.get("redirect_url", ""),
        ville=ville,
        region=region,
        lat=raw.get("latitude"),
        lon=raw.get("longitude"),
        contrat=contrat,
        teletravail=normalize_remote(raw.get("title", "") + " " + description[:500]),
        salaire_min=_plausible(raw.get("salary_min")),
        salaire_max=_plausible(raw.get("salary_max")),
        date_publication=(raw.get("created") or "")[:10],
        description=description,
    )


def fetch_adzuna() -> list[dict]:
    """Récupère les offres IT France d'Adzuna. Retourne [] si identifiants absents."""
    app_id = os.environ.get("ADZUNA_APP_ID", "")
    app_key = os.environ.get("ADZUNA_APP_KEY", "")
    if not app_id or not app_key:
        print("Adzuna : ADZUNA_APP_ID/ADZUNA_APP_KEY absents, source ignorée.", file=sys.stderr)
        return []

    session = make_session()
    jobs = []
    try:
        for page in range(1, MAX_PAGES + 1):
            resp = session.get(
                f"{BASE_URL}/{page}",
                params={
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": RESULTS_PER_PAGE,
                    "category": "it-jobs",
                    "sort_by": "date",
                    "content-type": "application/json",
                },
                timeout=30,
            )
            if resp.status_code == 429:
                print("Adzuna : quota atteint, arrêt propre.", file=sys.stderr)
                break
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if not results:
                break
            jobs.extend(_convert(r) for r in results)
            time.sleep(0.3)
    except Exception as exc:  # noqa: BLE001 - source d'appoint : jamais bloquante
        print(f"Adzuna : échec ({type(exc).__name__}: {exc}), on garde {len(jobs)} offres.", file=sys.stderr)

    print(f"Adzuna : {len(jobs)} offres", file=sys.stderr)
    return jobs


if __name__ == "__main__":
    result = fetch_adzuna()
    print(len(result))
