from scripts.esn import is_esn_name
from scripts.normalize import detect_esn_signals, make_job


class TestListePrestataires:
    def test_esn_connues(self):
        assert is_esn_name("Capgemini")
        assert is_esn_name("Sopra Steria")
        assert is_esn_name("mc2i")
        assert is_esn_name("ALTEN")

    def test_cabinets_et_interim(self):
        assert is_esn_name("Michael Page")
        assert is_esn_name("Adecco")

    def test_clients_finaux_non_matches(self):
        assert not is_esn_name("Doctolib")
        assert not is_esn_name("Back Market")
        # Pas de match partiel : "Open" est une ESN mais pas "OpenClassrooms".
        assert not is_esn_name("OpenClassrooms")


class TestSignauxTextuels:
    def test_signaux_positifs(self):
        assert detect_esn_signals("Nous recrutons pour notre client un développeur Java")
        assert detect_esn_signals("Mission en régie chez un grand compte bancaire")
        assert detect_esn_signals("Notre cabinet de recrutement recherche…")
        assert detect_esn_signals("Vous interviendrez chez nos clients grands comptes")

    def test_signaux_negatifs(self):
        assert not detect_esn_signals("Rejoignez notre équipe produit pour construire notre app")
        assert not detect_esn_signals("Nos clients utilisent notre plateforme SaaS chaque jour")


class TestMakeJob:
    def test_signaux_marquent_esn(self):
        job = make_job(source="france_travail", ref="1", titre="Dev Java",
                       entreprise="Petite ESN Locale", url="https://x",
                       description="Pour le compte de notre client bancaire, vous développerez…")
        assert job["employeur_type"] == "esn"

    def test_valeur_explicite_prioritaire(self):
        job = make_job(source="wttj", ref="2", titre="Dev", entreprise="Acme", url="https://x",
                       description="pour notre client…", employeur_type="client final")
        assert job["employeur_type"] == "client final"

    def test_sans_signal_reste_indetermine(self):
        job = make_job(source="adzuna", ref="3", titre="Dev", entreprise="Inconnue", url="https://x")
        assert job["employeur_type"] == ""
