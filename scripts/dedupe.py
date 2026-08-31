"""Dédoublonnage cross-sources.

La même offre apparaît souvent sur plusieurs canaux (ATS de l'entreprise,
WTTJ, France Travail, Adzuna). Clé floue : entreprise + titre + ville
normalisés (suffixes juridiques et mentions H/F retirés). On garde la source
la plus proche de l'entreprise et on complète ses champs vides avec les autres.
"""

from __future__ import annotations

import re
import sys

from scripts.normalize import norm_text

# Plus petit = plus prioritaire (URL de candidature directe d'abord).
SOURCE_PRIORITY = {
    "greenhouse": 0, "lever": 0, "ashby": 0, "recruitee": 0,
    "smartrecruiters": 0, "workable": 0,
    "wttj": 1,
    "france_travail": 2,
    "adzuna": 3,
}

_TITLE_NOISE = re.compile(
    r"\(?\b(h/f/nb|h/f/x|f/h/x|h/f|f/h|m/f/d|m/w/d|x/f/h)\b\)?"
    r"|\((cdi|cdd|stage|alternance|freelance)\)"
    r"|\bcdi\b\s*[-–]\s*|\s*[-–]\s*\bcdi\b",
    re.IGNORECASE,
)
_COMPANY_NOISE = re.compile(r"\b(sas|sasu|sarl|sa|group|groupe|france)\b", re.IGNORECASE)


def _title_key(titre: str) -> str:
    return norm_text(_TITLE_NOISE.sub(" ", titre))


def _company_key(entreprise: str) -> str:
    return norm_text(_COMPANY_NOISE.sub(" ", entreprise))


def _fill_missing(winner: dict, loser: dict) -> None:
    # .get partout : les offres rechargées depuis les chunks publiés n'ont plus
    # certains champs privés (_description) ni forcément les champs récents.
    for field in ("salaire_min", "salaire_max", "tjm_min", "tjm_max", "lat", "lon"):
        if winner.get(field) is None and loser.get(field) is not None:
            winner[field] = loser[field]
    for field in ("contrat", "teletravail", "ville", "departement", "region", "date_publication",
                  "extrait", "_description"):
        if not winner.get(field) and loser.get(field):
            winner[field] = loser[field]
    for tag in loser["tags"]:
        if tag not in winner["tags"] and len(winner["tags"]) < 12:
            winner["tags"].append(tag)


def dedupe(jobs: list[dict], pair_stats: dict | None = None) -> list[dict]:
    """Dédoublonne. Si pair_stats est fourni, y compte les fusions par paire
    "source_gardée < source_écartée"."""
    best: dict[tuple, dict] = {}
    for job in jobs:
        company_key = _company_key(job["entreprise"])
        if not company_key:
            company_key = "?" + job["id"]  # employeur confidentiel : jamais fusionné
        key = (company_key, _title_key(job["titre"]), norm_text(job["ville"]))
        current = best.get(key)
        if current is None:
            best[key] = job
        else:
            prio_new = SOURCE_PRIORITY.get(job["source"], 9)
            prio_cur = SOURCE_PRIORITY.get(current["source"], 9)
            if prio_new < prio_cur:
                winner, loser = job, current
                _fill_missing(job, current)
                best[key] = job
            else:
                winner, loser = current, job
                _fill_missing(current, job)
            if pair_stats is not None:
                pair = f"{winner['source']} < {loser['source']}"
                pair_stats[pair] = pair_stats.get(pair, 0) + 1

    result = list(best.values())
    removed = len(jobs) - len(result)
    print(f"Dédoublonnage : {removed} doublons retirés ({len(result)} offres restantes)", file=sys.stderr)
    return result
