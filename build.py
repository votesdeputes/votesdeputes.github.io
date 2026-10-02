"""Génère le site statique à partir de l'open data de l'Assemblée nationale.

    python build.py            # télécharge les données (ou réutilise cache/) et écrit site/
    python build.py --refresh  # force un nouveau téléchargement

Arborescence produite :
    site/index.html                  recherche par commune ou code postal, liste des départements
    site/<dep>/index.html            députés d'un département (Paris : choix par arrondissement)
    site/<dep>/<circo>/index.html    fiche d'un député
    site/data/                       scrutins, votes par député, communes

data/communes.json est produit par scripts/communes.py (à relancer seulement si le découpage change).
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

SITE_NAME = "Votes des députés"
LEGISLATURE = "17"
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
# Sigles d'usage quand celui de l'open data diffère.
SIGLES = {"ECOS": "EcoS", "DEM": "Dem", "UDDPLR": "UDR", "NI": "NI"}
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


def load_organes(amo):
    groupes, partis = {}, {}
    for doc in read_json(amo, "json/organe/"):
        o = doc["organe"]
        if o.get("codeType") == "GP" and o.get("legislature") == LEGISLATURE:
            abrev = o.get("libelleAbrev") or o["libelle"]
            groupes[o["uid"]] = {"abrev": abrev, "sigle": SIGLES.get(abrev, abrev), "nom": o["libelle"],
                                 "couleur": o.get("couleurAssociee") or "#8D949A"}
        elif o.get("codeType") == "PARPOL":
            partis[o["uid"]] = o["libelle"]
    return groupes, partis


def load_deputes(amo, groupes, partis):
    ni = next((g for g in groupes.values() if g["abrev"] == "NI"), {"abrev": "NI", "sigle": "NI", "nom": "Non inscrit", "couleur": "#8D949A"})
    deputes = []
    for doc in read_json(amo, "json/acteur/"):
        a = doc["acteur"]
        mandats = as_list(a["mandats"]["mandat"])
        siege = next((m for m in mandats if m.get("typeOrgane") == "ASSEMBLEE"
                      and m.get("legislature") == LEGISLATURE and not m.get("dateFin")), None)
        if not siege:
            continue
        lieu = siege["election"]["lieu"]
        # Un député peut avoir siégé sur plusieurs périodes (remplacement d'un ministre, retour…).
        periodes = sorted(
            [((m.get("mandature") or {}).get("datePriseFonction") or m["dateDebut"])[:10], (m.get("dateFin") or "9999-12-31")[:10]]
            for m in mandats if m.get("typeOrgane") == "ASSEMBLEE" and m.get("legislature") == LEGISLATURE)
        actifs = lambda t: [m["organes"]["organeRef"] for m in mandats if m.get("typeOrgane") == t and not m.get("dateFin")]
        gp, parti = actifs("GP"), actifs("PARPOL")
        ident = a["etatCivil"]["ident"]
        dep, circo = lieu["numDepartement"], int(lieu["numCirco"])
        deputes.append({
            "id": a["uid"]["#text"],
            "civ": ident["civ"],
            "nom": f"{ident['prenom']} {ident['nom']}",
            "nomFamille": ident["nom"],
            "dep": dep,
            "depNom": lieu["departement"],
            "circo": circo,
            "url": f"{dep.lower()}/{circo:02d}/",
            "depuis": ((siege.get("mandature") or {}).get("datePriseFonction") or siege["dateDebut"])[:10],
            "periodes": periodes,
            "groupe": groupes.get(gp[0], ni) if gp else ni,
            "parti": partis.get(parti[0]) if parti else None,
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
    fideles = [(s, v) for s, v in exprimes if v[1] in GROUPES and v[1] != "NI" and s["gpos"][GROUPES.index(v[1])] in "pca"]
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
    }


def fr_num(x):
    return f"{x:,}".replace(",", " ").replace(".", ",")


def fr_date(s):
    return date.fromisoformat(s).strftime("%d/%m/%Y")


def ordinal(n):
    return f"{n}{'re' if n == 1 else 'e'}"


def ordre_dep(code):
    """Ordre officiel : 01 à 95 (la Corse entre 19 et 21), outre-mer, puis Français de l'étranger."""
    if code == "099":
        return 9999
    return {"2A": 20.1, "2B": 20.2}.get(code) or int(code)


