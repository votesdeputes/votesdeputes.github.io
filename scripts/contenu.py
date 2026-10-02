"""Construit data/contenu.json : les sujets qu'un texte touche d'après son contenu, pas seulement son titre.

Un titre est choisi par les auteurs du texte et peut taire l'essentiel : « lever les contraintes à l'exercice
du métier d'agriculteur » autorise des pesticides interdits. Ce script lit le texte lui-même (projet ou
proposition de loi, textes adoptés) publié en open data par l'Assemblée, et ajoute un sujet quand des termes
précis y figurent. Les termes trouvés sont gardés comme preuve et publiés.

À relancer quand de nouveaux textes sont votés (les documents déjà lus restent en cache) :
    python scripts/contenu.py
"""
import html
import json
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from build import norm, texte_de, cle_texte, charge_themes, themes_de  # noqa: E402

DOSSIERS = "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/dossiers_legislatifs/Dossiers_Legislatifs.json.zip"
DOC = "https://www.assemblee-nationale.fr/dyn/opendata/{}.html"
CACHE = ROOT / "cache"
# Les lois budgétaires parlent de tout : leur contenu ne dit rien de leur sujet.
IGNORES = ["loi de finances", "financement de la securite sociale", "fin de gestion", "approbation des comptes",
           "loi speciale", "resultats de la gestion", "comptes de la securite sociale"]
# Faux positifs relus à la main : le terme apparaît sans que le texte porte sur ce sujet.
EXCLUSIONS = {
    "proposition de loi contre toutes les fraudes aux aides publiques": ["environnement"],  # fraude à MaPrimeRénov'
}
# Termes recherchés dans le contenu, par sujet. « min » : nombre d'occurrences au total pour retenir le sujet.
SIGNAUX = {
    "sante": {"min": 2, "termes": ["phytopharmaceutique", "neonicotinoide", "acetamipride", "pesticide",
                                    "perturbateurs endocriniens", "qualite de l'air", "zones a faibles emissions",
                                    "aide medicale de l'etat"]},
    "environnement": {"min": 3, "termes": ["phytopharmaceutique", "neonicotinoide", "pesticide",
                                            "zones a faibles emissions", "artificialisation", "biodiversite",
                                            "especes protegees", "zones humides", "office francais de la biodiversite",
                                            "prelevements d'eau", "stockage de l'eau", "retenues d'eau",
                                            "evaluation environnementale", "installations classees",
                                            "performance energetique"]},
    "immigration": {"min": 2, "termes": ["titre de sejour", "obligation de quitter le territoire",
                                          "aide medicale de l'etat", "retention administrative", "droit du sol",
                                          "regroupement familial", "situation irreguliere"]},
    "egalite-droits": {"min": 2, "termes": ["reconnaissance faciale", "traitements algorithmiques",
                                             "traitement algorithmique", "reconnaissance biometrique",
                                             "techniques de renseignement", "donnees biometriques"]},
}


def texte_brut(uid):
    f = CACHE / "docs" / f"{uid}.html"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(DOC.format(uid), headers={"User-Agent": "votesdeputes (open data)"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                f.write_bytes(r.read())
        except Exception as e:  # document absent ou pas encore publié
            print(f"   {uid} : {e}")
            f.write_text("")
        time.sleep(0.5)
    t = f.read_text(encoding="utf-8", errors="ignore")
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    return norm(html.unescape(re.sub(r"<[^>]+>", " ", t)))


def documents(dossier):
    refs = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("texteAdopteRef", "texteAssocie") and isinstance(v, str) and re.match(r"(PRJL|PION|TA)ANR5L17", v):
                    refs.append(v)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(dossier.get("actesLegislatifs"))
    return list(dict.fromkeys(refs))


def main():
    zpath = CACHE / "dossiers.zip"
    if not zpath.exists():
        urllib.request.urlretrieve(DOSSIERS, zpath)
    dossiers = []
    with zipfile.ZipFile(zpath) as z:
        for name in z.namelist():
            if "/dossierParlementaire/" in name:
                d = json.load(z.open(name))["dossierParlementaire"]
                titre = d["titreDossier"]["titre"]
                if titre and "DossierLegislatif" in d.get("@xsi:type", ""):
                    cle = re.sub(r"^(proposition|projet) de loi (organique )?", "", norm(titre))
                    dossiers.append((cle, d))

    scrutins = json.loads((ROOT / "site" / "data" / "scrutins.json").read_text(encoding="utf-8"))
    textes = sorted({texte_de(r[3]) for r in scrutins["rows"]})
    themes = charge_themes(avec_contenu=False)  # sujets du seul titre
    resultat = {}
    for texte in textes:
        n = cle_texte(texte)
        if not n.startswith(("projet de loi", "proposition de loi")) or any(i in n for i in IGNORES):
            continue
        # Le titre du dossier diffère souvent un peu de celui du texte (« et juguler » / « et à juguler ») :
        # on retient le dossier dont presque tous les mots figurent dans le titre du texte.
        mots = set(re.findall(r"[a-z0-9']+", n))
        candidats = []
        for cle, d in dossiers:
            m = set(re.findall(r"[a-z0-9']+", cle))
            if len(cle) > 15 and cle in n:
                candidats.append((1.0, len(m), d))
            elif len(m) >= 4:
                score = len(m & mots) / len(m)
                if score >= 0.85:
                    candidats.append((score, len(m), d))
        if not candidats:
            print(f"Sans dossier : {texte[:100]}")
            continue
        d = max(candidats, key=lambda x: (x[0], x[1]))[2]
        contenu = " ".join(texte_brut(uid) for uid in documents(d))
        deja = set(themes_de(texte, themes))
        ajouts = {}
        for theme, s in SIGNAUX.items():
            trouves = {t: contenu.count(t) for t in s["termes"] if contenu.count(t)}
            if theme not in deja and sum(trouves.values()) >= s["min"] and theme not in EXCLUSIONS.get(n, []):
                ajouts[theme] = sorted(trouves, key=trouves.get, reverse=True)
        if ajouts:
            resultat[n] = {"dossier": f"https://www.assemblee-nationale.fr/dyn/17/dossiers/{d['titreDossier']['titreChemin']}",
                           "ajouts": ajouts}
            print(f"{texte[:90]}\n   + " + " ; ".join(f"{k} ({', '.join(v[:3])})" for k, v in ajouts.items()))
    (ROOT / "data" / "contenu.json").write_text(json.dumps(resultat, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(resultat)} textes enrichis")


if __name__ == "__main__":
    main()
