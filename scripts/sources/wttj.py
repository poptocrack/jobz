"""Source Welcome to the Jungle — index Algolia public du site (NON OFFICIEL).

Le site interroge Algolia (app CSEKHVMS53) avec une clé de recherche publique
restreinte par Referer. Cette intégration peut casser sans préavis si WTTJ
change de clé ou d'index : le module est tolérant à l'échec et le build
continue sans lui. La clé peut être surchargée via WTTJ_ALGOLIA_KEY.

Algolia plafonne la pagination (~1000 hits par requête) : on segmente
récursivement par région puis département puis type de contrat.
"""

from __future__ import annotations

import os
import sys
import time

from scripts.http_util import make_session
from scripts.normalize import make_job, normalize_contract, parse_salary

ALGOLIA_APP = "CSEKHVMS53"
ALGOLIA_KEY_DEFAULT = "4bd8f6215d0cc52b26430765769e65a0"
INDEX = "wttj_jobs_production_fr"
QUERY_URL = f"https://{ALGOLIA_APP.lower()}-dsn.algolia.net/1/indexes/{INDEX}/query"
REFERER = "https://www.welcometothejungle.com/"

HITS_PER_PAGE = 500
PAGINATION_CAP = 1000

# Catégories métiers ciblées (référentiel interne WTTJ, relevé août 2026).
CATEGORIES = [
    "new_profession.category_reference:tech-engineering-3NjUy",
    "new_profession.category_reference:project-product-management-xYmEw",
]

# Facettes de segmentation, de la plus grosse maille à la plus fine.
SPLIT_FACETS = ["offices.state", "offices.district", "contract_type", "remote"]

ATTRIBUTES = [
    "name", "reference", "slug", "organization.name", "organization.slug",
    "offices", "_geoloc", "remote", "contract_type", "published_at_date",
    "salary_minimum", "salary_maximum", "salary_currency", "salary_period",
    "new_profession", "summary", "sectors",
]

# Secteurs WTTJ signant une société de conseil / prestation.
_CONSEIL_PARENTS = {"consulting-audit"}
_CONSEIL_REFS = {"it-digital-1", "recruitment-1", "interim"}

_REMOTE_MAP = {"fulltime": "total", "partial": "hybride", "punctual": "hybride", "no": "sur site"}


class _WttjClient:
    def __init__(self):
        self.session = make_session()
        self.session.headers.update({
            "x-algolia-application-id": ALGOLIA_APP,
            "x-algolia-api-key": os.environ.get("WTTJ_ALGOLIA_KEY", ALGOLIA_KEY_DEFAULT),
            "Referer": REFERER,
            "Origin": "https://www.welcometothejungle.com",
        })

    def query(self, facet_filters: list, *, page: int = 0, hits_per_page: int = HITS_PER_PAGE,
              facets: list[str] | None = None) -> dict:
        body = {
            "query": "",
            "hitsPerPage": hits_per_page,
            "page": page,
            "facetFilters": facet_filters,
            "attributesToRetrieve": ATTRIBUTES,
            "attributesToHighlight": [],
            "analytics": False,
        }
        if facets:
            body["facets"] = facets
        resp = self.session.post(QUERY_URL, json=body, timeout=30)
        resp.raise_for_status()
        time.sleep(0.15)
        return resp.json()


def _annual_salary(hit: dict) -> tuple[int | None, int | None]:
    if hit.get("salary_currency") not in (None, "", "EUR"):
        return None, None
    period = hit.get("salary_period") or "yearly"
    factor = {"yearly": 1, "monthly": 12, "daily": 218, "hourly": 1607}.get(period, 1)
    out = []
    for key in ("salary_minimum", "salary_maximum"):
        value = hit.get(key)
        if isinstance(value, (int, float)) and value > 0:
            annual = int(value * factor)
            out.append(annual if 8000 <= annual <= 600000 else None)
        else:
            out.append(None)
    return out[0], out[1]