def badge(g):
    return f'<span class="grp"><i style="background:{escape(g["couleur"])}"></i>{escape(g["nom"])}</span>'


def page(title, description, body, depth=0, scripts=(), styles=()):
    up = "../" * depth
    tags = "".join(f'<link rel="stylesheet" href="{up}assets/{s}">' for s in styles)
    tags += "".join(f'<script src="{up}assets/{s}" defer></script>' for s in scripts)
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
<link rel="stylesheet" href="{up}assets/fonts.css">
<link rel="stylesheet" href="{up}assets/style.css">
{tags}
</head>
<body data-root="{up}">
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


def page_depute(d, st, zones):
    elle = d["civ"] == "Mme"
    il = "elle" if elle else "il"
    titre_civ = "Députée" if elle else "Député"
    pct = lambda x: f"{fr_num(x)} %"
    autres = [f"du {fr_date(a)} au {fr_date(b)}" for a, b in d["periodes"] if b != "9999-12-31"]
    periodes = f" (a aussi siégé {', '.join(autres)})" if autres else ""
    parti = f'<span>Parti : {escape(d["parti"])}</span>' if d["parti"] and d["parti"] != "Non rattaché(s)" else ""
    lieu = f"{ordinal(d['circo'])} circonscription · {escape(d['depNom'])}"
    desc = (f"Les votes de {d['nom']}, {titre_civ.lower()} de la {ordinal(d['circo'])} circonscription ({d['depNom']}), "
            f"à l'Assemblée nationale : votes sur les textes, motions de censure, proximité avec les groupes.")
    body = f"""
<header class="hero">
  <div class="eyebrow"><a href="../index.html">{escape(d['depNom'])}</a> · {ordinal(d['circo'])} circonscription{' · ' + escape(', '.join(zones)) if zones else ''}</div>
  <h1>{escape(d['nom'])}</h1>
  <div class="idline">{badge(d['groupe'])}{parti}</div>
  <div class="idline"><span>{titre_civ} depuis le {fr_date(d['depuis'])}{periodes}</span><a href="https://www.assemblee-nationale.fr/dyn/deputes/{d['id']}" target="_blank" rel="noopener">Fiche officielle</a></div>
</header>
<div class="stats">
  <div class="stat"><b>{st['ensVotes']}/{st['ensTotal']}</b><span>votes sur l'ensemble d'un texte auxquels {il} a participé</span></div>
  <div class="stat"><b>{pct(st['participation'])}</b><span>de participation à tous les scrutins publics (moyenne des députés : {pct(st['moyenne'])})</span></div>
  <div class="stat"><b>{pct(st['groupe']) if st['groupe'] is not None else '–'}</b><span>{'de ses votes identiques à la position de son groupe' if st['groupe'] is not None else 'Non inscrit : pas de groupe de référence'}</span></div>
</div>
<section>
  <h2>Avec quels groupes vote-t-{il} ?</h2>
  <p class="sub">Part des scrutins où son vote (pour, contre ou abstention) est le même que la position majoritaire de chaque groupe. Calculé sur les {fr_num(st['votes'])} scrutins auxquels {il} a participé.</p>
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
<script id="depute" type="application/json">{json.dumps({"id": d["id"], "periodes": d["periodes"], "groupe": d["groupe"]["abrev"], "stats": st}, ensure_ascii=False)}</script>
"""
    return page(f"{d['nom']} · {lieu}", desc, body, depth=2, scripts=("depute.js",))


def carte(d, href, extra=""):
    return (f'<a class="card" href="{href}"><span class="mono">{ordinal(d["circo"])} circ.{extra}</span>'
            f'<b>{escape(d["nom"])}</b>{badge(d["groupe"])}</a>')


