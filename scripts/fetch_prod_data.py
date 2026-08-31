"""Télécharge les données actuellement en production vers un dossier local.

Utilisé par le workflow de déploiement "front seul" : publier une correction
de site sans refaire une collecte. Stdlib uniquement (pas de pip install en CI).

Usage : python scripts/fetch_prod_data.py <dossier_destination>
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

SITE_URL = os.environ.get("SITE_URL", "https://poptocrack.github.io/jobz/")
EXTRAS = ["analytics.json", "history.json", "seen_ids.json"]


def fetch(name: str) -> bytes:
    with urllib.request.urlopen(SITE_URL.rstrip("/") + "/data/" + name, timeout=30) as resp:
        return resp.read()


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)

    manifest_bytes = fetch("manifest.json")
    manifest = json.loads(manifest_bytes)
    (out / "manifest.json").write_bytes(manifest_bytes)

    files = [c["file"] for c in manifest["chunks"]] + EXTRAS
    for name in files:
        try:
            (out / name).write_bytes(fetch(name))
        except Exception as exc:  # noqa: BLE001 - les extras peuvent manquer sur un vieux déploiement
            if name in EXTRAS:
                print(f"optionnel absent : {name} ({exc})", file=sys.stderr)
            else:
                raise
    print(f"{len(files)} fichier(s) récupérés depuis la prod ({manifest['total']} offres, "
          f"générées {manifest['generated_at']})", file=sys.stderr)


if __name__ == "__main__":
    main()
