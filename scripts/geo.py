"""Enrichissement géographique : départements, régions, géocodage des villes.

- Référentiel statique département -> (nom, région) pour résoudre les codes.
- Géocodage des villes sans lat/lon via l'API Adresse (api-adresse.data.gouv.fr,
  gratuite, ~50 req/s autorisées), avec cache JSON persistant.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from scripts.http_util import make_session
from scripts.normalize import norm_text

GEO_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "geo_cache.json"
ADRESSE_URL = "https://api-adresse.data.gouv.fr/search/"

# Code département -> (nom, région)
DEPARTEMENTS: dict[str, tuple[str, str]] = {
    "01": ("Ain", "Auvergne-Rhône-Alpes"), "02": ("Aisne", "Hauts-de-France"),
    "03": ("Allier", "Auvergne-Rhône-Alpes"), "04": ("Alpes-de-Haute-Provence", "Provence-Alpes-Côte d'Azur"),
    "05": ("Hautes-Alpes", "Provence-Alpes-Côte d'Azur"), "06": ("Alpes-Maritimes", "Provence-Alpes-Côte d'Azur"),
    "07": ("Ardèche", "Auvergne-Rhône-Alpes"), "08": ("Ardennes", "Grand Est"),
    "09": ("Ariège", "Occitanie"), "10": ("Aube", "Grand Est"),
    "11": ("Aude", "Occitanie"), "12": ("Aveyron", "Occitanie"),
    "13": ("Bouches-du-Rhône", "Provence-Alpes-Côte d'Azur"), "14": ("Calvados", "Normandie"),
    "15": ("Cantal", "Auvergne-Rhône-Alpes"), "16": ("Charente", "Nouvelle-Aquitaine"),
    "17": ("Charente-Maritime", "Nouvelle-Aquitaine"), "18": ("Cher", "Centre-Val de Loire"),
    "19": ("Corrèze", "Nouvelle-Aquitaine"), "21": ("Côte-d'Or", "Bourgogne-Franche-Comté"),
    "22": ("Côtes-d'Armor", "Bretagne"), "23": ("Creuse", "Nouvelle-Aquitaine"),
    "24": ("Dordogne", "Nouvelle-Aquitaine"), "25": ("Doubs", "Bourgogne-Franche-Comté"),
    "26": ("Drôme", "Auvergne-Rhône-Alpes"), "27": ("Eure", "Normandie"),
    "28": ("Eure-et-Loir", "Centre-Val de Loire"), "29": ("Finistère", "Bretagne"),
    "2A": ("Corse-du-Sud", "Corse"), "2B": ("Haute-Corse", "Corse"),
    "30": ("Gard", "Occitanie"), "31": ("Haute-Garonne", "Occitanie"),
    "32": ("Gers", "Occitanie"), "33": ("Gironde", "Nouvelle-Aquitaine"),
    "34": ("Hérault", "Occitanie"), "35": ("Ille-et-Vilaine", "Bretagne"),
    "36": ("Indre", "Centre-Val de Loire"), "37": ("Indre-et-Loire", "Centre-Val de Loire"),
    "38": ("Isère", "Auvergne-Rhône-Alpes"), "39": ("Jura", "Bourgogne-Franche-Comté"),
    "40": ("Landes", "Nouvelle-Aquitaine"), "41": ("Loir-et-Cher", "Centre-Val de Loire"),
    "42": ("Loire", "Auvergne-Rhône-Alpes"), "43": ("Haute-Loire", "Auvergne-Rhône-Alpes"),
    "44": ("Loire-Atlantique", "Pays de la Loire"), "45": ("Loiret", "Centre-Val de Loire"),
    "46": ("Lot", "Occitanie"), "47": ("Lot-et-Garonne", "Nouvelle-Aquitaine"),
    "48": ("Lozère", "Occitanie"), "49": ("Maine-et-Loire", "Pays de la Loire"),
    "50": ("Manche", "Normandie"), "51": ("Marne", "Grand Est"),
    "52": ("Haute-Marne", "Grand Est"), "53": ("Mayenne", "Pays de la Loire"),
    "54": ("Meurthe-et-Moselle", "Grand Est"), "55": ("Meuse", "Grand Est"),
    "56": ("Morbihan", "Bretagne"), "57": ("Moselle", "Grand Est"),
    "58": ("Nièvre", "Bourgogne-Franche-Comté"), "59": ("Nord", "Hauts-de-France"),
    "60": ("Oise", "Hauts-de-France"), "61": ("Orne", "Normandie"),
    "62": ("Pas-de-Calais", "Hauts-de-France"), "63": ("Puy-de-Dôme", "Auvergne-Rhône-Alpes"),
    "64": ("Pyrénées-Atlantiques", "Nouvelle-Aquitaine"), "65": ("Hautes-Pyrénées", "Occitanie"),
    "66": ("Pyrénées-Orientales", "Occitanie"), "67": ("Bas-Rhin", "Grand Est"),
    "68": ("Haut-Rhin", "Grand Est"), "69": ("Rhône", "Auvergne-Rhône-Alpes"),
    "70": ("Haute-Saône", "Bourgogne-Franche-Comté"), "71": ("Saône-et-Loire", "Bourgogne-Franche-Comté"),
    "72": ("Sarthe", "Pays de la Loire"), "73": ("Savoie", "Auvergne-Rhône-Alpes"),
    "74": ("Haute-Savoie", "Auvergne-Rhône-Alpes"), "75": ("Paris", "Île-de-France"),
    "76": ("Seine-Maritime", "Normandie"), "77": ("Seine-et-Marne", "Île-de-France"),
    "78": ("Yvelines", "Île-de-France"), "79": ("Deux-Sèvres", "Nouvelle-Aquitaine"),
    "80": ("Somme", "Hauts-de-France"), "81": ("Tarn", "Occitanie"),
    "82": ("Tarn-et-Garonne", "Occitanie"), "83": ("Var", "Provence-Alpes-Côte d'Azur"),
    "84": ("Vaucluse", "Provence-Alpes-Côte d'Azur"), "85": ("Vendée", "Pays de la Loire"),
    "86": ("Vienne", "Nouvelle-Aquitaine"), "87": ("Haute-Vienne", "Nouvelle-Aquitaine"),
    "88": ("Vosges", "Grand Est"), "89": ("Yonne", "Bourgogne-Franche-Comté"),
    "90": ("Territoire de Belfort", "Bourgogne-Franche-Comté"), "91": ("Essonne", "Île-de-France"),
    "92": ("Hauts-de-Seine", "Île-de-France"), "93": ("Seine-Saint-Denis", "Île-de-France"),
    "94": ("Val-de-Marne", "Île-de-France"), "95": ("Val-d'Oise", "Île-de-France"),
    "971": ("Guadeloupe", "Guadeloupe"), "972": ("Martinique", "Martinique"),
    "973": ("Guyane", "Guyane"), "974": ("La Réunion", "La Réunion"),
    "976": ("Mayotte", "Mayotte"),
}

# Nom de département normalisé -> code (pour WTTJ qui donne le nom).
_NAME_TO_CODE = {norm_text(name): code for code, (name, _) in DEPARTEMENTS.items()}


def departement_code(name_or_code: str) -> str:
    value = (name_or_code or "").strip()
    if value in DEPARTEMENTS:
        return value
    return _NAME_TO_CODE.get(norm_text(value), "")


def region_of(dept_code: str) -> str:
    return DEPARTEMENTS.get(dept_code, ("", ""))[1]


def _load_cache() -> dict:
    if GEO_CACHE_PATH.exists():
        try:
            return json.loads(GEO_CACHE_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    GEO_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GEO_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, sort_keys=True))


def _geocode_city(session, city: str) -> dict | None:
    """Retourne {lat, lon, dept} pour une ville, ou None si introuvable."""
    try:
        resp = session.get(
            ADRESSE_URL,
            params={"q": city, "type": "municipality", "limit": 1},
            timeout=15,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
    except Exception:  # noqa: BLE001 - le géocodage est un enrichissement optionnel
        return None
    if not features:
        return None
    feature = features[0]
    lon, lat = feature["geometry"]["coordinates"]
    citycode = feature["properties"].get("citycode", "")
    dept = citycode[:3] if citycode.startswith("97") else citycode[:2]
    return {"lat": round(lat, 5), "lon": round(lon, 5), "dept": dept}


# Boîtes englobantes France métropolitaine + DOM, pour invalider les géolocs aberrantes.
_FR_BOUNDS = [
    (41.0, 51.2, -5.8, 10.0),    # métropole + Corse (51.2 exclut Londres/Bruxelles… au nord)
    (14.0, 18.6, -63.5, -60.0),  # Guadeloupe / Martinique
    (2.0, 6.5, -55.5, -51.0),    # Guyane
    (-21.6, -20.6, 55.0, 56.0),  # La Réunion
    (-13.2, -12.4, 44.8, 45.5),  # Mayotte
]


def _in_france(lat: float, lon: float) -> bool:
    return any(a <= lat <= b and c <= lon <= d for a, b, c, d in _FR_BOUNDS)


def enrich_geo(jobs: list[dict]) -> None:
    """Complète en place departement/region/lat/lon des offres.

    - Invalide les lat/lon hors de France (géoloc source mal alignée), re-géocodés ensuite.
    - Résout les codes département depuis les noms (WTTJ) ou codes (FT).
    - Déduit la région depuis le département.
    - Géocode les villes sans lat/lon (cache persistant).
    """
    session = make_session()
    cache = _load_cache()
    cache_dirty = False

    for job in jobs:
        if job["lat"] is not None and job["lon"] is not None and not _in_france(job["lat"], job["lon"]):
            job["lat"] = job["lon"] = None

        if job["departement"]:
            job["departement"] = departement_code(job["departement"])

        needs_geocode = (job["lat"] is None or job["lon"] is None) and job["ville"]
        needs_dept = not job["departement"] and job["ville"]
        if needs_geocode or needs_dept:
            # Clé de cache : ville seule (les homonymes ambigus restent rares
            # et l'API renvoie la commune la plus peuplée, acceptable ici).
            key = norm_text(job["ville"])
            if key and len(key) > 1:
                if key not in cache:
                    cache[key] = _geocode_city(session, job["ville"])
                    cache_dirty = True
                    time.sleep(0.05)
                hit = cache.get(key)
                if hit:
                    if job["lat"] is None or job["lon"] is None:
                        job["lat"], job["lon"] = hit["lat"], hit["lon"]
                    if not job["departement"]:
                        job["departement"] = hit["dept"]

        if not job["region"] or job["departement"]:
            region = region_of(job["departement"])
            if region:
                job["region"] = region

    if cache_dirty:
        _save_cache(cache)
    located = sum(1 for j in jobs if j["lat"] is not None)
    print(f"Géo : {located}/{len(jobs)} offres géolocalisées", file=sys.stderr)