def page_departement(code, nom, nb_circos, deputes, decoupage):
    par_circo = {d["circo"]: d for d in deputes}
    cartes = "".join(carte(par_circo[c], f"{c:02d}/index.html") if c in par_circo else
                     f'<div class="card vacant"><span class="mono">{ordinal(c)} circ.</span><b>Siège vacant</b><span>En attente d\'une élection partielle</span></div>'
                     for c in range(1, nb_circos + 1))
    arr = ""
    if decoupage:
        boutons = "".join(f'<button data-arr="{a}" aria-pressed="false">{a}{"er" if a == "1" else "e"}</button>' for a in decoupage)
        arr = f"""<section>
  <h2>Votre arrondissement</h2>
  <div class="arr" id="arr">{boutons}</div>
  <div id="result" class="result"></div>
</section>
<script id="data" type="application/json">{json.dumps({"deputes": {d["circo"]: {"nom": d["nom"], "groupe": d["groupe"]} for d in deputes}, "decoupage": decoupage}, ensure_ascii=False)}</script>"""
    pluriel = "s" if nb_circos > 1 else ""
    body = f"""
<header class="hero">
  <div class="eyebrow">{nb_circos} circonscription{pluriel}</div>
  <h1>{escape(nom)}</h1>
  <p class="lede">{'Les députés élus' if nb_circos > 1 else 'Le député élu'} dans ce territoire et leurs votes à l'Assemblée nationale.</p>
</header>
{arr}
<section>
  <h2>Député{pluriel}</h2>
  <div class="cards">{cartes}</div>
</section>
"""
    return page(f"Députés · {nom}", f"Les votes des députés de {nom} à l'Assemblée nationale.", body, depth=1,
                scripts=("departement.js",) if decoupage else ())


def page_index(deputes, departements):
    liste = "".join(f'<a href="{c.lower()}/index.html"><span class="mono">{c}</span>{escape(d["nom"])}</a>'
                    for c, d in sorted(departements.items(), key=lambda x: ordre_dep(x[0])))
    index = {f'{d["dep"]}-{d["circo"]}': [d["nom"], d["groupe"]["sigle"], d["groupe"]["couleur"]] for d in deputes}
    sieges = {}
    for d in deputes:
        sieges.setdefault(d["groupe"]["abrev"], [d["groupe"], 0])[1] += 1
    legende = "".join(f'<li><span class="grp"><i style="background:{escape(g["couleur"])}"></i>{escape(g["nom"])}</span><span class="mono">{n}</span></li>'
                      for g, n in sorted(sieges.values(), key=lambda x: GROUPES.index(x[0]["abrev"]) if x[0]["abrev"] in GROUPES else 99))
    vacants = sum(d["circos"] for d in departements.values()) - len(deputes)
    if vacants:
        legende += f'<li><span class="grp"><i class="vide"></i>Sièges vacants</span><span class="mono">{vacants}</span></li>'
    hors_carte = "".join(f'<a href="{c}/index.html">{escape(departements[c]["nom"])}</a>' for c in ("977", "986", "987", "988", "099") if c in departements)
    body = f"""
<header class="hero">
  <div class="eyebrow">Les {len(deputes)} députés en fonction</div>
  <h1>Comment vote votre député ?</h1>
  <p class="lede">Tapez votre commune ou votre code postal pour retrouver votre député et ses votes à l'Assemblée nationale, scrutin par scrutin, d'après les données officielles.</p>
</header>
<section>
  <label class="search" for="commune"><span class="sr">Commune ou code postal</span>
    <input type="search" id="commune" placeholder="Commune ou code postal : Lille, 33000, Ajaccio…" autocomplete="off">
  </label>
  <div id="resultats" class="result" aria-live="polite"></div>
  <p class="sub">Les Français de l'étranger peuvent taper leur ville de résidence. Pour une adresse précise, utilisez <a href="https://www.assemblee-nationale.fr/dyn/vos-deputes" target="_blank" rel="noopener">la recherche de l'Assemblée nationale</a>.</p>
</section>
<section>
  <h2>La carte des circonscriptions</h2>
  <p class="sub">Chaque circonscription a la couleur du groupe de son député. Touchez-en une pour voir qui la représente.</p>
  <div class="vues" id="vues">
    <button data-vue="metropole" aria-pressed="true">Métropole</button>
    <button data-vue="paris" aria-pressed="false">Paris et petite couronne</button>
    <button data-vue="971" aria-pressed="false">Guadeloupe</button>
    <button data-vue="972" aria-pressed="false">Martinique</button>
    <button data-vue="973" aria-pressed="false">Guyane</button>
    <button data-vue="974" aria-pressed="false">La Réunion</button>
    <button data-vue="976" aria-pressed="false">Mayotte</button>
    <button data-vue="975" aria-pressed="false">Saint-Pierre-et-Miquelon</button>
  </div>
  <div class="carte-grille">
    <div id="carte" class="carte" role="region" aria-label="Carte des circonscriptions"></div>
    <div class="carte-cote">
      <div id="carte-info" class="result"></div>
      <ul class="legende">{legende}</ul>
    </div>
  </div>
  <p class="sub">Hors de la carte : {hors_carte}.</p>
</section>
<section>
  <h2>Par département</h2>
  <div class="deps">{liste}</div>
</section>
<script id="data" type="application/json">{json.dumps({"deputes": index, "departements": {c: d["nom"] for c, d in departements.items()}}, ensure_ascii=False, separators=(",", ":"))}</script>
"""
    return page(f"{SITE_NAME} · Comment vote votre député ?",
                "Retrouvez les votes des 577 députés à l'Assemblée nationale, par commune ou code postal, d'après l'open data officiel.",
                body, scripts=("vendor/leaflet.js", "index.js", "carte.js"), styles=("vendor/leaflet.css",))


