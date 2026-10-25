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
import re
import shutil
import sys
import unicodedata
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path

SITE_NAME = "Votes des députés"
LEGISLATURE = "17"
NB_DEPUTES = 577
# Ajouté aux adresses des scripts, styles et données : chaque publication force les navigateurs à recharger.
VERSION = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")

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


TEXTE = re.compile(r"((?:projet|proposition) de (?:loi|résolution)\b.*)", re.I)


def norm(s):
    s = unicodedata.normalize("NFD", s.replace("’", "'")).encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def texte_de(titre):
    """Le texte de loi visé par un scrutin (« l'amendement n° 12 … du projet de loi X » → « projet de loi X »)."""
    m = TEXTE.search(titre.replace("’", "'"))
    return m.group(1) if m else titre


def cle_texte(titre):
    """Clé d'un texte de loi, sans les mentions de lecture : sert à relier un scrutin à data/contenu.json."""
    n = norm(texte_de(titre))
    return re.sub(r"\s*\((premiere|deuxieme|nouvelle|seconde|lecture|texte|cmp|commission)[^)]*\)", "", n).strip(" .)")


def charge_themes(avec_contenu=True):
    themes = json.loads((ROOT / "data" / "themes.json").read_text(encoding="utf-8"))["themes"]
    contenu = ROOT / "data" / "contenu.json"
    ajouts = json.loads(contenu.read_text(encoding="utf-8")) if avec_contenu and contenu.exists() else {}
    for th in themes:
        th["contenu"] = {cle for cle, v in ajouts.items() if th["id"] in v["ajouts"]}
        th["re"] = re.compile("|".join(r"(?<![a-z])" + re.escape(norm(m)) for m in th["mots"]))
        th["sauf_n"] = [norm(s) for s in th.get("sauf", [])]
    return themes


def themes_de(titre, themes):
    base = norm(texte_de(titre))
    ids = []
    for th in themes:
        s = base
        for sauf in th["sauf_n"]:
            s = s.replace(sauf, " ")
        if th["re"].search(s) or cle_texte(titre) in th["contenu"]:
            ids.append(th["id"])
    return ids


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


def load_scrutins(scr, groupes, themes):
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
            "themes": themes_de(titre, themes),
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
    tags = "".join(f'<link rel="stylesheet" href="{up}assets/{s}?v={VERSION}">' for s in styles)
    tags += "".join(f'<script src="{up}assets/{s}?v={VERSION}" defer></script>' for s in scripts)
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
<link rel="stylesheet" href="{up}assets/fonts.css?v={VERSION}">
<link rel="stylesheet" href="{up}assets/style.css?v={VERSION}">
{tags}
</head>
<body data-root="{up}" data-v="{VERSION}">
<div class="wrap">
<nav class="top"><a href="{up}index.html" class="brand">{escape(SITE_NAME)}</a><span class="nav-liens"><a href="{up}causes/index.html">Les causes</a><a href="{up}methode.html">Méthode</a></span></nav>
{body}
<footer>
<div>Source : open data de l'Assemblée nationale (data.assemblee-nationale.fr), Licence Ouverte. Mise à jour le {date.today().strftime('%d/%m/%Y')}.</div>
<div><a href="{up}methode.html">Méthode et limites</a> · <a href="{up}mentions-legales.html">Mentions légales</a></div>
</footer>
</div>
</body>
</html>
"""


def page_depute(d, st, zones, causes=()):
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
{section_causes_depute(st, causes, il)}
<section>
  <h2>Avec quels groupes vote-t-{il} ?</h2>
  <p class="sub">Part des scrutins où son vote (pour, contre ou abstention) est le même que la position majoritaire de chaque groupe. Calculé sur les {fr_num(st['votes'])} scrutins auxquels {il} a participé.</p>
  <div class="bars" id="bars"></div>
</section>
<section>
  <h2>Ses votes par sujet</h2>
  <p class="sub">Ses positions sur l'ensemble des textes de chaque sujet (vote final). Touchez un sujet pour voir le détail de ses votes, amendements compris.</p>
  <p class="sub"><strong>« Contre » veut dire contre le texte, pas contre le sujet.</strong> Un texte qui réautorise un pesticide est classé en « Santé » et en « Environnement » : voter contre ce texte compte comme un vote « contre » dans ces deux sujets. Regardez le détail pour savoir ce que chaque texte change.</p>
  <div class="sujets" id="sujets"><p class="sub">Chargement…</p></div>
</section>
<section id="registre">
  <h2>Ses votes, scrutin par scrutin</h2>
  <div class="tabs" role="tablist" id="tabs">
    <button role="tab" data-cat="e" aria-selected="true">Votes sur l'ensemble d'un texte</button>
    <button role="tab" data-cat="m" aria-selected="false">Motions de censure</button>
    <button role="tab" data-cat="r" aria-selected="false">Dernières séances</button>
    <button role="tab" data-cat="all" aria-selected="false">Tous ses votes</button>
  </div>
  <div class="tools">
    <select id="theme" aria-label="Filtrer par sujet"><option value="">Tous les sujets</option></select>
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
<a class="encart-causes" href="causes/index.html">
  <span class="eyebrow">Les causes</span>
  <b>Comment votent les groupes sur les énergies fossiles, les impôts des plus riches, la santé ?</b>
  <span>Chaque vote classé selon qu'il fait avancer ou reculer la cause →</span>
</a>
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


# ---------------------------------------------------------------- Causes
# Chaque vote classé dans data/causes/<id>-*.tsv dit si adopter le texte fait avancer (+) ou reculer (-) la cause.

def charge_causes():
    conf = json.loads((ROOT / "data" / "causes.json").read_text(encoding="utf-8"))["causes"]
    for c in conf:
        c["votes"] = {}
        for f in sorted((ROOT / "data" / "causes").glob(f"{c['id']}-*.tsv")):
            for ligne in f.read_text(encoding="utf-8").splitlines():
                if ligne.strip() and not ligne.startswith("#"):
                    n, sens, raison = ligne.split("\t", 2)
                    c["votes"][int(n)] = (1 if sens.strip() == "+" else -1, raison.strip())
    return conf


def sens_cause(code, sens):
    """Vote d'un député (p, c, a) traduit en position sur la cause : « p » pour, « c » contre, « a » abstention."""
    if code == "a":
        return "a"
    if code not in ("p", "c"):
        return None
    return "p" if (code == "p") == (sens > 0) else "c"


