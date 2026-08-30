"""Classification de l'employeur : ESN / cabinet / intérim vs client final.

Trois signaux, du plus fiable au moins fiable :
1. Nom de l'entreprise dans la liste des prestataires connus (ESN, cabinets
   de recrutement, agences d'intérim). Match exact sur nom normalisé.
2. Secteur WTTJ de l'entreprise (appliqué dans la source wttj).
3. Signaux textuels dans le titre/la description ("pour notre client",
   "en régie"...), appliqués dans normalize.make_job.

Valeurs du champ employeur_type : "esn" | "client final" | "" (indéterminé).
"""

from __future__ import annotations

from scripts.normalize import norm_text

# Noms normalisés (norm_text) : ESN et sociétés de conseil IT.
_ESN = {
    "capgemini", "capgemini engineering", "capgemini invent", "sogeti",
    "sopra steria", "sopra", "steria", "cgi", "cgi france", "umanis",
    "atos", "eviden", "accenture", "alten", "akkodis", "akka", "akka technologies",
    "modis", "expleo", "davidson", "davidson consulting", "inetum", "gfi",
    "sword", "sii", "groupe sii", "astek", "aubay", "infotel", "neurones",
    "devoteam", "wavestone", "onepoint", "groupe onepoint", "talan", "mc2i",
    "viveris", "extia", "amiltone", "apside", "ausy", "econocom",
    "groupe open", "open", "keyrus", "micropole", "smile", "alter solutions",
    "klanik", "zenika", "ippon", "ippon technologies", "octo", "octo technology",
    "theodo", "sfeir", "publicis sapient", "netcompany", "computacenter",
    "business decision", "scalian", "segula", "segula technologies",
    "celad", "cat amania", "hardis", "hardis group", "consort group",
    "capfi", "meritis", "margo", "daveo", "positive thinking company",
    "acensi", "amaris", "mantu", "solutec", "dxc", "dxc technology",
    "tata consultancy services", "tcs", "infosys", "wipro", "cognizant",
    "capco", "niji", "mon assistant numerique", "b hive", "b hive engineering",
    "exalt", "ltd", "ltd international",
}

# Cabinets de recrutement et agences d'intérim.
_CABINETS = {
    "adecco", "manpower", "randstad", "randstad digital", "expectra", "hays",
    "michael page", "page personnel", "robert half", "lhh", "lhh recruitment solutions",
    "externatic", "seyos", "silkhom", "mobiskill", "fed it", "urban linker",
    "approach people", "harry hope", "lynx rh", "mistertemp", "aquila rh",
    "spring france", "walters people", "robert walters", "kelly services",
    "synergie", "proman", "crit", "start people", "temporis", "menway",
    "grafton", "opensourcing", "free work", "freelance com", "club freelance",
}

_ALL_PRESTA = _ESN | _CABINETS


def is_esn_name(entreprise: str) -> bool:
    return norm_text(entreprise) in _ALL_PRESTA
