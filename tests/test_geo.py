from scripts.geo import (
    _correspond,
    _geocode_city,
    _in_france,
    clean_city,
    departement_code,
    region_of,
)


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


def test_clean_city_ecarte_les_non_villes():
    assert clean_city("France") == ""
    assert clean_city("Île-de-France, France") == ""
    assert clean_city("France - Remote") == ""
    assert clean_city("Remote") == ""
    assert clean_city("") == ""


def test_clean_city_garde_la_commune():
    assert clean_city("Paris, France") == "Paris"
    assert clean_city("Béthune, Pas-de-Calais, France") == "Béthune"
    assert clean_city("Nantes") == "Nantes"
    # Communes dont le nom contient "France" : jamais tronquées.
    assert clean_city("Roissy-en-France") == "Roissy-en-France"
    assert clean_city("Fort-de-France") == "Fort-de-France"


def test_correspond_accepte_les_vraies_communes():
    assert _correspond("Paris 15e", "Paris 15e Arrondissement")
    assert _correspond("15ème arrondissement", "Paris 15e Arrondissement")
    assert _correspond("plessis robinson", "Le Plessis-Robinson")
    assert _correspond("marcq en baroeul", "Marcq-en-Barœul")
    assert _correspond("Salanches", "Sallanches")  # faute de frappe de la source


def test_correspond_rejette_les_rapprochements_fantaisistes():
    assert not _correspond("France", "Fort-de-France")
    assert not _correspond("Val-de-Marne", "Val-des-Marais")
    assert not _correspond("Hautes-Alpes", "Châteauroux-les-Alpes")
    assert not _correspond("New Orleans LA", "Orléans")


class _FakeResponse:
    def __init__(self, features):
        self._features = features

    def raise_for_status(self):
        pass

    def json(self):
        return {"features": self._features}


class _FakeSession:
    def __init__(self, features):
        self._features = features

    def get(self, url, params=None, timeout=None):
        return _FakeResponse(self._features)


def _feature(name, citycode, lat, lon):
    return {"properties": {"name": name, "citycode": citycode},
            "geometry": {"coordinates": [lon, lat]}}


SAINT_DENIS = [_feature("Saint-Denis", "97411", -20.88, 55.45),
               _feature("Saint-Denis", "93066", 48.93, 2.35)]


def test_geocodage_choisit_l_homonyme_du_departement_connu():
    hit = _geocode_city(_FakeSession(SAINT_DENIS), "Saint-Denis", "93")
    assert hit["dept"] == "93"
    assert hit["lat"] == 48.93


def test_geocodage_sans_departement_garde_le_premier_candidat():
    hit = _geocode_city(_FakeSession(SAINT_DENIS), "Saint-Denis")
    assert hit["dept"] == "974"


def test_geocodage_refuse_une_commune_qui_ne_correspond_pas():
    fort_de_france = [_feature("Fort-de-France", "97209", 14.63, -61.06)]
    assert _geocode_city(_FakeSession(fort_de_france), "France") is None


def test_geocodage_fait_confiance_a_un_code_postal():
    sens = [_feature("Sens", "89387", 48.19, 3.28)]
    assert _geocode_city(_FakeSession(sens), "89100")["dept"] == "89"