def calc_causes(causes, scrutins):
    par_n = {s["n"]: s for s in scrutins}
    for c in causes:
        groupes = {g: {"p": 0, "c": 0, "a": 0} for g in GROUPES}
        lignes = []
        for n, (sens, raison) in sorted(c["votes"].items(), key=lambda x: -x[0]):
            s = par_n.get(n)
            if not s:
                continue
            for code, abrev in s["votes"].values():
                pos = sens_cause(code, sens)
                if pos and abrev in groupes:
                    groupes[abrev][pos] += 1
            gpos = "".join((sens_cause(p, sens) or "-") if p in ("p", "c", "a") else "-" for p in s["gpos"])
            lignes.append({"n": n, "date": s["date"], "raison": raison, "titre": s["titre"], "sens": sens,
                           "adopte": s["adopte"], "gpos": gpos, "final": s["cat"] == "e"})
        c["groupes"] = groupes
        c["lignes"] = lignes
    return causes


def causes_depute(d, causes, par_n):
    """Positions d'un député sur chaque cause : pour, contre, abstention, absent (votes pendant son mandat)."""
    out = {}
    for c in causes:
        r = {"p": 0, "c": 0, "a": 0, "x": 0}
        for n, (sens, _) in c["votes"].items():
            s = par_n.get(n)
            if not s or not any(a <= s["date"] <= b for a, b in d["periodes"]):
                continue
            v = s["votes"].get(d["id"])
            pos = sens_cause(v[0], sens) if v else None
            r[pos or "x"] += 1
        out[c["id"]] = r
    return out


def barre_cause(r, sigle=None, couleur=None):
    """Une barre empilée pour / abstention / contre, en pourcentage des votes exprimés."""
    total = r["p"] + r["c"] + r["a"]
    if not total:
        return ""
    p, a, c = (round(100 * r[k] / total) for k in ("p", "a", "c"))
    lab = f'<span class="cb-lab"><i style="background:{escape(couleur)}"></i>{escape(sigle)}</span>' if sigle else ""
    tp = f"{p} %" if p >= 9 else ""
    tc = f"{c} %" if c >= 9 else ""
    return (f'<div class="cb">{lab}<div class="cb-barre" role="img" aria-label="{p} % pour, {a} % abstention, {c} % contre">'
            f'<i class="cb-p" style="width:{p}%">{tp}</i><i class="cb-a" style="width:{a}%"></i>'
            f'<i class="cb-c" style="width:{c}%">{tc}</i></div></div>')


