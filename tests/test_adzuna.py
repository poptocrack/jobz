from scripts.sources.adzuna import _convert


def _job(area, display_name=""):
    return _convert({
        "id": "1",
        "title": "Développeur Python",
        "location": {"area": area, "display_name": display_name or ", ".join(reversed(area))},
    })


def test_localisation_complete():
    job = _job(["France", "Pays de la Loire", "Loire-Atlantique", "Nantes", "Carquefou"])
    assert job["ville"] == "Carquefou"
    assert job["departement"] == "Loire-Atlantique"
    assert job["region"] == "Pays de la Loire"


def test_localisation_sans_commune():
    job = _job(["France", "Bretagne", "Finistère"])
    assert job["ville"] == ""
    assert job["departement"] == "Finistère"
    assert job["region"] == "Bretagne"


def test_pays_seul_ne_donne_pas_de_ville():
    # Cas des offres full remote : Adzuna ne connaît que le pays. Recopier
    # display_name donnait ville="France", géocodée en Fort-de-France.
    job = _job(["France"])
    assert job["ville"] == ""
    assert job["departement"] == ""
    assert job["region"] == ""
