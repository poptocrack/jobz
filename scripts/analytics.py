"""Analytics du marché : agrégats précalculés servis à la page Analyse.

Produit data/analytics.json (agrégats du jour) et data/history.json (série
temporelle). Les données n'étant jamais commitées, l'historique est reporté
d'un déploiement à l'autre : on relit le history.json du site en ligne et on
y ajoute le point du jour.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from scripts.http_util import make_session

SITE_URL = os.environ.get("SITE_URL", "https://poptocrack.github.io/jobz/")
HISTORY_MAX_POINTS = 730  # 2 ans à 1 point/jour (les runs multiples écrasent le point du jour)

MIN_N_TECHNO_SALAIRE = 15  # médiane par techno seulement si assez d'offres


def _midpoint(job: dict) -> int | None:
    lo, hi = job["salaire_min"], job["salaire_max"]
    if lo and hi:
        return (lo + hi) // 2
    return lo or hi


def _tjm_midpoint(job: dict) -> int | None:
    lo, hi = job.get("tjm_min"), job.get("tjm_max")
    if lo and hi:
        return (lo + hi) // 2
    return lo or hi


def _salary_buckets(values: list[int], lo: int, hi: int, step: int) -> list[dict]:
    buckets = []
    for start in range(lo, hi, step):
        count = sum(1 for v in values if start <= v < start + step)
        buckets.append({"de": start, "a": start + step, "n": count})
    below = sum(1 for v in values if v < lo)
    above = sum(1 for v in values if v >= hi)
    if below:
        buckets.insert(0, {"de": None, "a": lo, "n": below})
    if above:
        buckets.append({"de": hi, "a": None, "n": above})
    return buckets


def build_analytics(jobs: list[dict]) -> dict:
    # Conditions de l'API Adzuna : leurs données ne peuvent pas alimenter des
    # agrégats publiés (moyennes de salaires, décomptes) sans accord écrit.
    # La page Analyse est donc calculée hors Adzuna.
    jobs = [j for j in jobs if j["source"] != "adzuna"]
    today = date.today()

    # --- Salaires annuels par contrat (midpoint des fourchettes) ---
    par_contrat = {}
    for contrat in ("CDI", "CDD", "Alternance", "Stage"):
        values = [m for j in jobs if j["contrat"] == contrat and (m := _midpoint(j))]
        if len(values) >= 10:
            values.sort()
            par_contrat[contrat] = {
                "n": len(values),
                "mediane": int(median(values)),
                "q1": values[len(values) // 4],
                "q3": values[3 * len(values) // 4],
            }

    # --- TJM freelance ---
    tjms = sorted(m for j in jobs if (m := _tjm_midpoint(j)))
    tjm_stats = None
    if len(tjms) >= 5:
        tjm_stats = {
            "n": len(tjms),
            "mediane": int(median(tjms)),
            "q1": tjms[len(tjms) // 4],
            "q3": tjms[3 * len(tjms) // 4],
            "distribution": _salary_buckets(tjms, 300, 1100, 100),
        }

    # --- Technos : demande et salaire ---
    tag_counts = Counter(t for j in jobs for t in j["tags"])
    top_technos = [{"tag": t, "n": n} for t, n in tag_counts.most_common(25)]

    salaires_techno = []
    for tag, _ in tag_counts.most_common(40):
        values = [
            m for j in jobs
            if tag in j["tags"] and j["contrat"] == "CDI" and (m := _midpoint(j))
        ]
        if len(values) >= MIN_N_TECHNO_SALAIRE:
            salaires_techno.append({"tag": tag, "n": len(values), "mediane": int(median(values))})
    salaires_techno.sort(key=lambda x: -x["mediane"])
    salaires_techno = salaires_techno[:15]

    # --- Distribution des salaires CDI ---
    cdi_values = [m for j in jobs if j["contrat"] == "CDI" and (m := _midpoint(j))]
    distribution_cdi = _salary_buckets(cdi_values, 20000, 120000, 10000) if cdi_values else []

    # --- Géographie ---
    par_region = Counter(j["region"] for j in jobs if j["region"]).most_common(13)
    par_ville = Counter(j["ville"] for j in jobs if j["ville"]).most_common(15)

    # --- Répartitions ---
    repartitions = {
        "contrat": dict(Counter(j["contrat"] or "Non précisé" for j in jobs).most_common()),
        "teletravail": dict(Counter(j["teletravail"] or "inconnu" for j in jobs).most_common()),
        "employeur": dict(Counter(j["employeur_type"] or "inconnu" for j in jobs).most_common()),
    }

    # --- Transparence salariale par type d'employeur ---
    transparence = {}
    for etype, label in (("client final", "Client final"), ("esn", "ESN / conseil"), ("", "Non déterminé")):
        subset = [j for j in jobs if j["employeur_type"] == etype]
        if subset:
            avec = sum(1 for j in subset if j["salaire_min"] or j["tjm_min"])
            transparence[label] = {"n": len(subset), "pct": round(100 * avec / len(subset), 1)}

    # --- Top recruteurs ---
    def top_recruteurs(etype):
        return [
            {"entreprise": e, "n": n}
            for e, n in Counter(
                j["entreprise"] for j in jobs
                if j["employeur_type"] == etype
                and j["entreprise"] and j["entreprise"] != "Employeur confidentiel"
            ).most_common(10)
        ]

    # --- Publications par jour (30 derniers jours) ---
    cutoff = (today - timedelta(days=30)).isoformat()
    par_jour = Counter(j["date_publication"] for j in jobs if j["date_publication"] >= cutoff)
    publications = [
        {"date": (today - timedelta(days=i)).isoformat(), "n": par_jour.get((today - timedelta(days=i)).isoformat(), 0)}
        for i in range(30, -1, -1)
    ]

    avec_salaire = sum(1 for j in jobs if j["salaire_min"] or j["tjm_min"])
    remote_ok = sum(1 for j in jobs if j["teletravail"] in ("total", "hybride"))

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kpis": {
            "total": len(jobs),
            "salaire_median_cdi": par_contrat.get("CDI", {}).get("mediane"),
            "tjm_median": tjm_stats["mediane"] if tjm_stats else None,
            "pct_avec_salaire": round(100 * avec_salaire / len(jobs), 1) if jobs else 0,
            "pct_teletravail": round(100 * remote_ok / len(jobs), 1) if jobs else 0,
        },
        "top_technos": top_technos,
        "salaires_techno": salaires_techno,
        "salaires_contrat": par_contrat,
        "tjm": tjm_stats,
        "distribution_cdi": distribution_cdi,
        "par_region": [{"region": r, "n": n} for r, n in par_region],
        "par_ville": [{"ville": v, "n": n} for v, n in par_ville],
        "repartitions": repartitions,
        "transparence_salariale": transparence,
        "top_clients_finaux": top_recruteurs("client final"),
        "top_esn": top_recruteurs("esn"),
        "publications_par_jour": publications,
    }


def _fetch_previous_history() -> list[dict]:
    try:
        resp = make_session().get(SITE_URL.rstrip("/") + "/data/history.json", timeout=15)
        if resp.ok:
            return resp.json().get("points", [])
    except Exception:  # noqa: BLE001 - premier déploiement ou site indisponible
        pass
    return []


def write_analytics(jobs: list[dict], out_dir: Path) -> None:
    analytics = build_analytics(jobs)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "analytics.json").write_text(json.dumps(analytics, ensure_ascii=False))

    points = _fetch_previous_history()
    today = date.today().isoformat()
    point = {
        "date": today,
        "total": analytics["kpis"]["total"],
        "salaire_median_cdi": analytics["kpis"]["salaire_median_cdi"],
        "tjm_median": analytics["kpis"]["tjm_median"],
        "pct_avec_salaire": analytics["kpis"]["pct_avec_salaire"],
        "top5_technos": {t["tag"]: t["n"] for t in analytics["top_technos"][:5]},
    }
    points = [p for p in points if p.get("date") != today] + [point]
    points = points[-HISTORY_MAX_POINTS:]
    (out_dir / "history.json").write_text(json.dumps({"points": points}, ensure_ascii=False))
    print(f"Analytics : agrégats écrits, historique {len(points)} point(s)", file=sys.stderr)
