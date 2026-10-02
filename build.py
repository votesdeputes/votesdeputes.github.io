"""Génère le site statique à partir de l'open data de l'Assemblée nationale.

    python build.py            # télécharge les données (ou réutilise cache/) et écrit site/
    python build.py --refresh  # force un nouveau téléchargement

Pour ajouter un département : ajouter son code dans DEPARTEMENTS et un fichier
data/circonscriptions-XX.json (facultatif, sert au choix par arrondissement/commune).
"""
import io
import json
import shutil
import sys
import urllib.request
import zipfile
from datetime import date
from html import escape
from pathlib import Path

SITE_NAME = "Paris à l'Assemblée"
LEGISLATURE = "17"
DEPARTEMENTS = {"75": "Paris"}
NB_DEPUTES = 577

ROOT = Path(__file__).parent
CACHE = ROOT / "cache"
OUT = ROOT / "site"
BASE = f"https://data.assemblee-nationale.fr/static/openData/repository/{LEGISLATURE}"
SOURCES = {
    "amo": f"{BASE}/amo/deputes_senateurs_ministres_legislature/AMO20_dep_sen_min_tous_mandats_et_organes.json.zip",
    "scrutins": f"{BASE}/loi/scrutins/Scrutins.json.zip",
}
# Ordre d'affichage des groupes, de gauche à droite de l'hémicycle.
GROUPES = ["LFI-NFP", "GDR", "ECOS", "SOC", "LIOT", "DEM", "EPR", "HOR", "DR", "UDDPLR", "RN", "NI"]
POS = {"pour": "p", "contre": "c", "abstention": "a", "nonVotant": "n"}


def as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def fetch(refresh):
    CACHE.mkdir(exist_ok=True)
    zips = {}
    for key, url in SOURCES.items():
        path = CACHE / f"{key}.zip"
        if refresh or not path.exists():
            print(f"Téléchargement {url}")
            with urllib.request.urlopen(url, timeout=300) as r:
                path.write_bytes(r.read())
        zips[key] = zipfile.ZipFile(path)
    return zips


def read_json(zf, prefix):
    for name in zf.namelist():
        if name.startswith(prefix) and name.endswith(".json"):
            yield json.load(io.TextIOWrapper(zf.open(name), encoding="utf-8"))


def load_groupes(amo):
    groupes = {}
    for doc in read_json(amo, "json/organe/"):
        o = doc["organe"]
        if o.get("codeType") == "GP" and o.get("legislature") == LEGISLATURE:
            groupes[o["uid"]] = {"abrev": o.get("libelleAbrev") or o["libelle"], "nom": o["libelle"]}
    return groupes


def load_deputes(amo, groupes):
    deputes = []
    for doc in read_json(amo, "json/acteur/"):
        a = doc["acteur"]
        mandats = as_list(a["mandats"]["mandat"])
        siege = next((m for m in mandats if m.get("typeOrgane") == "ASSEMBLEE"
                      and m.get("legislature") == LEGISLATURE and not m.get("dateFin")), None)
        if not siege:
            continue
        lieu = siege["election"]["lieu"]
        if lieu.get("numDepartement") not in DEPARTEMENTS:
            continue
        # Un député peut avoir siégé sur plusieurs périodes (remplacement d'un ministre, retour…).
        periodes = sorted(
            [((m.get("mandature") or {}).get("datePriseFonction") or m["dateDebut"])[:10], (m.get("dateFin") or "9999-12-31")[:10]]
            for m in mandats if m.get("typeOrgane") == "ASSEMBLEE" and m.get("legislature") == LEGISLATURE)
        gp = next((m["organes"]["organeRef"] for m in mandats
                   if m.get("typeOrgane") == "GP" and not m.get("dateFin")), None)
        ident = a["etatCivil"]["ident"]
        dep, circo = lieu["numDepartement"], int(lieu["numCirco"])
        deputes.append({
            "id": a["uid"]["#text"],
            "civ": ident["civ"],
            "nom": f"{ident['prenom']} {ident['nom']}",
            "dep": dep,
            "depNom": DEPARTEMENTS[dep],
            "circo": circo,
            "slug": f"{DEPARTEMENTS[dep].lower()}-{circo:02d}",
            "depuis": ((siege.get("mandature") or {}).get("datePriseFonction") or siege["dateDebut"])[:10],
            "periodes": periodes,
            "groupe": groupes.get(gp, {"abrev": "NI", "nom": "Non inscrit"}),
        })
    return sorted(deputes, key=lambda d: (d["dep"], d["circo"]))