def _convert(hit: dict) -> dict | None:
    org = hit.get("organization") or {}
    all_offices = hit.get("offices") or []
    geolocs = hit.get("_geoloc") or []
    # _geoloc[i] correspond à offices[i] : on garde la géoloc du bureau FR retenu.
    office, geoloc = {}, {}
    for i, o in enumerate(all_offices):
        if o.get("country_code") == "FR":
            office = o
            if i < len(geolocs):
                geoloc = geolocs[i]
            break
    if not hit.get("name") or not org.get("slug"):
        return None

    sal_min, sal_max = _annual_salary(hit)
    url = f"https://www.welcometothejungle.com/fr/companies/{org['slug']}/jobs/{hit.get('slug', '')}"

    sectors = hit.get("sectors") or []
    employeur_type = ""
    if any(s.get("parent_reference") in _CONSEIL_PARENTS or s.get("reference") in _CONSEIL_REFS for s in sectors):
        employeur_type = "esn"
    elif sectors:
        employeur_type = "client final"

    return make_job(
        source="wttj",
        ref=str(hit.get("reference") or hit.get("objectID", "")),
        titre=hit.get("name", ""),
        entreprise=org.get("name", ""),
        url=url,
        ville=office.get("local_city") or office.get("city", ""),
        region=office.get("local_state") or office.get("state", ""),
        # Le code département est résolu plus tard (scripts.geo) depuis le nom.
        departement=office.get("local_district") or office.get("district", ""),
        lat=geoloc.get("lat"),
        lon=geoloc.get("lng"),
        contrat=normalize_contract(hit.get("contract_type", "")),
        teletravail=_REMOTE_MAP.get(hit.get("remote", ""), ""),
        salaire_min=sal_min,
        salaire_max=sal_max,
        date_publication=hit.get("published_at_date", ""),
        description=hit.get("summary") or "",
        employeur_type=employeur_type,
    )


def _collect_segment(client: _WttjClient, filters: list, split_level: int, seen: dict) -> None:
    first = client.query(filters, facets=[SPLIT_FACETS[split_level]] if split_level < len(SPLIT_FACETS) else None)
    nb_hits = first.get("nbHits", 0)
    if nb_hits == 0:
        return

    if nb_hits > PAGINATION_CAP and split_level < len(SPLIT_FACETS):
        facet = SPLIT_FACETS[split_level]
        values = list((first.get("facets") or {}).get(facet, {}))
        if values:
            for value in values:
                _collect_segment(client, filters + [[f"{facet}:{value}"]], split_level + 1, seen)
            return
        # Pas de valeurs de facette exploitables : on pagine ce qu'on peut.

    for hit in first.get("hits", []):
        seen.setdefault(hit["objectID"], hit)
    page = 1
    while page * HITS_PER_PAGE < min(nb_hits, PAGINATION_CAP):
        data = client.query(filters, page=page)
        hits = data.get("hits", [])
        if not hits:
            break
        for hit in hits:
            seen.setdefault(hit["objectID"], hit)
        page += 1


def fetch_wttj() -> list[dict]:
    """Récupère les offres tech/produit France de WTTJ. Retourne [] en cas d'échec."""
    client = _WttjClient()
    seen: dict[str, dict] = {}
    try:
        for category in CATEGORIES:
            _collect_segment(client, [["offices.country_code:FR"], [category]], 0, seen)
    except Exception as exc:  # noqa: BLE001 - source non officielle : jamais bloquante
        print(f"WTTJ : échec ({type(exc).__name__}: {exc}), source ignorée pour ce run.", file=sys.stderr)
        if not seen:
            return []

    jobs = [job for job in (_convert(h) for h in seen.values()) if job]
    print(f"WTTJ : {len(jobs)} offres", file=sys.stderr)
    return jobs


if __name__ == "__main__":
    result = fetch_wttj()
    print(len(result))
    for job in result[:3]:
        print(job)
