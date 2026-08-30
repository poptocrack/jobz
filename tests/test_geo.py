from scripts.geo import _in_france, departement_code, region_of


def test_departement_depuis_code():
    assert departement_code("75") == "75"
    assert departement_code("2A") == "2A"
    assert departement_code("974") == "974"


def test_departement_depuis_nom():
    assert departement_code("Val-de-Marne") == "94"
    assert departement_code("Bouches-du-Rhône") == "13"
    assert departement_code("bouches du rhone") == "13"
    assert departement_code("Inexistant") == ""


def test_region():
    assert region_of("75") == "Île-de-France"
    assert region_of("69") == "Auvergne-Rhône-Alpes"
    assert region_of("") == ""


def test_in_france():
    assert _in_france(48.85, 2.35)        # Paris
    assert _in_france(-20.9, 55.5)        # La Réunion
    assert not _in_france(51.5, -0.12)    # Londres
    assert not _in_france(40.7, -74.0)    # New York
