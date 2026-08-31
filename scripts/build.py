"""Orchestration du pipeline : fetch -> dédoublonnage -> géo -> chunks gzip + manifest.

Usage :
    python -m scripts.build [--out data] [--skip-sources wttj,adzuna] [--max-age-days 45]

Les sources sans identifiants (France Travail, Adzuna) ou en échec sont
ignorées proprement ; le build produit toujours un jeu de données valide.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from scripts.analytics import write_analytics
from scripts.dedupe import SOURCE_PRIORITY, dedupe
from scripts.esn import is_esn_name
from scripts.geo import enrich_geo
from scripts.sources.adzuna import fetch_adzuna
from scripts.sources.ats import fetch_all_ats
from scripts.sources.france_travail import fetch_france_travail
from scripts.sources.wttj import fetch_wttj

ROOT = Path(__file__).resolve().parent.parent
CHUNK_SIZE = 4000


def load_companies() -> list[dict]:
    path = ROOT / "companies.json"
    if not path.exists():
        print("companies.json absent : sources ATS ignorées.", file=sys.stderr)
        return []
    return json.loads(path.read_text())["companies"]


def collect(skip: set[str]) -> tuple[list[dict], dict]:
    jobs: list[dict] = []
    errors: dict = {}

    if "ats" not in skip:
        ats_jobs, ats_errors = fetch_all_ats(load_companies())
        print(f"ATS : {len(ats_jobs)} offres, {len(ats_errors)} entreprises en erreur", file=sys.stderr)
        jobs.extend(ats_jobs)
        errors["ats"] = ats_errors
    if "france_travail" not in skip:
        jobs.extend(fetch_france_travail())
    if "wttj" not in skip:
        jobs.extend(fetch_wttj())
    if "adzuna" not in skip:
        jobs.extend(fetch_adzuna())
    return jobs, errors


def prune(jobs: list[dict], max_age_days: int) -> list[dict]:
    cutoff = (date.today() - timedelta(days=max_age_days)).isoformat()
    kept = [
        j for j in jobs
        if j["titre"] and j["url"] and (not j["date_publication"] or j["date_publication"] >= cutoff)
    ]
    print(f"Filtrage : {len(jobs) - len(kept)} offres écartées (anciennes ou incomplètes)", file=sys.stderr)
    return kept


def classify_employers(jobs: list[dict]) -> None:
    """Passe finale employeur_type : la liste des prestataires connus prime,
    et une offre issue de l'ATS d'une entreprise du seed est un client final."""
    for job in jobs:
        if is_esn_name(job["entreprise"]):
            job["employeur_type"] = "esn"
        elif not job["employeur_type"] and SOURCE_PRIORITY.get(job["source"]) == 0:
            job["employeur_type"] = "client final"
    counts = Counter(j["employeur_type"] or "inconnu" for j in jobs)
    print(f"Employeurs : {dict(counts.most_common())}", file=sys.stderr)


def build_stats(jobs: list[dict], errors: dict) -> dict:
    return {
        "par_source": dict(Counter(j["source"] for j in jobs).most_common()),
        "par_contrat": dict(Counter(j["contrat"] or "Non précisé" for j in jobs).most_common()),
        "par_region": dict(Counter(j["region"] or "Non précisée" for j in jobs).most_common()),
        "par_teletravail": dict(Counter(j["teletravail"] or "inconnu" for j in jobs).most_common()),
        "par_employeur": dict(Counter(j["employeur_type"] or "inconnu" for j in jobs).most_common()),
        "top_entreprises": dict(Counter(j["entreprise"] for j in jobs if j["entreprise"]).most_common(20)),
        "avec_salaire": sum(1 for j in jobs if j["salaire_min"] is not None),
        "erreurs_ats": errors.get("ats", {}),
        "doublons_par_paire": dict(sorted(errors.get("doublons", {}).items(), key=lambda x: -x[1])),
    }


def stamp_first_seen(jobs: list[dict]) -> None:
    """Date de première observation par NOTRE pipeline (signal honnête d'ancienneté,
    contrairement à date_publication que les reposts rajeunissent)."""
    from scripts.newsletter import fetch_previous_seen
    seen = fetch_previous_seen()
    today = date.today().isoformat()
    for job in jobs:
        job["premiere_vue"] = seen.get(job["id"], today)


def write_output(jobs: list[dict], out_dir: Path, errors: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs.sort(key=lambda j: j["date_publication"] or "0000", reverse=True)

    # Descriptions longues : réservées aux pages SEO, jamais dans les chunks du front.
    descriptions = {}
    for job in jobs:
        desc = job.pop("_description", "")
        if desc:
            descriptions[job["id"]] = desc
    (out_dir / "descriptions.json.gz").write_bytes(
        gzip.compress(json.dumps(descriptions, ensure_ascii=False).encode(), compresslevel=9)
    )

    chunks = []
    for i in range(0, max(len(jobs), 1), CHUNK_SIZE):
        chunk = jobs[i:i + CHUNK_SIZE]
        name = f"jobs_{i // CHUNK_SIZE:03d}.json.gz"
        payload = json.dumps(chunk, ensure_ascii=False, separators=(",", ":")).encode()
        (out_dir / name).write_bytes(gzip.compress(payload, compresslevel=9))
        chunks.append({"file": name, "count": len(chunk)})

    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(jobs),
        "chunks": chunks,
        "stats": build_stats(jobs, errors),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    size = sum((out_dir / c["file"]).stat().st_size for c in chunks)
    print(f"Écrit : {len(jobs)} offres, {len(chunks)} chunks ({size / 1024:.0f} Ko gz), manifest.json", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(ROOT / "data"))
    parser.add_argument("--skip-sources", default="", help="ex: wttj,adzuna,ats,france_travail")
    parser.add_argument("--max-age-days", type=int, default=45)
    args = parser.parse_args()

    skip = {s.strip() for s in args.skip_sources.split(",") if s.strip()}
    jobs, errors = collect(skip)
    jobs = prune(jobs, args.max_age_days)
    pair_stats: dict = {}
    jobs = dedupe(jobs, pair_stats)
    if pair_stats:
        print(f"Doublons par paire : {dict(sorted(pair_stats.items(), key=lambda x: -x[1]))}", file=sys.stderr)
    errors["doublons"] = pair_stats
    classify_employers(jobs)
    enrich_geo(jobs)
    stamp_first_seen(jobs)
    write_output(jobs, Path(args.out), errors)
    write_analytics(jobs, Path(args.out))


if __name__ == "__main__":
    main()
