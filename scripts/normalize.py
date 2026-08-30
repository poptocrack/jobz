"""Schéma d'offre normalisé et helpers de normalisation partagés par toutes les sources.

Schéma canonique d'une offre (dict) :
    id                : hash stable (source + référence source)
    titre             : intitulé du poste
    entreprise        : nom de l'entreprise
    ville             : ville (texte libre normalisé)
    departement       : code département ("75", "2A", "974") ou ""
    region            : nom de région ou ""
    lat, lon          : float ou None
    contrat           : CDI | CDD | Stage | Alternance | Freelance | Autre | ""
    teletravail       : total | hybride | sur site | ""
    salaire_min/max   : EUR brut annuel (int) ou None
    date_publication  : date ISO "YYYY-MM-DD" ou ""
    source            : france_travail | greenhouse | lever | ashby | recruitee
                        | smartrecruiters | workable | wttj | adzuna
    url               : URL de candidature
    tags              : liste de technos détectées
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

CONTRATS = ("CDI", "CDD", "Stage", "Alternance", "Freelance", "Autre")

# Motifs -> contrat canonique, testés dans l'ordre (le premier qui matche gagne).
_CONTRAT_PATTERNS = [
    (r"\balternan|apprentissage|apprenti|professionnalisation\b", "Alternance"),
    (r"\bstage\b|stagiaire|\bintern(ship)?\b", "Stage"),
    (r"\bfreelance\b|\bind[ée]pendant\b|\bcontractor\b|\bmission\b.*\bfreelance\b|liberal", "Freelance"),
    (r"\bcdd\b|dur[ée]e d[ée]termin[ée]e|fixed[- ]term|\btemporary\b|\bsaisonnier\b|\binterim\b|int[ée]rim", "CDD"),
    (r"\bcdi\b|dur[ée]e ind[ée]termin[ée]e|\bpermanent\b|full[- ]?time|\bfull_time\b|temps plein", "CDI"),
]

_REMOTE_PATTERNS = [
    (r"full[- ]?remote|fully remote|100\s*%\s*remote|remote[- ]first|t[ée]l[ée]travail (total|complet|100)", "total"),
    (r"\bhybrid|hybride|partiel|ponctuel|flexible remote|remote friendly|occasionnel", "hybride"),
    (r"on[- ]?site|sur site|pr[ée]sentiel|no remote|non autoris", "sur site"),
    (r"\bremote\b|t[ée]l[ée]travail", "total"),
]

# Technos détectées dans titre + description pour les tags.
_TAGS = [
    "python", "javascript", "typescript", "java", "kotlin", "swift", "objective-c",
    "go", "golang", "rust", "c++", "c#", ".net", "php", "ruby", "scala", "elixir",
    "react", "react native", "vue", "angular", "svelte", "next.js", "node", "node.js",
    "django", "flask", "fastapi", "rails", "laravel", "symfony", "spring",
    "flutter", "android", "ios",
    "aws", "gcp", "azure", "kubernetes", "docker", "terraform", "ansible",
    "postgresql", "postgres", "mysql", "mongodb", "redis", "elasticsearch", "kafka",
    "spark", "airflow", "dbt", "snowflake", "bigquery",
    "machine learning", "deep learning", "data science", "nlp", "llm",
    "devops", "sre", "cybersécurité", "blockchain",
    "product manager", "product owner", "scrum", "agile", "ux", "ui",
    "qa", "test automation", "embedded", "embarqué", "sap", "salesforce",
]
_TAG_RES = [(t, re.compile(r"(?<![\w+#.])" + re.escape(t) + r"(?![\w+])", re.IGNORECASE)) for t in _TAGS]

# Alias -> tag canonique pour éviter les doublons de tags.
_TAG_ALIASES = {"golang": "go", "node.js": "node", "postgres": "postgresql", "embarqué": "embedded"}


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def slugify(text: str) -> str:
    text = strip_accents(text.lower())
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def norm_text(text: str) -> str:
    """Forme canonique pour comparaisons (dédoublonnage) : minuscules, sans accents ni ponctuation."""
    text = strip_accents((text or "").lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def stable_id(source: str, ref: str) -> str:
    return hashlib.sha1(f"{source}:{ref}".encode()).hexdigest()[:16]


def normalize_contract(raw: str) -> str:
    """Déduit le type de contrat depuis un libellé libre (FR ou EN)."""
    if not raw:
        return ""
    low = strip_accents(raw.lower())
    for pattern, contrat in _CONTRAT_PATTERNS:
        if re.search(pattern, low):
            return contrat
    return "Autre"


def normalize_remote(raw: str) -> str:
    """Déduit la politique de télétravail depuis un libellé libre (FR ou EN)."""
    if not raw:
        return ""
    low = strip_accents(raw.lower())
    for pattern, mode in _REMOTE_PATTERNS:
        if re.search(pattern, low):
            return mode
    return ""


# Nombre : soit milliers groupés ("45 000", "45.000"), soit entier simple ("2500").
_SAL_NUM = r"(\d{1,3}(?:[   .,]\d{3})+|\d+(?:[.,]\d{1,2})?)\s*(k€|k)?"
# "45-55k" : le premier nombre d'une fourchette hérite du suffixe k du second.
_RANGE_K = re.compile(r"(\d+)(\s*[-–—/aà]\s*)(\d+)\s*k", re.IGNORECASE)


# Bornes de plausibilité d'un brut annuel sur ce marché.
SALARY_ANNUAL_MIN = 8000
SALARY_ANNUAL_MAX = 400000
# Au-delà, un montant déclaré "mensuel" est en réalité un annuel mal saisi
# (fréquent sur France Travail : "Mensuel de 45000.0 Euros").
MONTHLY_MAX_PLAUSIBLE = 15000


def _to_annual_eur(value: float, unit_hint: str, k_flag: bool) -> int | None:
    if k_flag:
        value *= 1000
    if unit_hint == "mois":
        value = value if value > MONTHLY_MAX_PLAUSIBLE else value * 12
    elif unit_hint == "jour":
        value *= 218  # jours ouvrés/an, approximation TJM -> annuel
    elif unit_hint == "heure":
        value *= 1607
    if value < SALARY_ANNUAL_MIN or value > SALARY_ANNUAL_MAX:
        return None
    return int(round(value / 100.0) * 100)


def parse_salary_details(raw: str) -> dict:
    """Extrait un salaire depuis un libellé libre.

    Retourne {"annual_min", "annual_max", "tjm_min", "tjm_max"} (None si absents).
    Un taux journalier ("TJM 500 €/jour") est conservé tel quel en tjm_* ET
    annualisé (×218) en annual_* pour les tris/filtres.
    Gère "45-55k€", "45 000 - 55 000 € / an", "2500 € par mois", "TJM 500€/jour".
    """
    out = {"annual_min": None, "annual_max": None, "tjm_min": None, "tjm_max": None}
    if not raw:
        return out
    low = strip_accents(raw.lower())
    low = re.sub(r"sur\s+\d+(?:[.,]\d+)?\s*(mois|an(?:nee)?s?)", " ", low)
    low = _RANGE_K.sub(r"\1k\2\3k", low)
    unit = "an"
    if re.search(r"/\s*mois|par mois|mensuel|month", low):
        unit = "mois"
    elif re.search(r"/\s*j(our)?\b|par jour|tjm|/\s*day|daily", low):
        unit = "jour"
    elif re.search(r"/\s*h(eure)?\b|par heure|horaire|hour", low):
        unit = "heure"

    annuals, dailies = [], []
    for num, k in re.findall(_SAL_NUM, low):
        if re.fullmatch(r"\d+[.,]\d{1,2}", num):
            cleaned = num.replace(",", ".")
        else:
            cleaned = re.sub(r"[   .,]", "", num)
        try:
            value = float(cleaned)
        except ValueError:
            continue
        annual = _to_annual_eur(value, unit, bool(k))
        if annual:
            annuals.append(annual)
            if unit == "jour" and 100 <= value <= 3000 and not k:
                dailies.append(int(value))
    if annuals:
        out["annual_min"], out["annual_max"] = min(annuals), max(annuals)
    if dailies:
        out["tjm_min"], out["tjm_max"] = min(dailies), max(dailies)
    return out


def parse_salary(raw: str) -> tuple[int | None, int | None]:
    """Extrait (min, max) en EUR brut annuel depuis un libellé libre."""
    details = parse_salary_details(raw)
    return details["annual_min"], details["annual_max"]


def extract_tags(text: str) -> list[str]:
    found = []
    for tag, tag_re in _TAG_RES:
        if tag_re.search(text):
            canonical = _TAG_ALIASES.get(tag, tag)
            if canonical not in found:
                found.append(canonical)
    return found[:12]


# Signaux textuels d'une offre postée par un prestataire (ESN, cabinet, intérim).
_ESN_SIGNALS = re.compile(
    r"pour (le compte d[e'] ?)?(notre|nos|l[e']un de nos) clients?"
    r"|chez (notre|nos|l[e']un de nos) clients?"
    r"|aupres de (notre|nos) clients?"
    r"|\ben regie\b"
    r"|cabinet de (recrutement|conseil)"
    r"|societe de conseil"
    r"|\besn\b|\bssii\b"
    r"|agence (d[e'] ?interim|de travail temporaire)"
    r"|vous interviendrez (chez|aupres)"
    r"|nos consultants intervienn",
)


def detect_esn_signals(text: str) -> bool:
    """Le texte (titre + description) trahit-il une offre de prestataire ?"""
    return bool(_ESN_SIGNALS.search(strip_accents((text or "").lower())))


def make_job(
    *,
    source: str,
    ref: str,
    titre: str,
    entreprise: str,
    url: str,
    ville: str = "",
    departement: str = "",
    region: str = "",
    lat: float | None = None,
    lon: float | None = None,
    contrat: str = "",
    teletravail: str = "",
    salaire_min: int | None = None,
    salaire_max: int | None = None,
    tjm_min: int | None = None,
    tjm_max: int | None = None,
    date_publication: str = "",
    description: str = "",
    employeur_type: str = "",
) -> dict:
    """Construit une offre au schéma canonique.

    `description` sert aux tags et à la détection de signaux ESN.
    `employeur_type` : "esn" | "client final" | "" ; si vide, les signaux
    textuels peuvent le passer à "esn" (jamais à "client final").
    """
    titre = re.sub(r"\s+", " ", titre or "").strip()
    if not employeur_type and detect_esn_signals(f"{titre}\n{description[:4000]}"):
        employeur_type = "esn"
    return {
        "id": stable_id(source, ref),
        "titre": titre,
        "entreprise": (entreprise or "").strip(),
        "ville": (ville or "").strip(),
        "departement": departement or "",
        "region": region or "",
        "lat": lat,
        "lon": lon,
        "contrat": contrat,
        "teletravail": teletravail,
        "salaire_min": salaire_min,
        "salaire_max": salaire_max,
        "tjm_min": tjm_min,
        "tjm_max": tjm_max,
        "date_publication": (date_publication or "")[:10],
        "source": source,
        "url": url,
        "tags": extract_tags(f"{titre}\n{description[:4000]}"),
        "employeur_type": employeur_type,
    }
