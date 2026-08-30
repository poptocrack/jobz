from scripts.newsletter import job_matches, render_email
from scripts.normalize import make_job


def job(**kwargs):
    defaults = dict(
        source="wttj", ref="r1", titre="Développeur React Senior", entreprise="Acme",
        url="https://x", ville="Paris", contrat="CDI", teletravail="hybride",
        salaire_min=55000, salaire_max=65000, employeur_type="client final",
    )
    defaults.update(kwargs)
    return make_job(**defaults)


class TestMatching:
    def test_mots_cles(self):
        assert job_matches(job(), {"q": "react"})
        assert job_matches(job(), {"q": "réact"})  # insensible aux accents
        assert not job_matches(job(), {"q": "angular"})
        assert job_matches(job(), {"q": "react senior"})  # tous les termes requis
        assert not job_matches(job(), {"q": "react angular"})

    def test_contrats(self):
        assert job_matches(job(), {"contrats": ["CDI", "CDD"]})
        assert not job_matches(job(), {"contrats": ["Stage"]})
        assert job_matches(job(), {"contrats": []})

    def test_employeur(self):
        assert job_matches(job(), {"employeur": "client final"})
        assert not job_matches(job(), {"employeur": "esn"})
        assert job_matches(job(employeur_type=""), {"employeur": "inconnu"})

    def test_salaire_min(self):
        assert job_matches(job(), {"salaire_min": 60})
        assert not job_matches(job(), {"salaire_min": 70})
        assert not job_matches(job(salaire_min=None, salaire_max=None), {"salaire_min": 40})

    def test_criteres_combines(self):
        criteres = {"q": "react", "contrats": ["CDI"], "remote": "hybride", "salaire_min": 50}
        assert job_matches(job(), criteres)
        assert not job_matches(job(teletravail="sur site"), criteres)


class TestRendu:
    def test_sujet_et_contenu(self):
        sujet, html = render_email([job()], {"q": "react"})
        assert "1 nouvelle offre" in sujet
        assert "react" in sujet
        assert "Développeur React Senior" in html
        assert "Acme" in html
        assert "55–65 k€" in html

    def test_tjm_prioritaire(self):
        offre = job(contrat="Freelance", tjm_min=500, tjm_max=600)
        _, html = render_email([offre], {"q": ""})
        assert "500–600 €/j" in html

    def test_plafond_offres(self):
        offres = [job(ref=f"r{i}", titre=f"Poste {i}") for i in range(30)]
        _, html = render_email(offres, {"q": ""})
        assert "+ 10 autres offres" in html
