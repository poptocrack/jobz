"""Découverte de slugs ATS d'entreprises françaises.

Trois mécanismes :
  --probe    : sonde les noms de seed_candidates.json sur chaque ATS (variantes de slug)
               et fusionne les hits dans companies.json.
  --cc       : interroge les index Common Crawl sur les motifs d'URL ATS pour extraire
               des slugs candidats, puis les sonde (lourd : à lancer ponctuellement).
  --from-file: extrait les slugs ATS depuis un dump d'URLs de candidature (WTTJ/Adzuna).

Un hit = le slug existe ET expose au moins une offre localisée en France.
Usage :
    python -m scripts.discover --probe
    python -m scripts.discover --cc greenhouse --cc-max-pages 2
    python -m scripts.discover --from-file data/raw_apply_urls.txt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from scripts.http_util import get_json, make_session
from scripts.normalize import slugify, strip_accents
from scripts.sources.ats import FETCHERS

ROOT = Path(__file__).resolve().parent.parent
COMPANIES_PATH = ROOT / "companies.json"
SEED_PATH = ROOT / "seed_candidates.json"

# Motifs d'URL de candidature -> (ats, groupe slug)
APPLY_URL_PATTERNS = [
    ("greenhouse", re.compile(r"boards?\.greenhouse\.io/([a-z0-9_-]+)")),
    ("greenhouse", re.compile(r"job-boards\.greenhouse\.io/([a-z0-9_-]+)")),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([a-zA-Z0-9_-]+)")),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([a-zA-Z0-9_.-]+)")),
    ("recruitee", re.compile(r"([a-z0-9-]+)\.recruitee\.com")),
    ("smartrecruiters", re.compile(r"(?:jobs|careers)\.smartrecruiters\.com/([a-zA-Z0-9_-]+)")),
    ("workable", re.compile(r"apply\.workable\.com/(?:j/)?([a-z0-9-]+)")),
]

CC_URL_PATTERNS = {
    "greenhouse": "boards.greenhouse.io/*",
    "lever": "jobs.lever.co/*",
    "ashby": "jobs.ashbyhq.com/*",
    "smartrecruiters": "jobs.smartrecruiters.com/*",
    "workable": "apply.workable.com/*",
}


def slug_variants(name: str) -> list[str]:
    """Variantes plausibles de slug pour un nom d'entreprise."""
    base = strip_accents(name.lower())
    base = re.sub(r"[&.]", " ", base).replace("'", "")
    words = re.findall(r"[a-z0-9]+", base)
    if not words:
        return []
    variants = ["".join(words), "-".join(words), slugify(name)]
    if len(words) > 1:
        variants.append(words[0])
        variants.append("".join(words) + "hq")
    seen, out = set(), []
    for v in variants:
        if v and len(v) > 1 and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def load_companies() -> list[dict]:
    if COMPANIES_PATH.exists():
        return json.loads(COMPANIES_PATH.read_text())["companies"]
    return []


def save_companies(companies: list[dict]) -> None:
    companies = sorted(companies, key=lambda c: (c["name"].lower(), c["ats"]))
    COMPANIES_PATH.write_text(
        json.dumps({"companies": companies}, indent=2, ensure_ascii=False) + "\n"
    )


def probe_one(session, ats: str, slug: str, name: str) -> dict | None:
    """Sonde un slug sur un ATS. Retourne l'entrée company si le board existe avec ≥1 offre FR."""
    try:
        jobs = FETCHERS[ats](session, {"name": name, "ats": ats, "slug": slug})
    except Exception:  # noqa: BLE001 - tout échec réseau/parse = pas de hit
        return None
    if jobs:
        return {"name": name, "ats": ats, "slug": slug, "fr_jobs_at_probe": len(jobs)}
    return None


def probe_candidates(pairs: list[tuple[str, str, str]], max_workers: int = 24) -> list[dict]:
    """pairs = [(name, ats, slug)] ; retourne les hits."""
    hits = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(probe_one, make_session(), ats, slug, name): (name, ats, slug)
            for name, ats, slug in pairs
        }
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % 100 == 0:
                print(f"  sondé {done}/{len(futures)}...", file=sys.stderr)
            result = future.result()
            if result:
                hits.append(result)
    return hits


def merge_hits(hits: list[dict]) -> tuple[int, int]:
    """Fusionne les hits dans companies.json. Garde un seul ATS par entreprise (le plus fourni)."""
    companies = load_companies()
    existing = {(c["name"].lower(), c["ats"]) for c in companies}
    names_present = {c["name"].lower() for c in companies}

    best_by_name: dict[str, dict] = {}
    for hit in hits:
        key = hit["name"].lower()
        if key not in best_by_name or hit["fr_jobs_at_probe"] > best_by_name[key]["fr_jobs_at_probe"]:
            best_by_name[key] = hit

    added = 0
    for key, hit in best_by_name.items():
        if key in names_present or (key, hit["ats"]) in existing:
            continue
        companies.append(hit)
        added += 1
    save_companies(companies)
    return added, len(companies)


