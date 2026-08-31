from scripts.normalize import (
    extract_tags,
    make_job,
    normalize_contract,
    normalize_remote,
    parse_salary,
    slugify,
    stable_id,
)


class TestContrat:
    def test_cdi_variants(self):
        assert normalize_contract("CDI") == "CDI"
        assert normalize_contract("Full-time") == "CDI"
        assert normalize_contract("Contrat à durée indéterminée") == "CDI"
        assert normalize_contract("full_time") == "CDI"

    def test_cdd_et_interim(self):
        assert normalize_contract("CDD 6 mois") == "CDD"
        assert normalize_contract("Temporary") == "CDD"
        assert normalize_contract("Intérim") == "CDD"

    def test_alternance_prioritaire_sur_cdd(self):
        # "Contrat d'apprentissage à durée déterminée" doit rester Alternance.
        assert normalize_contract("apprentissage durée déterminée") == "Alternance"
        assert normalize_contract("Alternance") == "Alternance"

    def test_stage_freelance(self):
        assert normalize_contract("Stage de fin d'études") == "Stage"
        assert normalize_contract("Internship") == "Stage"
        assert normalize_contract("Freelance") == "Freelance"

    def test_inconnu(self):
        assert normalize_contract("") == ""
        assert normalize_contract("Volontariat international") == "Autre"


class TestTeletravail:
    def test_total(self):
        assert normalize_remote("Full remote") == "total"
        assert normalize_remote("100 % remote") == "total"
        assert normalize_remote("Télétravail total") == "total"

    def test_hybride(self):
        assert normalize_remote("Hybrid") == "hybride"
        assert normalize_remote("Télétravail partiel") == "hybride"

    def test_sur_site(self):
        assert normalize_remote("On-site") == "sur site"
        assert normalize_remote("Présentiel") == "sur site"

    def test_inconnu(self):
        assert normalize_remote("") == ""
        assert normalize_remote("bureau sympa") == ""


class TestSalaire:
    def test_fourchette_k(self):
        assert parse_salary("45-55k€") == (45000, 55000)

    def test_fourchette_annuelle(self):
        assert parse_salary("45 000 - 55 000 € par an") == (45000, 55000)

    def test_mensuel(self):
        low, high = parse_salary("2500 € par mois")
        assert low == high == 30000

    def test_tjm(self):
        low, _ = parse_salary("TJM 500 € / jour")
        assert low == 109000

    def test_valeurs_absurdes_ignorees(self):
        assert parse_salary("13ème mois") == (None, None)
        assert parse_salary("") == (None, None)

    def test_annuel_saisi_dans_champ_mensuel(self):
        # Erreur de saisie fréquente (offre FT 213BPLB) : montants annuels
        # déclarés mensuels. Ne doit PAS être multiplié par 12.
        assert parse_salary("Mensuel de 45000.0 Euros à 50000.0 Euros sur 12.0 mois") == (45000, 50000)

    def test_decimales_et_duree(self):
        # "15.9" ne doit pas être lu comme 15 puis 9, et "sur 12.0 mois"
        # n'est pas un montant.
        low, high = parse_salary("Horaire de 15.9 Euros sur 12.0 mois")
        assert low == high == 25600

    def test_plafond_plausibilite(self):
        assert parse_salary("650 000 € par an") == (None, None)

    def test_fourchette_incoherente_max_ecarte(self):
        job = make_job(source="adzuna", ref="x", titre="Dev", entreprise="Acme",
                       url="https://a", salaire_min=30000, salaire_max=400000)
        assert job["salaire_min"] == 30000
        assert job["salaire_max"] is None


class TestTags:
    def test_detection_basique(self):
        tags = extract_tags("Développeur Python / React senior (AWS)")
        assert "python" in tags and "react" in tags and "aws" in tags

    def test_pas_de_faux_positifs_substring(self):
        # "go" ne doit pas matcher dans "Argos" ni "categories".
        assert "go" not in extract_tags("Chef de projet Argos categories")

    def test_alias(self):
        assert set(extract_tags("Node.js et Golang")) == {"node", "go"}


class TestFiltreFrance:
    def test_villes_francaises(self):
        from scripts.sources.ats import is_france_location
        assert is_france_location("Paris")
        assert is_france_location("Sophia Antipolis, France")
        assert is_france_location("Levallois-Perret")

    def test_etranger_rejete(self):
        from scripts.sources.ats import is_france_location
        assert not is_france_location("Berlin, Germany")
        assert not is_france_location("New York")
        assert not is_france_location("Remote (US)")
        assert not is_france_location("Remote - London")

    def test_remote_nu_accepte_pour_entreprises_fr(self):
        from scripts.sources.ats import is_france_location
        assert is_france_location("Remote")
        assert is_france_location("Full remote, France")
        assert not is_france_location("Remote", allow_bare_remote=False)


class TestDivers:
    def test_slugify(self):
        assert slugify("Alice & Bob") == "alice-bob"
        assert slugify("Éurécia") == "eurecia"

    def test_stable_id_deterministe(self):
        assert stable_id("wttj", "abc") == stable_id("wttj", "abc")
        assert stable_id("wttj", "abc") != stable_id("lever", "abc")

    def test_make_job_nettoie_titre(self):
        job = make_job(source="wttj", ref="x", titre="  Dev   Python \n", entreprise=" Acme ", url="https://a")
        assert job["titre"] == "Dev Python"
        assert job["entreprise"] == "Acme"
