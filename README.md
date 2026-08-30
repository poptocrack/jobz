# jobz — L'emploi tech en France

Agrégateur d'offres d'emploi tech centré sur le marché français : startups, scale-ups et
entreprises, toutes sources confondues, mis à jour quotidiennement. Équivalent français de
[job-board-aggregator](https://github.com/Feashliaa/job-board-aggregator), repensé pour le
paysage ATS français.

Architecture 100 % statique : pipeline Python quotidien (GitHub Actions) qui produit des
JSON gzippés, servis avec un front vanilla JS sur GitHub Pages. Zéro serveur, zéro coût.

## Sources

| Source | Type | Identifiants |
|---|---|---|
| Sites carrière (Greenhouse, Lever, Ashby, Recruitee, SmartRecruiters, Workable) | APIs JSON publiques par entreprise (`companies.json`) | aucun |
| Welcome to the Jungle | index Algolia public du site (non officiel, peut casser) | aucun |
| France Travail | API officielle "Offres d'emploi v2" | `FT_CLIENT_ID` / `FT_CLIENT_SECRET` ([francetravail.io](https://francetravail.io)) |
| Adzuna | API officielle, catégorie IT | `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` ([developer.adzuna.com](https://developer.adzuna.com)) |

Le pipeline dédoublonne les offres présentes sur plusieurs canaux (priorité au site carrière
de l'entreprise), normalise contrat / télétravail / salaire, et géocode les villes via
l'API Adresse (data.gouv.fr).

## Lancer en local

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
cp .env.example .env   # remplir les clés disponibles (les sources sans clé sont ignorées)

# Construire les données (data/)
set -a; source .env; set +a
.venv/bin/python -m scripts.build

# Servir le front
.venv/bin/python -m http.server 8742
# puis ouvrir http://127.0.0.1:8742/site/
```

## Enrichir la liste d'entreprises

```bash
# Sonder les noms de seed_candidates.json sur tous les ATS
.venv/bin/python -m scripts.discover --probe

# Découverte massive via les index Common Crawl (lourd, à lancer ponctuellement)
.venv/bin/python -m scripts.discover --cc lever --cc-max-pages 2

# Extraire des slugs ATS depuis un fichier d'URLs de candidature
.venv/bin/python -m scripts.discover --from-file urls.txt
```

Chaque hit est vérifié (le board existe et contient au moins une offre en France) avant
d'entrer dans `companies.json`.

## Déploiement

1. Créer le repo GitHub et pousser.
2. Renseigner les secrets Actions : `FT_CLIENT_ID`, `FT_CLIENT_SECRET`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`.
3. Activer GitHub Pages avec la source "GitHub Actions".
4. Lancer le workflow "Scrape & Deploy" (il tourne ensuite chaque matin à ~6h, heure de Paris).

Le workflow refuse de déployer si le volume total est anormalement bas (garde-fou en cas de
panne d'une source majeure). Les données ne sont jamais commitées : chaque run reconstruit
tout et déploie le site assemblé.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```