def legende_cause(c):
    return (f'<div class="cb-legende"><span><i class="cb-p"></i>{escape(c["pour"])}</span>'
            f'<span><i class="cb-a"></i>Abstention</span><span><i class="cb-c"></i>{escape(c["contre"])}</span></div>')


def barres_groupes(c, infos):
    part = lambda g: c["groupes"][g]["p"] / max(1, sum(c["groupes"][g].values()))
    return "".join(barre_cause(c["groupes"][g], infos[g]["sigle"], infos[g]["couleur"])
                   for g in sorted(GROUPES, key=lambda g: -part(g)) if sum(c["groupes"][g].values()))


def page_cause(c, infos):
    lignes = []
    for x in c["lignes"]:
        chips = "".join(f'<span class="chip cv-{p}">{escape(infos[g]["sigle"])}</span>'
                        for g, p in zip(GROUPES, x["gpos"]) if p != "-")
        avance = x["sens"] > 0
        lignes.append(
            f'<li class="row cause-row"><span class="chip vote cv-{"p" if avance else "c"}">{"Avance" if avance else "Recul"}</span>'
            f'<div class="t"><b>{escape(x["raison"])}</b><small>{escape(x["titre"])}</small></div>'
            f'<div class="meta"><span>{fr_date(x["date"])}</span><span class="res-{x["adopte"]}">{"Adopté" if x["adopte"] else "Rejeté"}</span>'
            f'<a href="https://www.assemblee-nationale.fr/dyn/17/scrutins/{x["n"]}" target="_blank" rel="noopener">Scrutin n° {x["n"]}</a></div>'
            f'<div class="gp cause-gp">{chips}</div></li>')
    body = f"""
<header class="hero">
  <div class="eyebrow"><a href="../index.html">Les causes</a></div>
  <h1>{escape(c['titre'])}</h1>
  <p class="lede">{escape(c['question'])}</p>
</header>
<section>
  <p class="sub">{escape(c['intro'])}</p>
  {legende_cause(c)}
  <div class="cbs">{barres_groupes(c, infos)}</div>
  <p class="sub">En % des votes exprimés de chaque groupe, sur les {len(c['lignes'])} scrutins classés pour cette cause (amendements et textes de loi).</p>
</section>
<section>
  <h2>Les votes pris en compte</h2>
  <p class="sub">« Avance » : adopter ce texte fait avancer la cause. « Recul » : l'adopter la fait reculer. Sous chaque vote, les groupes en vert ont voté majoritairement dans le sens de la cause, ceux en rouge contre.</p>
  <ol class="list">{''.join(lignes)}</ol>
</section>
"""
    return page(f"{c['titre']} · {SITE_NAME}", c["question"], body, depth=2)


def page_causes(causes, infos):
    cartes = "".join(
        f'<a class="cause-carte" href="{c["id"]}/index.html"><h2>{escape(c["titre"])}</h2><p class="sub">{escape(c["question"])}</p>'
        f'{legende_cause(c)}<div class="cbs">{barres_groupes(c, infos)}</div><span class="lien-suite">Voir les {len(c["lignes"])} votes →</span></a>'
        for c in causes)
    body = f"""
<header class="hero">
  <div class="eyebrow">Les causes</div>
  <h1>Comment votent les groupes sur ce qui compte ?</h1>
  <p class="lede">Pour chaque cause, chaque vote est classé selon qu'il la fait avancer ou reculer. Les barres montrent comment chaque groupe a voté.</p>
</header>
<p class="sub">Ce site assume ses choix : il considère que sortir des énergies fossiles, faire contribuer les plus riches ou protéger la santé sont des objectifs souhaitables. Chaque classement est justifié, vote par vote, avec un lien vers le scrutin officiel. <a href="../methode.html">Méthode</a>.</p>
<div class="causes-liste">{cartes}</div>
"""
    return page(f"Les causes · {SITE_NAME}", "Comment votent les groupes de l'Assemblée sur les grandes causes.", body, depth=1)


