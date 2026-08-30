from scripts.dedupe import dedupe
from scripts.normalize import make_job


def job(source, titre, entreprise="Acme", ville="Paris", **kwargs):
    return make_job(
        source=source, ref=f"{source}-{titre}", titre=titre,
        entreprise=entreprise, url=f"https://{source}.example/x", ville=ville, **kwargs,
    )


def test_meme_offre_deux_sources_garde_ats():
    ats = job("lever", "Data Engineer H/F")
    wttj = job("wttj", "Data Engineer", salaire_min=50000)
    result = dedupe([wttj, ats])
    assert len(result) == 1
    assert result[0]["source"] == "lever"
    # Le salaire de WTTJ complète l'offre ATS qui n'en avait pas.
    assert result[0]["salaire_min"] == 50000


def test_titres_differents_pas_fusionnes():
    result = dedupe([job("wttj", "Data Engineer"), job("wttj", "Data Scientist")])
    assert len(result) == 2


def test_villes_differentes_pas_fusionnees():
    result = dedupe([job("wttj", "Dev", ville="Paris"), job("wttj", "Dev", ville="Lyon")])
    assert len(result) == 2


def test_suffixe_juridique_ignore():
    result = dedupe([job("lever", "Dev", entreprise="Acme SAS"), job("adzuna", "Dev", entreprise="Acme")])
    assert len(result) == 1
    assert result[0]["source"] == "lever"


def test_employeur_confidentiel_jamais_fusionne():
    a = make_job(source="france_travail", ref="offre-1", titre="Dev Python",
                 entreprise="", url="https://ft.example/1", ville="Paris")
    b = make_job(source="france_travail", ref="offre-2", titre="Dev Python",
                 entreprise="", url="https://ft.example/2", ville="Paris")
    result = dedupe([a, b])
    assert len(result) == 2