def main():
    zips = fetch("--refresh" in sys.argv)
    groupes, partis = load_organes(zips["amo"])
    deputes = load_deputes(zips["amo"], groupes, partis)
    scrutins = load_scrutins(zips["scrutins"], groupes)
    communes = json.loads((ROOT / "data" / "communes.json").read_text(encoding="utf-8"))
    departements = communes["departements"]
    decoupages = {"75": json.loads((ROOT / "data" / "circonscriptions-75.json").read_text(encoding="utf-8"))["arrondissements"]}
    print(f"{len(deputes)} députés, {len(scrutins)} scrutins, {len(departements)} départements")

    # On vide site/ sans le supprimer : sous Windows, un serveur local peut garder le dossier ouvert.
    OUT.mkdir(exist_ok=True)
    for old in OUT.iterdir():
        shutil.rmtree(old) if old.is_dir() else old.unlink()
    shutil.copytree(ROOT / "static", OUT, dirs_exist_ok=True)
    (OUT / "data" / "votes").mkdir(parents=True)
    shutil.copy(ROOT / "data" / "communes.json", OUT / "data" / "communes.json")
    shutil.copy(ROOT / "data" / "carte.json", OUT / "data" / "carte.json")

    recent = sorted({s["date"] for s in scrutins})[-3:]
    (OUT / "data" / "scrutins.json").write_text(json.dumps({
        "groupes": GROUPES,
        "infos": {g["abrev"]: {"sigle": g["sigle"], "couleur": g["couleur"]} for g in groupes.values() if g["abrev"] in GROUPES},
        "derniersJours": recent,
        "rows": [[s["n"], s["date"], s["cat"], s["titre"], s["adopte"], s["dec"], s["solennel"], s["gpos"]] for s in scrutins],
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    for d in deputes:
        st = stats_depute(d, scrutins)
        votes = "".join(f"{s['n']}{s['votes'][d['id']][0]}" for s in scrutins if d["id"] in s["votes"])
        (OUT / "data" / "votes" / f"{d['id']}.txt").write_text(votes, encoding="utf-8")
        zones = [f"{a}{'er' if a == '1' else 'e'} arr." + ("" if z["zone"] == "Tout l'arrondissement" else " (partie)")
                 for a, zs in decoupages.get(d["dep"], {}).items() for z in zs if z["circo"] == d["circo"]]
        (OUT / d["url"]).mkdir(parents=True)
        (OUT / d["url"] / "index.html").write_text(page_depute(d, st, zones), encoding="utf-8")

    for code, dep in departements.items():
        (OUT / code.lower()).mkdir(exist_ok=True)
        html = page_departement(code, dep["nom"], dep["circos"], [d for d in deputes if d["dep"] == code], decoupages.get(code))
        (OUT / code.lower() / "index.html").write_text(html, encoding="utf-8")

    (OUT / "index.html").write_text(page_index(deputes, departements), encoding="utf-8")
    for name, title in (("methode", "Méthode et limites"), ("mentions-legales", "Mentions légales")):
        body = (ROOT / "content" / f"{name}.html").read_text(encoding="utf-8")
        (OUT / f"{name}.html").write_text(page(f"{title} · {SITE_NAME}", title, body), encoding="utf-8")
    (OUT / ".nojekyll").write_text("")
    print(f"Site généré dans {OUT}")


if __name__ == "__main__":
    main()
