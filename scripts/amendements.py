"""Relie chaque scrutin sur un amendement au texte de cet amendement (open data de l'Assemblée).

Produit cache/amendements_scrutins.json : numéro de scrutin -> exposé sommaire, dispositif, auteur.
Sert à classer les votes par cause (data/causes.json).
    python scripts/amendements.py
"""
import html
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
SEANCE = "PO838901"  # amendements examinés en séance publique (pas en commission)
NUM = re.compile(r"(?:sous-)?amendement(?:s)?(?: de [a-zé ]+)?(?: \(rect\.\))? n[°o]\s*(\d+)", re.I)


def texte(h):
    h = html.unescape(re.sub(r"<[^>]+>", " ", h or ""))
    return " ".join(h.split())


def main():
    index = {}
    with zipfile.ZipFile(CACHE / "amendements.zip") as z:
        for nom in z.namelist():
            if SEANCE not in nom:
                continue
            a = json.load(z.open(nom))["amendement"]
            seance = a.get("seanceDiscussionRef")
            seance = seance if isinstance(seance, str) else None
            num = a["identification"].get("numeroOrdreDepot")
            if not seance or not num:
                continue
            c = (a.get("corps") or {}).get("contenuAuteur") or {}
            sig = a.get("signataires") or {}
            index[(seance, str(int(num)))] = {
                "uid": a["uid"], "texte": a.get("texteLegislatifRef"),
                "auteur": texte(sig.get("libelle")), "expose": texte(c.get("exposeSommaire"))[:1500],
                "dispositif": texte(c.get("dispositif"))[:800], "sort": (a.get("cycleDeVie") or {}).get("sort"),
            }
    print(f"{len(index)} amendements de séance indexés")
    out, total, trouves = {}, 0, 0
    with zipfile.ZipFile(CACHE / "scrutins.zip") as z:
        for nom in z.namelist():
            if not nom.endswith(".json"):
                continue
            s = json.load(z.open(nom))["scrutin"]
            titre = s["objet"]["libelle"] or s["titre"]
            m = NUM.search(titre or "")
            if not m:
                continue
            total += 1
            a = index.get((s["seanceRef"], m.group(1)))
            if a:
                trouves += 1
                out[s["numero"]] = a
    (CACHE / "amendements_scrutins.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"{trouves}/{total} scrutins sur amendement reliés à leur texte")


if __name__ == "__main__":
    main()
