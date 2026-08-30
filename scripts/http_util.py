"""Session HTTP partagée : retries, timeout, User-Agent identifiable."""

from __future__ import annotations

import time

import requests

USER_AGENT = "jobz-aggregator/1.0 (+https://github.com/tristandebroise/jobz)"
DEFAULT_TIMEOUT = 20


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return session


def get_json(session: requests.Session, url: str, *, params=None, headers=None, retries: int = 2):
    """GET JSON avec retries sur erreurs transitoires. Retourne None sur 404 (slug inexistant)."""
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code == 404:
            return None
        if resp.status_code == 429:
            wait = float(resp.headers.get("Retry-After", 2) or 2)
            time.sleep(min(wait, 30))
            continue
        if resp.status_code >= 500 and attempt < retries:
            time.sleep(1.5 * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json()
    raise requests.HTTPError(f"Épuisement des retries sur {url}")