def load_scrutins(scr, groupes):
    scrutins = []
    for doc in read_json(scr, "json/"):
        s = doc["scrutin"]
        votes, gpos = {}, {}
        for g in as_list(s["ventilationVotes"]["organe"]["groupes"]["groupe"]):
            abrev = groupes.get(g["organeRef"], {}).get("abrev", "NI")
            v = g["vote"]
            gpos[abrev] = POS.get(v.get("positionMajoritaire"), "-")
            for key, code in (("pours", "p"), ("contres", "c"), ("abstentions", "a"), ("nonVotants", "n")):
                bloc = (v.get("decompteNominatif") or {}).get(key)
                for votant in as_list(bloc and bloc.get("votant")):
                    votes[votant["acteurRef"]] = (code, abrev)
        titre = " ".join((s["objet"]["libelle"] or s["titre"]).split())
        dec = s["syntheseVote"]["decompte"]
        code = s["typeVote"]["codeTypeVote"]
        scrutins.append({
            "n": int(s["numero"]),
            "date": s["dateScrutin"],
            "cat": "m" if code == "MOC" else ("e" if titre.lower().startswith("l'ensemble") else "x"),
            "titre": titre[0].upper() + titre[1:],
            "adopte": 1 if s["sort"]["code"].startswith("adopt") else 0,
            "dec": [int(dec["pour"]), int(dec["contre"]), int(dec["abstentions"])],
            "solennel": 1 if code == "SPS" else 0,
            "gpos": "".join(gpos.get(g, "-") for g in GROUPES),
            "votes": votes,
        })
    return sorted(scrutins, key=lambda s: s["n"])


def stats_depute(d, scrutins):
    fen = [s for s in scrutins if any(a <= s["date"] <= b for a, b in d["periodes"])]
    exprime = lambda s: s["votes"].get(d["id"], ("x",))[0] in "pca"
    exprimes = [(s, s["votes"][d["id"]]) for s in fen if exprime(s)]
    ens = [s for s in fen if s["cat"] == "e"]
    moc = [s for s in fen if s["cat"] == "m"]
    accord = {}
    for i, g in enumerate(GROUPES):
        comp = [(s, v) for s, v in exprimes if s["gpos"][i] in "pca"]
        if comp:
            accord[g] = round(100 * sum(s["gpos"][i] == v[0] for s, v in comp) / len(comp), 1)
    fideles = [(s, v) for s, v in exprimes if v[1] in GROUPES and s["gpos"][GROUPES.index(v[1])] in "pca"]
    return {
        "total": len(fen),
        "votes": len(exprimes),
        "participation": round(100 * len(exprimes) / len(fen), 1) if fen else 0,
        "moyenne": round(100 * sum(sum(s["dec"]) for s in fen) / len(fen) / NB_DEPUTES, 1) if fen else 0,
        "ensTotal": len(ens),
        "ensVotes": sum(1 for s in ens if exprime(s)),
        "mocTotal": len(moc),
        "mocPour": sum(1 for s in moc if s["votes"].get(d["id"], ("x",))[0] == "p"),
        "groupe": round(100 * sum(s["gpos"][GROUPES.index(v[1])] == v[0] for s, v in fideles) / len(fideles), 1) if fideles else None,
        "accord": accord,
        "premier": fen[0]["date"] if fen else None,
        "dernier": fen[-1]["date"] if fen else None,
    }


def fr_num(x):
    return f"{x:,}".replace(",", " ").replace(".", ",")


def page(title, description, body, depth=0, scripts=()):
    up = "../" * depth
    tags = "".join(f'<script src="{up}assets/{s}" defer></script>' for s in scripts)
    return f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description)}">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(description)}">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=Source+Sans+3:wght@400;600&family=JetBrains+Mono:wght@500&display=swap">
