"""Fetchers des APIs publiques d'ATS (par slug d'entreprise), avec filtre France.

Chaque fetcher prend (session, company) où company = {"name", "ats", "slug"}
et retourne une liste d'offres au schéma canonique (scripts.normalize.make_job).
Les réponses des ATS varient d'un tenant à l'autre : tous les accès aux champs
sont défensifs (.get) pour qu'un tenant exotique ne casse pas le run.
"""

from __future__ import annotations

import html as html_mod
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from scripts.http_util import get_json, make_session
from scripts.normalize import make_job, normalize_contract, normalize_remote, parse_salary, strip_accents

_FRENCH_CITIES = [
    "paris", "lyon", "marseille", "toulouse", "bordeaux", "nantes", "lille", "nice",
    "rennes", "strasbourg", "montpellier", "grenoble", "sophia antipolis", "sophia-antipolis",
    "aix-en-provence", "nancy", "metz", "dijon", "angers", "le mans", "tours", "orleans",
    "rouen", "caen", "brest", "clermont-ferrand", "saint-etienne", "toulon", "avignon",
    "annecy", "chambery", "mulhouse", "besancon", "limoges", "poitiers", "pau", "bayonne",
    "biarritz", "perpignan", "nimes", "reims", "troyes", "amiens", "dunkerque", "valenciennes",
    "boulogne-billancourt", "levallois", "courbevoie", "nanterre", "puteaux", "la defense",
    "issy-les-moulineaux", "montreuil", "saint-denis", "ivry", "massy", "saclay", "velizy",
    "guyancourt", "cergy", "charenton", "neuilly", "suresnes", "rueil", "malakoff",
    "chatillon", "villeurbanne", "niort", "la rochelle", "vannes", "lorient", "quimper",
    "saint-malo", "lannion", "cesson-sevigne", "colombes", "clichy", "pantin", "bagnolet",
    "antibes", "cannes", "mougins", "valbonne", "meudon", "sevres", "versailles",
    "saint-cloud", "gennevilliers", "creteil", "vincennes", "montrouge", "vanves",
]
_CITY_RE = re.compile("|".join(rf"\b{re.escape(c)}\b" for c in _FRENCH_CITIES))


def is_france_location(text: str, *, allow_bare_remote: bool = True) -> bool:
    """Heuristique : la localisation désigne-t-elle la France ?

    allow_bare_remote garde un "Remote" sans pays pour les entreprises françaises
    du seed (leur remote est presque toujours FR/UE).
    """
    low = strip_accents((text or "").lower())
    if not low:
        return False
    if "france" in low or re.search(r"\bfr\b", low):
        return True
    if _CITY_RE.search(low):
        return True
    if allow_bare_remote and re.search(r"\bremote\b|teletravail|a distance", low):
        # Un remote explicitement rattaché à un autre pays/ville n'est pas de la France.
        return not re.search(
            r"\b(us|usa|united states|uk|united kingdom|germany|deutschland|spain|espana"
            r"|italy|italia|poland|portugal|netherlands|belgium|canada|brazil|india|serbia|romania"
            r"|london|berlin|madrid|barcelona|milan|amsterdam|brussels|lisbon|warsaw|dublin"
            r"|zurich|geneva|new york)\b",
            low,
        )
    return False


def _iso_date(value) -> str:
    """Convertit timestamp ms / ISO datetime en date ISO courte."""
    if not value:
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return ""
    return str(value)[:10]


def fetch_greenhouse(session, company) -> list[dict]:
    data = get_json(
        session,
        f"https://boards-api.greenhouse.io/v1/boards/{company['slug']}/jobs",
        params={"content": "true"},
    )
    jobs = []
    for job in (data or {}).get("jobs", []):
        location = (job.get("location") or {}).get("name", "")
        if not is_france_location(location, allow_bare_remote=not company.get("strict")):
            continue
        jobs.append(make_job(
            source="greenhouse",
            ref=str(job.get("id", "")),
            titre=job.get("title", ""),
            entreprise=company["name"],
            url=job.get("absolute_url", ""),
            ville=location,
            date_publication=_iso_date(job.get("updated_at") or job.get("first_published")),
            description=html_mod.unescape(job.get("content") or "")[:6000],
        ))
    return jobs


def fetch_lever(session, company) -> list[dict]:
    data = get_json(session, f"https://api.lever.co/v0/postings/{company['slug']}", params={"mode": "json"})
    jobs = []
    for job in data or []:
        categories = job.get("categories") or {}
        location = categories.get("location") or ", ".join(categories.get("allLocations") or [])
        country = job.get("country", "")
        if country and country.upper() != "FR" and not is_france_location(location, allow_bare_remote=False):
            continue
        if not country and not is_france_location(location, allow_bare_remote=not company.get("strict")):
            continue
        salary = job.get("salaryRange") or {}
        sal_min, sal_max = salary.get("min"), salary.get("max")
        if salary.get("currency") not in (None, "", "EUR"):
            sal_min = sal_max = None
        jobs.append(make_job(
            source="lever",
            ref=str(job.get("id", "")),
            titre=job.get("text", ""),
            entreprise=company["name"],
            url=job.get("hostedUrl") or job.get("applyUrl", ""),
            ville=location,
            contrat=normalize_contract(categories.get("commitment", "")),
            teletravail=normalize_remote(job.get("workplaceType", "")),
            salaire_min=sal_min,
            salaire_max=sal_max,
            date_publication=_iso_date(job.get("createdAt")),
            description=job.get("descriptionPlain", "")[:4000],
        ))
    return jobs


