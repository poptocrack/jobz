"""Source France Travail — API Offres d'emploi v2 (francetravail.io).

Auth OAuth2 client credentials. Variables d'environnement requises :
    FT_CLIENT_ID, FT_CLIENT_SECRET  (application créée sur francetravail.io
    avec l'API "Offres d'emploi v2" activée)

Ciblage tech : domaine professionnel M18 (systèmes d'information et de
télécommunication) + requêtes par mots-clés pour les métiers tech classés
ailleurs (data, produit). La pagination de l'API est plafonnée (range max
p=3149), donc on segmente par département quand une requête dépasse le cap.
"""

from __future__ import annotations

import os
import sys
import time

import requests

from scripts.http_util import make_session
from scripts.normalize import make_job, normalize_contract, normalize_remote, parse_salary

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SCOPE = "api_offresdemploiv2 o2dsoffre"

PAGE_SIZE = 150
RANGE_CAP = 3000  # sous le plafond réel (~3149) pour rester sûr
REQUEST_INTERVAL = 0.3  # ~3 req/s, sous le quota de 4 req/s

# Domaine professionnel tech principal.
DOMAINES = ["M18"]
# Métiers tech hors M18, rattrapés par mots-clés.
MOTS_CLES = ["data engineer", "data scientist", "product manager", "devops", "cybersecurite"]

# Codes département : 01..95 (hors 20) + Corse + DOM.
DEPARTEMENTS = (
    [f"{i:02d}" for i in range(1, 96) if i != 20]
    + ["2A", "2B", "971", "972", "973", "974", "976"]
)


class FranceTravailClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = make_session()
        self.token = ""
        self.token_expiry = 0.0
        self.last_request = 0.0

    def _ensure_token(self) -> None:
        if self.token and time.time() < self.token_expiry - 60:
            return
        resp = self.session.post(
            TOKEN_URL,
            params={"realm": "/partenaire"},
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": SCOPE,
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
        self.token = payload["access_token"]
        self.token_expiry = time.time() + payload.get("expires_in", 1500)

    def _search_page(self, params: dict) -> tuple[list[dict], int]:
        """Une page de résultats. Retourne (offres, total du segment)."""
        self._ensure_token()
        wait = REQUEST_INTERVAL - (time.time() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        for attempt in range(3):
            resp = self.session.get(
                SEARCH_URL,
                params=params,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30,
            )
            self.last_request = time.time()
            if resp.status_code == 429:
                time.sleep(float(resp.headers.get("Retry-After", 2) or 2))
                continue
            if resp.status_code == 401:
                self.token = ""
                self._ensure_token()
                continue
            # 200 = page pleine, 206 = contenu partiel (pagination), 204 = aucun résultat
            if resp.status_code == 204:
                return [], 0
            if resp.status_code in (200, 206):
                total = _parse_content_range(resp.headers.get("Content-Range", ""))
                return resp.json().get("resultats", []), total
            if resp.status_code >= 500 and attempt < 2:
                time.sleep(2)
                continue
            resp.raise_for_status()
        return [], 0

    def search_segment(self, base_params: dict) -> tuple[list[dict], int]:
        """Récupère toutes les pages d'un segment (jusqu'au cap). Retourne (offres, total annoncé)."""
        offres, start = [], 0
        total = 0
        while start <= RANGE_CAP:
            params = dict(base_params, range=f"{start}-{min(start + PAGE_SIZE - 1, RANGE_CAP + PAGE_SIZE - 1)}")
            page, total = self._search_page(params)
            offres.extend(page)
            if not page or start + PAGE_SIZE >= total:
                break
            start += PAGE_SIZE
        return offres, total


def _parse_content_range(header: str) -> int:
    # Format: "offres p-d/total"
    if "/" in header:
        try:
            return int(header.rsplit("/", 1)[1])
        except ValueError:
            return 0
    return 0


def _convert(raw: dict) -> dict:
    lieu = raw.get("lieuTravail") or {}
    commune = lieu.get("commune", "")  # code INSEE, ex. "75101"
    departement = ""
    if commune[:2].isdigit():
        departement = commune[:3] if commune[:2] == "97" else commune[:2]
    elif commune[:2] in ("2A", "2B"):
        departement = commune[:2]
    ville = (lieu.get("libelle") or "").split(" - ")[-1].strip()

    salaire_txt = (raw.get("salaire") or {}).get("libelle", "")
    sal_min, sal_max = parse_salary(salaire_txt)

    contrat = normalize_contract(
        " ".join(filter(None, [raw.get("typeContrat", ""), raw.get("natureContrat", ""), raw.get("typeContratLibelle", "")]))
    )
    if raw.get("alternance"):
        contrat = "Alternance"

    # Une mission d'intérim est par construction postée par une agence.
    employeur_type = "esn" if raw.get("typeContrat") == "MIS" else ""

    entreprise = (raw.get("entreprise") or {}).get("nom", "") or "Employeur confidentiel"
    url = (raw.get("origineOffre") or {}).get("urlOrigine", "") or (
        f"https://candidat.francetravail.fr/offres/recherche/detail/{raw.get('id', '')}"
    )

    return make_job(
        source="france_travail",
        ref=str(raw.get("id", "")),
        titre=raw.get("intitule", ""),
        entreprise=entreprise,
        url=url,
        ville=ville,
        departement=departement,
        lat=lieu.get("latitude"),
        lon=lieu.get("longitude"),
        contrat=contrat,
        teletravail=normalize_remote(raw.get("intitule", "") + " " + (raw.get("description") or "")[:500]),
        salaire_min=sal_min,
        salaire_max=sal_max,
        date_publication=(raw.get("dateCreation") or "")[:10],
        description=(raw.get("description") or "")[:4000],
        employeur_type=employeur_type,
    )


def fetch_france_travail() -> list[dict]:
    """Récupère les offres tech France Travail. Retourne [] si identifiants absents."""
    client_id = os.environ.get("FT_CLIENT_ID", "")
    client_secret = os.environ.get("FT_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("France Travail : FT_CLIENT_ID/FT_CLIENT_SECRET absents, source ignorée.", file=sys.stderr)
        return []

    client = FranceTravailClient(client_id, client_secret)
    seen: dict[str, dict] = {}

    def collect(base_params: dict, label: str) -> None:
        offres, total = client.search_segment(base_params)
        if total > RANGE_CAP and "departement" not in base_params:
            # Trop de résultats pour la pagination : on segmente par département.
            print(f"  FT [{label}] {total} offres -> segmentation par département", file=sys.stderr)
            for dept in DEPARTEMENTS:
                collect(dict(base_params, departement=dept), f"{label}/{dept}")
            return
        for raw in offres:
            ref = str(raw.get("id", ""))
            if ref and ref not in seen:
                seen[ref] = raw

    try:
        for domaine in DOMAINES:
            collect({"domaine": domaine}, f"domaine={domaine}")
        for mots in MOTS_CLES:
            collect({"motsCles": mots}, f"mots={mots}")
    except Exception as exc:  # noqa: BLE001 - une panne FT ne doit pas stopper le run quotidien
        print(
            f"France Travail : échec ({type(exc).__name__}: {exc}), "
            f"on garde {len(seen)} offres déjà récupérées.",
            file=sys.stderr,
        )

    jobs = [_convert(raw) for raw in seen.values()]
    print(f"France Travail : {len(jobs)} offres uniques", file=sys.stderr)
    return jobs


if __name__ == "__main__":
    result = fetch_france_travail()
    print(len(result))
    for job in result[:5]:
        print(job)
