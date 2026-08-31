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
import os
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


def collect(skip: set[str], since_hours: int | None = None) -> tuple[list[dict], dict]:
    jobs: list[dict] = []
    errors: dict = {}

    if "ats" not in skip:
        ats_jobs, ats_errors = fetch_all_ats(load_companies())
        print(f"ATS : {len(ats_jobs)} offres, {len(ats_errors)} entreprises en erreur", file=sys.stderr)
        jobs.extend(ats_jobs)
        errors["ats"] = ats_errors
    if "france_travail" not in skip:
        jobs.extend(fetch_france_travail(since_hours))
    if "wttj" not in skip:
        jobs.extend(fetch_wttj(since_hours))
    if "adzuna" not in skip:
        jobs.extend(fetch_adzuna(since_hours))
    return jobs, errors


def load_existing(out_dir: Path) -> list[dict]:
    """Charge le jeu de données du run précédent (runs légers : base de fusion)."""
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.exists():
        return []
    jobs: list[dict] = []
    for chunk in json.loads(manifest_path.read_text())["chunks"]:
        path = out_dir / chunk["file"]
        if path.exists():
            jobs.extend(json.loads(gzip.decompress(path.read_bytes())))
    print(f"Base existante : {len(jobs)} offres", file=sys.stderr)
    return jobs


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


SEEN_MAX_AGE_DAYS = 60


def stamp_and_diff(jobs: list[dict], out_dir: Path) -> set[str]:
    """Première observation par NOTRE pipeline + diff des nouveautés.

    - premiere_vue (date) posée sur chaque offre : signal honnête d'ancienneté,
      contrairement à date_publication que les reposts rajeunissent.
    - Écrit seen_ids.json (horodatages ISO) et new_jobs.json (offres jamais vues,
      consommées par la newsletter).
    - Retourne les ids sous EMBARGO_MINUTES (exclus de la publication : les
      abonnés reçoivent l'offre avant qu'elle apparaisse sur le site).
    """
    from scripts.newsletter import fetch_previous_seen
    seen = fetch_previous_seen()
    first_run = not seen
    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    embargo_minutes = int(os.environ.get("EMBARGO_MINUTES", "0") or 0)

    cutoff = (date.today() - timedelta(days=SEEN_MAX_AGE_DAYS)).isoformat()
    updated = {jid: ts for jid, ts in seen.items() if ts[:10] >= cutoff}

    new_jobs, published_now, embargoed = [], [], set()
    for job in jobs:
        ts = updated.get(job["id"])
        if ts is None:
            updated[job["id"]] = now_iso
            job["premiere_vue"] = now_iso[:10]
            if not first_run:
                new_jobs.append(job)
                if embargo_minutes:
                    embargoed.add(job["id"])
        else:
            job["premiere_vue"] = ts[:10]
            if embargo_minutes and len(ts) > 10:
                age_min = (now - datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds() / 60
                if age_min < embargo_minutes:
                    embargoed.add(job["id"])
                elif age_min < embargo_minutes + 90:
                    # Embargo levé depuis ce run (ou presque) : cible du palier gratuit.
                    published_now.append(job)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "seen_ids.json").write_text(json.dumps({"ids": updated}))
    # Fichiers LOCAUX du run (jamais publiés : ils contiennent les offres sous embargo).
    (out_dir / "new_jobs.json").write_text(json.dumps(new_jobs, ensure_ascii=False))
    (out_dir / "published_now.json").write_text(json.dumps(published_now, ensure_ascii=False))
    print(f"Diff : {len(new_jobs)} nouvelles, {len(embargoed)} sous embargo ({embargo_minutes} min), "
          f"{len(published_now)} tout juste publiées", file=sys.stderr)
    return embargoed


def write_output(jobs: list[dict], out_dir: Path, errors: dict, exclude_ids: set[str] | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if exclude_ids:
        jobs = [j for j in jobs if j["id"] not in exclude_ids]
    jobs.sort(key=lambda j: j["date_publication"] or "0000", reverse=True)

    # Descriptions longues : réservées aux pages SEO, jamais dans les chunks du front.
    # En run léger, on fusionne avec le store existant (les offres de la base
    # n'ont plus leur _description en mémoire).
    descriptions = {}
    desc_path = out_dir / "descriptions.json.gz"
    if desc_path.exists():
        descriptions = json.loads(gzip.decompress(desc_path.read_bytes()))
    for job in jobs:
        desc = job.pop("_description", "")
        if desc:
            descriptions[job["id"]] = desc
    current_ids = {j["id"] for j in jobs}
    descriptions = {jid: d for jid, d in descriptions.items() if jid in current_ids}
    desc_path.write_bytes(
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
    parser.add_argument("--light", action="store_true",
                        help="run incrémental : delta FT/WTTJ/Adzuna fusionné avec les données existantes")
    args = parser.parse_args()
    out_dir = Path(args.out)

    skip = {s.strip() for s in args.skip_sources.split(",") if s.strip()}
    since_hours = None
    base_jobs: list[dict] = []
    if args.light:
        skip.add("ats")
        since_hours = 2
        base_jobs = load_existing(out_dir)

    jobs, errors = collect(skip, since_hours)
    jobs = base_jobs + jobs
    jobs = prune(jobs, args.max_age_days)
    pair_stats: dict = {}
    jobs = dedupe(jobs, pair_stats)
    if pair_stats:
        print(f"Doublons par paire : {dict(sorted(pair_stats.items(), key=lambda x: -x[1]))}", file=sys.stderr)
    errors["doublons"] = pair_stats
    classify_employers(jobs)
    enrich_geo(jobs)
    embargoed = stamp_and_diff(jobs, out_dir)
    write_output(jobs, out_dir, errors, exclude_ids=embargoed)
    write_analytics(jobs, out_dir)


if __name__ == "__main__":
    main()