def fetch_ashby(session, company) -> list[dict]:
    data = get_json(
        session,
        f"https://api.ashbyhq.com/posting-api/job-board/{company['slug']}",
        params={"includeCompensation": "true"},
    )
    jobs = []
    for job in (data or {}).get("jobs", []):
        locations = [job.get("location", "")] + [
            loc.get("location", "") for loc in job.get("secondaryLocations") or []
        ]
        location = ", ".join(l for l in locations if l)
        if not is_france_location(location, allow_bare_remote=bool(job.get("isRemote")) and not company.get("strict")):
            continue
        comp = ((job.get("compensation") or {}).get("compensationTierSummary")) or ""
        sal_min, sal_max = parse_salary(comp) if "€" in comp or "EUR" in comp else (None, None)
        jobs.append(make_job(
            source="ashby",
            ref=str(job.get("id", "")),
            titre=job.get("title", ""),
            entreprise=company["name"],
            url=job.get("jobUrl") or job.get("applyUrl", ""),
            ville=location,
            contrat=normalize_contract(job.get("employmentType", "")),
            teletravail="total" if job.get("isRemote") else normalize_remote(location),
            salaire_min=sal_min,
            salaire_max=sal_max,
            date_publication=_iso_date(job.get("publishedAt") or job.get("publishedDate")),
            description=(job.get("descriptionHtml") or "")[:6000],
        ))
    return jobs


def fetch_recruitee(session, company) -> list[dict]:
    data = get_json(session, f"https://{company['slug']}.recruitee.com/api/offers/")
    jobs = []
    for job in (data or {}).get("offers", []):
        country = job.get("country", "")
        location = ", ".join(p for p in (job.get("city", ""), country) if p)
        is_fr = strip_accents(country.lower()) == "france" or is_france_location(location)
        if not is_fr and not (job.get("remote") and not country and not company.get("strict")):
            continue
        jobs.append(make_job(
            source="recruitee",
            ref=str(job.get("id", "")),
            titre=job.get("title", ""),
            entreprise=company["name"],
            url=job.get("careers_url") or f"https://{company['slug']}.recruitee.com/o/{job.get('slug', '')}",
            ville=job.get("city", ""),
            contrat=normalize_contract(job.get("employment_type_code") or job.get("employment_type") or ""),
            teletravail="total" if job.get("remote") else "",
            date_publication=_iso_date(job.get("published_at") or job.get("created_at")),
        ))
    return jobs


def fetch_smartrecruiters(session, company) -> list[dict]:
    jobs, offset = [], 0
    while True:
        data = get_json(
            session,
            f"https://api.smartrecruiters.com/v1/companies/{company['slug']}/postings",
            params={"limit": 100, "offset": offset},
        )
        if data is None:
            return jobs
        content = data.get("content", [])
        for job in content:
            location = job.get("location") or {}
            country = (location.get("country") or "").lower()
            loc_text = ", ".join(p for p in (location.get("city", ""), country) if p)
            if country != "fr" and not is_france_location(loc_text, allow_bare_remote=False):
                continue
            jobs.append(make_job(
                source="smartrecruiters",
                ref=str(job.get("id", "")),
                titre=job.get("name", ""),
                entreprise=company["name"],
                url=f"https://jobs.smartrecruiters.com/{company['slug']}/{job.get('id', '')}",
                ville=location.get("city", ""),
                contrat=normalize_contract((job.get("typeOfEmployment") or {}).get("label", "")),
                teletravail="total" if location.get("remote") else "",
                date_publication=_iso_date(job.get("releasedDate")),
            ))
        offset += len(content)
        if offset >= data.get("totalFound", 0) or not content:
            return jobs


def fetch_workable(session, company) -> list[dict]:
    data = get_json(session, f"https://apply.workable.com/api/v1/widget/accounts/{company['slug']}")
    jobs = []
    for job in (data or {}).get("jobs", []):
        country = (job.get("country") or "").lower()
        location = ", ".join(p for p in (job.get("city", ""), job.get("country", "")) if p)
        is_fr = country in ("france", "fr") or is_france_location(location, allow_bare_remote=False)
        if not is_fr and not (job.get("telecommuting") and not country and not company.get("strict")):
            continue
        jobs.append(make_job(
            source="workable",
            ref=str(job.get("shortcode") or job.get("code", "")),
            titre=job.get("title", ""),
            entreprise=company["name"],
            url=job.get("url") or job.get("application_url", ""),
            ville=job.get("city", ""),
            contrat=normalize_contract(job.get("employment_type", "")),
            teletravail="total" if job.get("telecommuting") else "",
            date_publication=_iso_date(job.get("published_on") or job.get("created_at")),
        ))
    return jobs


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "recruitee": fetch_recruitee,
    "smartrecruiters": fetch_smartrecruiters,
    "workable": fetch_workable,
}

_thread_local = threading.local()


def _session():
    if not hasattr(_thread_local, "session"):
        _thread_local.session = make_session()
    return _thread_local.session


def fetch_all_ats(companies: list[dict], max_workers: int = 16) -> tuple[list[dict], dict]:
    """Interroge tous les ATS en parallèle. Retourne (offres, erreurs par entreprise)."""
    jobs, errors = [], {}

    def worker(company):
        fetcher = FETCHERS.get(company["ats"])
        if not fetcher:
            raise ValueError(f"ATS inconnu : {company['ats']}")
        return fetcher(_session(), company)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(worker, c): c for c in companies}
        for future in as_completed(futures):
            company = futures[future]
            try:
                jobs.extend(future.result())
            except Exception as exc:  # noqa: BLE001 - un tenant cassé ne doit pas stopper le run
                errors[f"{company['ats']}:{company['slug']}"] = str(exc)
    return jobs, errors