def run_probe() -> None:
    seed = json.loads(SEED_PATH.read_text())["candidates"]
    pairs = []
    for name in seed:
        for ats in FETCHERS:
            for slug in slug_variants(name):
                pairs.append((name, ats, slug))
                if ats == "smartrecruiters":
                    # Les identifiants SmartRecruiters sont souvent suffixés (ex. Ubisoft2).
                    pairs.extend([(name, ats, slug + "1"), (name, ats, slug + "2")])
    print(f"Sondage de {len(seed)} entreprises ({len(pairs)} combinaisons)...", file=sys.stderr)
    hits = probe_candidates(pairs)
    added, total = merge_hits(hits)
    print(f"{len(hits)} hits bruts, {added} entreprises ajoutées, {total} au total dans companies.json")


def run_from_file(path: str) -> None:
    text = Path(path).read_text()
    found: set[tuple[str, str]] = set()
    for ats, pattern in APPLY_URL_PATTERNS:
        for match in pattern.finditer(text):
            slug = match.group(1).lower()
            if slug not in ("wp-content", "cdn", "www", "j", "embed"):
                found.add((ats, slug))
    known = {(c["ats"], c["slug"]) for c in load_companies()}
    new = [(slug, ats, slug) for ats, slug in found if (ats, slug) not in known]
    print(f"{len(found)} slugs extraits, {len(new)} nouveaux à sonder...", file=sys.stderr)
    hits = probe_candidates(new)
    for hit in hits:
        hit["name"] = hit["name"].replace("-", " ").title()
        hit["strict"] = True
    added, total = merge_hits(hits)
    print(f"{len(hits)} confirmés FR, {added} ajoutés, {total} au total")


def run_common_crawl(ats: str, max_pages: int) -> None:
    session = make_session()
    collections = get_json(session, "https://index.commoncrawl.org/collinfo.json")
    latest = collections[0]["id"]
    pattern = CC_URL_PATTERNS[ats]
    print(f"Common Crawl {latest}, motif {pattern}", file=sys.stderr)

    slugs: set[str] = set()
    for page in range(max_pages):
        # L'index Common Crawl est souvent surchargé : retries avec backoff.
        resp = None
        for attempt in range(4):
            try:
                resp = session.get(
                    f"https://index.commoncrawl.org/{latest}-index",
                    params={"url": pattern, "output": "json", "page": page, "fl": "url"},
                    timeout=120,
                )
                break
            except Exception as exc:  # noqa: BLE001
                print(f"  CC page {page} tentative {attempt + 1} : {type(exc).__name__}", file=sys.stderr)
                time.sleep(15 * (attempt + 1))
        if resp is None or resp.status_code != 200:
            print(f"  CC page {page} abandonnée", file=sys.stderr)
            break
        for line in resp.text.splitlines():
            try:
                url = json.loads(line).get("url", "")
            except json.JSONDecodeError:
                continue
            for pat_ats, pat in APPLY_URL_PATTERNS:
                if pat_ats != ats:
                    continue
                match = pat.search(url)
                if match:
                    slugs.add(match.group(1).lower())
    known = {c["slug"] for c in load_companies() if c["ats"] == ats}
    candidates = [(slug, ats, slug) for slug in slugs - known]
    print(f"{len(slugs)} slugs uniques, {len(candidates)} nouveaux à sonder (filtre FR au sondage)...", file=sys.stderr)
    hits = probe_candidates(candidates)
    for hit in hits:
        hit["name"] = hit["name"].replace("-", " ").title()
        # Entreprise découverte (pas du seed vérifié) : filtre France strict,
        # un "Remote" sans pays ne suffit pas.
        hit["strict"] = True
    added, total = merge_hits(hits)
    print(f"{len(hits)} confirmés FR, {added} ajoutés, {total} au total")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="sonder seed_candidates.json")
    parser.add_argument("--cc", choices=sorted(CC_URL_PATTERNS), help="découverte Common Crawl pour un ATS")
    parser.add_argument("--cc-max-pages", type=int, default=1)
    parser.add_argument("--from-file", help="fichier d'URLs de candidature à analyser")
    args = parser.parse_args()

    if args.probe:
        run_probe()
    elif args.cc:
        run_common_crawl(args.cc, args.cc_max_pages)
    elif args.from_file:
        run_from_file(args.from_file)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
