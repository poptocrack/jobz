"""Génération SEO statique : pages par offre (JobPosting/Google Jobs), pages
segments (techno, région, ville), sitemap.xml, robots.txt et liens de footer.

Tourne en CI après la collecte, écrit directement dans le dossier du site
assemblé. Tout est régénéré à chaque run : les offres expirées disparaissent
du sitemap et leurs pages ne sont plus publiées.

Usage : python -m scripts.seo --data data --out _site
"""

from __future__ import annotations

import argparse
import gzip
import html
import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from scripts.normalize import slugify

SITE_URL = os.environ.get("SITE_URL", "https://poptocrack.github.io/jobz/").rstrip("/")

MIN_OFFERS_SEGMENT = 25
MAX_OFFERS_PER_SEGMENT_PAGE = 100
VALID_DAYS = 45

_EMPLOYMENT_TYPES = {
    "CDI": "FULL_TIME",
    "CDD": "TEMPORARY",
    "Stage": "INTERN",
    "Alternance": "OTHER",
    "Freelance": "CONTRACTOR",
}


def esc(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def load_jobs(data_dir: Path) -> tuple[list[dict], dict]:
    manifest = json.loads((data_dir / "manifest.json").read_text())
    jobs: list[dict] = []
    for chunk in manifest["chunks"]:
        jobs.extend(json.loads(gzip.decompress((data_dir / chunk["file"]).read_bytes())))
    descriptions = {}
    desc_path = data_dir / "descriptions.json.gz"
    if desc_path.exists():
        descriptions = json.loads(gzip.decompress(desc_path.read_bytes()))
    return jobs, descriptions


def page_shell(titre: str, description: str, canonical: str, body: str, jsonld: dict | None = None) -> str:
    ld = (
        f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>'
        if jsonld else ""
    )
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(titre)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{esc(titre)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:image" content="{SITE_URL}/og.png">
<meta property="og:locale" content="fr_FR">
<link rel="stylesheet" href="{SITE_URL}/styles.css">
{ld}
</head>
<body>
<header class="topbar"><div class="topbar-inner">
  <a class="brand" href="{SITE_URL}/" style="text-decoration:none;color:inherit;">
    <span class="brand-mark" aria-hidden="true">jz</span>
    <div><h1 style="margin:0;font-size:1.05rem;">jobz</h1>
    <span class="tagline">🇫🇷 l'emploi tech en France</span></div>
  </a>
</div></header>
<main class="seo-page">{body}</main>
<footer class="seo-page-footer">
  <p><a href="{SITE_URL}/">jobz</a> agrège l'emploi tech en France : France Travail,
  Welcome to the Jungle et 1 400+ sites carrière, actualisés 3 fois par jour.</p>
</footer>
</body>
</html>"""


def offer_jsonld(job: dict, description: str) -> dict:
    posted = job.get("date_publication") or job.get("premiere_vue") or date.today().isoformat()
    valid = (date.fromisoformat(posted) + timedelta(days=VALID_DAYS)).isoformat()
    ld = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": job["titre"],
        "description": f"<p>{esc(description or job.get('extrait') or job['titre'])}</p>",
        "datePosted": posted,
        "validThrough": f"{valid}T23:59:59+01:00",
        "hiringOrganization": {"@type": "Organization", "name": job["entreprise"] or "Employeur confidentiel"},
        "jobLocation": {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": job.get("ville") or "France",
                "addressRegion": job.get("region") or "",
                "addressCountry": "FR",
            },
        },
        "directApply": False,
    }
    emp = _EMPLOYMENT_TYPES.get(job.get("contrat", ""))
    if emp:
        ld["employmentType"] = emp
    if job.get("teletravail") == "total":
        ld["jobLocationType"] = "TELECOMMUTE"
        ld["applicantLocationRequirements"] = {"@type": "Country", "name": "France"}
    if job.get("salaire_min") or job.get("salaire_max"):
        value = {"@type": "QuantitativeValue", "unitText": "YEAR"}
        if job.get("salaire_min"):
            value["minValue"] = job["salaire_min"]
        if job.get("salaire_max"):
            value["maxValue"] = job["salaire_max"]
        ld["baseSalary"] = {"@type": "MonetaryAmount", "currency": "EUR", "value": value}
    return ld


def fmt_salaire(job: dict) -> str:
    if job.get("tjm_min") or job.get("tjm_max"):
        lo, hi = job.get("tjm_min"), job.get("tjm_max")
        return f"{lo}–{hi} €/jour" if lo and hi and lo != hi else f"{lo or hi} €/jour"
    lo, hi = job.get("salaire_min"), job.get("salaire_max")
    if lo and hi and lo != hi:
        return f"{lo // 1000}–{hi // 1000} k€ brut/an"
    if lo or hi:
        return f"{(lo or hi) // 1000} k€ brut/an"
    return ""


def write_offer_pages(jobs: list[dict], descriptions: dict, out: Path) -> int:
    count = 0
    for job in jobs:
        page_dir = out / "offre" / job["id"]
        page_dir.mkdir(parents=True, exist_ok=True)
        canonical = f"{SITE_URL}/offre/{job['id']}/"
        description = descriptions.get(job["id"], "")
        titre_page = f"{job['titre']} — {job['entreprise'] or 'Emploi tech'}"
        meta = job.get("extrait") or f"{job['titre']} chez {job['entreprise']}, {job.get('ville') or 'France'}."

        infos = " · ".join(filter(None, [
            job.get("ville"), job.get("region") if job.get("region") != job.get("ville") else "",
            job.get("contrat"),
            {"total": "Full remote", "hybride": "Télétravail hybride", "sur site": "Sur site"}.get(job.get("teletravail", ""), ""),
            fmt_salaire(job),
            {"client final": "Client final", "esn": "ESN / conseil"}.get(job.get("employeur_type", ""), ""),
        ]))
        tags = " ".join(f'<span class="badge tag">{esc(t)}</span>' for t in job.get("tags", []))
        body = f"""
<h1>{esc(job['titre'])}</h1>
<p class="seo-infos"><strong>{esc(job['entreprise'] or 'Employeur confidentiel')}</strong> · {esc(infos)}</p>
<div class="badges">{tags}</div>
<p>{esc(description or job.get('extrait') or '')}</p>
<p><a class="btn btn-primary" href="{esc(job['url'])}" rel="nofollow noopener">Voir l'offre et postuler</a></p>
<p><a href="{SITE_URL}/?q={esc(job.get('tags', [''])[0] if job.get('tags') else '')}">Voir les offres similaires sur jobz</a></p>
"""
        (page_dir / "index.html").write_text(
            page_shell(titre_page, meta, canonical, body, offer_jsonld(job, description))
        )
        count += 1
    return count


def build_segments(jobs: list[dict]) -> list[dict]:
    segments = []
    tag_counts = Counter(t for j in jobs for t in j["tags"])
    for tag, n in tag_counts.most_common(40):
        if n >= MIN_OFFERS_SEGMENT:
            segments.append({
                "slug": f"emploi-{slugify(tag)}",
                "titre": f"Offres d'emploi {tag} en France",
                "label": f"Emploi {tag}",
                "filtre": lambda j, t=tag: t in j["tags"],
                "lien_app": f"{SITE_URL}/?q={tag}",
            })
    for region, n in Counter(j["region"] for j in jobs if j["region"]).most_common(13):
        if n >= MIN_OFFERS_SEGMENT:
            segments.append({
                "slug": f"emploi-tech-{slugify(region)}",
                "titre": f"Offres d'emploi tech en {region}",
                "label": f"Tech {region}",
                "filtre": lambda j, r=region: j["region"] == r,
                "lien_app": f"{SITE_URL}/?region={region}",
            })
    for ville, n in Counter(j["ville"] for j in jobs if j["ville"]).most_common(15):
        if n >= MIN_OFFERS_SEGMENT:
            segments.append({
                "slug": f"emploi-tech-ville-{slugify(ville)}",
                "titre": f"Offres d'emploi tech à {ville}",
                "label": f"Tech {ville}",
                "filtre": lambda j, v=ville: j["ville"] == v,
                "lien_app": f"{SITE_URL}/?q={ville}",
            })
    segments.append({
        "slug": "emploi-tech-client-final",
        "titre": "Offres d'emploi tech chez des clients finaux (hors ESN)",
        "label": "Client final uniquement",
        "filtre": lambda j: j["employeur_type"] == "client final",
        "lien_app": f"{SITE_URL}/?emp=client+final",
    })
    segments.append({
        "slug": "emploi-tech-full-remote",
        "titre": "Offres d'emploi tech en full remote depuis la France",
        "label": "Full remote",
        "filtre": lambda j: j["teletravail"] == "total",
        "lien_app": f"{SITE_URL}/?tt=total",
    })
    return segments


def write_segment_pages(jobs: list[dict], segments: list[dict], out: Path) -> None:
    for seg in segments:
        matches = [j for j in jobs if seg["filtre"](j)]
        matches.sort(key=lambda j: j["date_publication"] or "", reverse=True)
        shown = matches[:MAX_OFFERS_PER_SEGMENT_PAGE]
        canonical = f"{SITE_URL}/{seg['slug']}/"
        rows = "\n".join(
            f'<li><a href="{SITE_URL}/offre/{j["id"]}/">{esc(j["titre"])}</a>'
            f' — {esc(j["entreprise"])}{" · " + esc(j["ville"]) if j["ville"] else ""}'
            f'{" · " + esc(fmt_salaire(j)) if fmt_salaire(j) else ""}</li>'
            for j in shown
        )
        meta = (f"{len(matches)} offres actualisées 3 fois par jour, agrégées depuis France Travail, "
                f"Welcome to the Jungle et les sites carrière des entreprises.")
        jsonld = {
            "@context": "https://schema.org/",
            "@type": "ItemList",
            "name": seg["titre"],
            "numberOfItems": len(shown),
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "url": f"{SITE_URL}/offre/{j['id']}/"}
                for i, j in enumerate(shown)
            ],
        }
        body = f"""
<h1>{esc(seg['titre'])}</h1>
<p>{len(matches)} offres en ce moment, mises à jour 3 fois par jour.
<a href="{seg['lien_app']}">Filtrer et affiner sur jobz →</a></p>
<ul class="seo-list">{rows}</ul>
"""
        page_dir = out / seg["slug"]
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(page_shell(seg["titre"], meta, canonical, body, jsonld))


def write_sitemap(jobs: list[dict], segments: list[dict], out: Path) -> None:
    today = date.today().isoformat()
    urls = [f"{SITE_URL}/", f"{SITE_URL}/analyse.html"]
    urls += [f"{SITE_URL}/{seg['slug']}/" for seg in segments]
    urls += [f"{SITE_URL}/offre/{j['id']}/" for j in jobs]
    entries = "\n".join(
        f"<url><loc>{u}</loc><lastmod>{today}</lastmod></url>" for u in urls
    )
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n</urlset>"
    )
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data")
    parser.add_argument("--out", default="_site")
    args = parser.parse_args()
    data_dir, out = Path(args.data), Path(args.out)

    jobs, descriptions = load_jobs(data_dir)
    segments = build_segments(jobs)

    count = write_offer_pages(jobs, descriptions, out)
    write_segment_pages(jobs, segments, out)
    write_sitemap(jobs, segments, out)

    links = [{"label": seg["label"], "url": f"{SITE_URL}/{seg['slug']}/"} for seg in segments]
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "data" / "seo_links.json").write_text(json.dumps(links, ensure_ascii=False))

    print(f"SEO : {count} pages offre, {len(segments)} pages segment, sitemap {count + len(segments) + 2} URLs",
          file=sys.stderr)


if __name__ == "__main__":
    main()
