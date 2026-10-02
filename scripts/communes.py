"""Construit data/communes.json : chaque commune, ses codes postaux et sa ou ses circonscriptions.

À relancer seulement si le découpage change (nouvelles élections, fusions de communes).
Sources (data.gouv.fr) :
  - Législatives 2024, 1er tour, résultats par circonscription et par bureau de vote (ministère de l'Intérieur).
    Le fichier par bureau n'indique pas la circonscription : on la retrouve grâce aux candidats,
    propres à chaque circonscription.
  - Base officielle des codes postaux (La Poste).

    python scripts/communes.py
"""
import csv
import json
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
BASE = "https://static.data.gouv.fr/resources/elections-legislatives-des-30-juin-et-7-juillet-2024-resultats-definitifs-du-1er-tour"
SOURCES = {
    "circos2024.csv": f"{BASE}/20240710-171413/resultats-definitifs-par-circonscriptions-legislatives.csv",
    "bureaux2024.csv": f"{BASE}/20240710-171445/resultats-definitifs-par-bureau-de-vote.csv",
    "laposte.csv": "https://data.laposte.fr/data-fair/api/v1/datasets/laposte-hexasmal/raw",
}
# Codes du ministère de l'Intérieur → codes de l'Assemblée nationale.
DEP_AN = {"ZX": "977", "ZZ": "099"}
# Arrondissements municipaux (codes La Poste) → commune entière (codes des résultats électoraux).
PLM = {"751": "75056", "693": "69123", "132": "13055"}


def dep_an(code):
    return DEP_AN.get(code, code.zfill(2))


def main():
    CACHE.mkdir(exist_ok=True)
    for name, url in SOURCES.items():
        if not (CACHE / name).exists():
            print(f"Téléchargement {url}")
            urllib.request.urlretrieve(url, CACHE / name)

    cle = lambda r: (r["Code département"], r["Nom candidat 1"], r["Prénom candidat 1"], r["Nom candidat 2"])
    circos, deps = {}, {}
    with open(CACHE / "circos2024.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            dep = dep_an(r["Code département"])
            circos[cle(r)] = int(r["Code circonscription législative"][-2:])
            deps.setdefault(dep, {"nom": r["Libellé département"], "circos": 0})
            deps[dep]["circos"] += 1

    communes = {}
    with open(CACHE / "bureaux2024.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            code = r["Code commune"].zfill(5)  # le fichier perd le zéro initial (1001 pour 01001)
            c = communes.setdefault(code, {"nom": r["Libellé commune"], "dep": dep_an(r["Code département"]), "circos": set()})
            c["circos"].add(circos[cle(r)])

    cps = defaultdict(set)
    with open(CACHE / "laposte.csv", encoding="latin-1") as f:
        next(f)
        for insee, _, cp, *_ in csv.reader(f, delimiter=";"):
            cps[PLM.get(insee[:3], insee)].add(cp)

    rows = [[code, c["nom"], c["dep"], sorted(c["circos"]), sorted(cps.get(code, []))]
            for code, c in sorted(communes.items())]
    (ROOT / "data" / "communes.json").write_text(
        json.dumps({"departements": deps, "communes": rows}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    sans_cp = sum(1 for r in rows if not r[4] and r[2] != "099")
    print(f"{len(rows)} communes, {len(deps)} départements, {sum(d['circos'] for d in deps.values())} circonscriptions, {sans_cp} communes sans code postal")


if __name__ == "__main__":
    main()