def section_causes_depute(st, causes, il):
    lignes = "".join(
        f'<a class="cause-dep" href="../../causes/{c["id"]}/index.html"><span class="cd-titre">{escape(c["titre"])}</span>'
        f'{barre_cause(st["causes"][c["id"]])}<span class="cd-det mono">{st["causes"][c["id"]]["p"]} pour · '
        f'{st["causes"][c["id"]]["c"]} contre · {st["causes"][c["id"]]["a"]} abst. · {st["causes"][c["id"]]["x"]} absent</span></a>'
        for c in causes if sum(st["causes"][c["id"]].values()))
    if not lignes:
        return ""
    return f"""<section>
  <h2>Ses votes sur les grandes causes</h2>
  <p class="sub">Pour chaque cause, ses votes classés selon qu'ils la font avancer (vert) ou reculer (rouge). Touchez une cause pour voir le détail.</p>
  <div class="causes-dep">{lignes}</div>
</section>"""


def main():
    zips = fetch("--refresh" in sys.argv)
    groupes, partis = load_organes(zips["amo"])
    deputes = load_deputes(zips["amo"], groupes, partis)
    themes = charge_themes()
    scrutins = load_scrutins(zips["scrutins"], groupes, themes)
    sans = {texte_de(s["titre"])[:120] for s in scrutins if not s["themes"]}
    print(f"{sum(1 for s in scrutins if s['themes'])}/{len(scrutins)} scrutins classés ; textes sans thème : {len(sans)}")
    for x in sorted(sans):
        print("   ", x)
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

    # Résumés « Ce que fait ce texte », affichés sous les votes sur l'ensemble d'un texte.
    resumes = json.loads((ROOT / "data" / "resumes.json").read_text(encoding="utf-8"))["resumes"]
    for s in scrutins:
        cle = cle_texte(s["titre"])
        s["resume"] = next((i for i, r in enumerate(resumes) if r["cle"] in cle), -1) if s["cat"] == "e" else -1
    print(f"{sum(1 for s in scrutins if s['resume'] >= 0)} votes finaux avec résumé sur {sum(1 for s in scrutins if s['cat'] == 'e')}")
    recent = sorted({s["date"] for s in scrutins})[-3:]
    ids = [th["id"] for th in themes]
    (OUT / "data" / "scrutins.json").write_text(json.dumps({
        "groupes": GROUPES,
        "infos": {g["abrev"]: {"sigle": g["sigle"], "couleur": g["couleur"]} for g in groupes.values() if g["abrev"] in GROUPES},
        "derniersJours": recent,
        "themes": [{"id": th["id"], "nom": th["nom"]} for th in themes],
        "resumes": [[r["resume"], r.get("source", "")] for r in resumes],
        "rows": [[s["n"], s["date"], s["cat"], s["titre"], s["adopte"], s["dec"], s["solennel"], s["gpos"],
                  [ids.index(i) for i in s["themes"]], s["resume"]] for s in scrutins],
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    causes = calc_causes(charge_causes(), scrutins)
    infos = {g["abrev"]: {"sigle": g["sigle"], "couleur": g["couleur"]} for g in groupes.values() if g["abrev"] in GROUPES}
    par_n = {s["n"]: s for s in scrutins}
    (OUT / "causes").mkdir()
    (OUT / "causes" / "index.html").write_text(page_causes(causes, infos), encoding="utf-8")
    for c in causes:
        (OUT / "causes" / c["id"]).mkdir()
        (OUT / "causes" / c["id"] / "index.html").write_text(page_cause(c, infos), encoding="utf-8")
        print(f"cause {c['id']} : {len(c['lignes'])} votes")

    for d in deputes:
        st = stats_depute(d, scrutins)
        st["causes"] = causes_depute(d, causes, par_n)
        votes = "".join(f"{s['n']}{s['votes'][d['id']][0]}" for s in scrutins if d["id"] in s["votes"])
        (OUT / "data" / "votes" / f"{d['id']}.txt").write_text(votes, encoding="utf-8")
        zones = [f"{a}{'er' if a == '1' else 'e'} arr." + ("" if z["zone"] == "Tout l'arrondissement" else " (partie)")
                 for a, zs in decoupages.get(d["dep"], {}).items() for z in zs if z["circo"] == d["circo"]]
        (OUT / d["url"]).mkdir(parents=True)
        (OUT / d["url"] / "index.html").write_text(page_depute(d, st, zones, causes), encoding="utf-8")

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