<link rel="stylesheet" href="{up}assets/style.css">
{tags}
</head>
<body>
<div class="wrap">
<nav class="top"><a href="{up}index.html" class="brand">{escape(SITE_NAME)}</a><a href="{up}methode.html">Méthode</a></nav>
{body}
<footer>
<div>Source : open data de l'Assemblée nationale (data.assemblee-nationale.fr), Licence Ouverte. Mise à jour le {date.today().strftime('%d/%m/%Y')}.</div>
<div><a href="{up}methode.html">Méthode et limites</a> · <a href="{up}mentions-legales.html">Mentions légales</a></div>
</footer>
</div>
</body>
</html>
"""


def page_depute(d, st):
    titre_civ = "Députée" if d["civ"] == "Mme" else "Député"
    pct = lambda x: f"{fr_num(x)} %"
    fr_date = lambda s: date.fromisoformat(s).strftime("%d/%m/%Y")
    autres = [f"du {fr_date(a)} au {fr_date(b)}" for a, b in d["periodes"] if b != "9999-12-31"]
    periodes = f" (a aussi siégé {', '.join(autres)})" if autres else ""
    desc = (f"Les votes de {d['nom']}, {titre_civ.lower()} de la {d['circo']}e circonscription de {d['depNom']}, "
            f"à l'Assemblée nationale : votes sur les textes, motions de censure, proximité avec les groupes.")
    body = f"""
<header class="hero">
  <div class="eyebrow">{d['circo']}e circonscription de {escape(d['depNom'])}{' · ' + escape(', '.join(d['zones'])) if d['zones'] else ''}</div>
  <h1>{escape(d['nom'])}</h1>
  <div class="idline"><span class="pill">{escape(d['groupe']['nom'])}</span><span>{titre_civ} depuis le {fr_date(d['depuis'])}{periodes}</span><a href="https://www.assemblee-nationale.fr/dyn/deputes/{d['id']}" target="_blank" rel="noopener">Fiche officielle</a></div>
</header>
<div class="stats">
  <div class="stat"><b>{st['ensVotes']}/{st['ensTotal']}</b><span>votes sur l'ensemble d'un texte auxquels {'elle' if d['civ'] == 'Mme' else 'il'} a participé</span></div>
  <div class="stat"><b>{pct(st['participation'])}</b><span>de participation à tous les scrutins publics (moyenne des députés : {pct(st['moyenne'])})</span></div>
  <div class="stat"><b>{pct(st['groupe']) if st['groupe'] is not None else '–'}</b><span>de ses votes identiques à la position de son groupe</span></div>
</div>
<section>
  <h2>Avec quels groupes vote-t-{'elle' if d['civ'] == 'Mme' else 'il'} ?</h2>
  <p class="sub">Part des scrutins où son vote (pour, contre ou abstention) est le même que la position majoritaire de chaque groupe. Calculé sur les {fr_num(st['votes'])} scrutins auxquels {'elle' if d['civ'] == 'Mme' else 'il'} a participé.</p>
  <div class="bars" id="bars"></div>
</section>
<section>
  <h2>Ses votes, scrutin par scrutin</h2>
  <div class="tabs" role="tablist" id="tabs">
    <button role="tab" data-cat="e" aria-selected="true">Votes sur l'ensemble d'un texte</button>
    <button role="tab" data-cat="m" aria-selected="false">Motions de censure</button>
    <button role="tab" data-cat="r" aria-selected="false">Dernières séances</button>
    <button role="tab" data-cat="all" aria-selected="false">Tous ses votes</button>
  </div>
  <div class="tools">
    <input type="search" id="q" placeholder="Chercher un mot : retraites, logement, budget…" aria-label="Chercher dans les scrutins">
    <span class="count" id="count"></span>
  </div>
  <p class="sub" id="tabnote"></p>
  <ol class="list" id="list"><li class="empty">Chargement des scrutins…</li></ol>
  <button class="more" id="more" hidden>Afficher plus</button>
</section>
<script id="depute" type="application/json">{json.dumps({**d, "stats": st}, ensure_ascii=False)}</script>
"""
    return page(f"{d['nom']} · {d['circo']}e circonscription de {d['depNom']}", desc, body, depth=1, scripts=("depute.js",))


def page_index(deputes, decoupage):
    cards = "".join(
        f'<a class="card" href="{d["slug"]}/index.html"><span class="mono">{d["circo"]}e circ.</span>'
        f'<b>{escape(d["nom"])}</b><span>{escape(d["groupe"]["nom"])}</span></a>' for d in deputes)
    arr = "".join(f'<button data-arr="{a}" aria-pressed="false">{a}{"er" if a == "1" else "e"}</button>' for a in decoupage)
    body = f"""
<header class="hero">
  <div class="eyebrow">Les {len(deputes)} députés de Paris</div>
  <h1>Comment vote votre député ?</h1>
  <p class="lede">Choisissez votre arrondissement pour retrouver votre député et ses votes à l'Assemblée nationale, scrutin par scrutin, d'après les données officielles.</p>
</header>
<section>
  <h2>Votre arrondissement</h2>
  <div class="arr" id="arr">{arr}</div>
  <div id="result" class="result"></div>
  <p class="sub">Un doute sur votre circonscription ? Cherchez votre adresse sur <a href="https://www.assemblee-nationale.fr/dyn/vos-deputes" target="_blank" rel="noopener">le site de l'Assemblée nationale</a>.</p>
</section>
<section>
  <h2>Tous les députés de Paris</h2>
  <div class="cards">{cards}</div>
</section>
<script id="data" type="application/json">{json.dumps({"deputes": [{k: d[k] for k in ("nom", "circo", "slug", "groupe")} for d in deputes], "decoupage": decoupage}, ensure_ascii=False)}</script>
"""
    return page(f"{SITE_NAME} · Comment vote votre député ?",
                "Retrouvez les votes des 18 députés de Paris à l'Assemblée nationale, par arrondissement, d'après l'open data officiel.",
                body, scripts=("index.js",))


def main():
    zips = fetch("--refresh" in sys.argv)
    groupes = load_groupes(zips["amo"])
    deputes = load_deputes(zips["amo"], groupes)
    scrutins = load_scrutins(zips["scrutins"], groupes)
    print(f"{len(deputes)} députés, {len(scrutins)} scrutins")

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "static", OUT)
    (OUT / "data").mkdir(exist_ok=True)

    # Les scrutins utiles : ceux où au moins un député suivi a voté, plus les textes,
    # les motions de censure et les trois derniers jours de séance (pour afficher les absences).
    ids = {d["id"] for d in deputes}
    recent = sorted({s["date"] for s in scrutins})[-3:]
    utiles = [s for s in scrutins if s["cat"] != "x" or s["date"] in recent or ids & s["votes"].keys()]
    (OUT / "data" / "scrutins.json").write_text(json.dumps({
        "groupes": GROUPES,
        "derniersJours": recent,
        "rows": [[s["n"], s["date"], s["cat"], s["titre"], s["adopte"], s["dec"], s["solennel"], s["gpos"]] for s in utiles],
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    decoupages = {}
    for dep in DEPARTEMENTS:
        f = ROOT / "data" / f"circonscriptions-{dep}.json"
        if f.exists():
            decoupages[dep] = json.loads(f.read_text(encoding="utf-8"))["arrondissements"]

    for d in deputes:
        st = stats_depute(d, scrutins)
        votes = {s["n"]: s["votes"][d["id"]][0] for s in utiles if d["id"] in s["votes"]}
        (OUT / "data" / f"{d['slug']}.json").write_text(json.dumps(votes, separators=(",", ":")), encoding="utf-8")
        zones = [f"{a}{'er' if a == '1' else 'e'} arr." + ("" if z["zone"] == "Tout l'arrondissement" else " (partie)")
                 for a, zs in decoupages.get(d["dep"], {}).items() for z in zs if z["circo"] == d["circo"]]
        d["zones"] = zones
        (OUT / d["slug"]).mkdir()
        (OUT / d["slug"] / "index.html").write_text(page_depute(d, st), encoding="utf-8")

    (OUT / "index.html").write_text(page_index(deputes, decoupages.get("75", {})), encoding="utf-8")
    for name, title in (("methode", "Méthode et limites"), ("mentions-legales", "Mentions légales")):
        body = (ROOT / "content" / f"{name}.html").read_text(encoding="utf-8")
        (OUT / f"{name}.html").write_text(page(f"{title} · {SITE_NAME}", title, body), encoding="utf-8")
    print(f"Site généré dans {OUT}")


if __name__ == "__main__":
    main()
