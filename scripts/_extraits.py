"""Outil de travail : extrait l'exposé des motifs des textes les plus votés (pour rédiger data/resumes.json)."""
import json, re, sys, zipfile, collections, html
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from build import norm, texte_de, cle_texte
import contenu as C

def dossiers():
    out = []
    with zipfile.ZipFile(ROOT / "cache" / "dossiers.zip") as z:
        for name in z.namelist():
            if "/dossierParlementaire/" in name:
                d = json.load(z.open(name))["dossierParlementaire"]
                t = d["titreDossier"]["titre"]
                if t and "DossierLegislatif" in d.get("@xsi:type", ""):
                    out.append((re.sub(r"^(proposition|projet) de loi (organique )?", "", norm(t)), d))
    return out

def trouve(n, ds):
    mots = set(re.findall(r"[a-z0-9']+", n)); cands = []
    for cle, d in ds:
        m = set(re.findall(r"[a-z0-9']+", cle))
        if len(cle) > 15 and cle in n: cands.append((1.0, len(m), d))
        elif len(m) >= 4 and len(m & mots) / len(m) >= 0.85: cands.append((len(m & mots) / len(m), len(m), d))
    return max(cands, key=lambda x: (x[0], x[1]))[2] if cands else None

def brut(uid):
    f = ROOT / "cache" / "docs" / f"{uid}.html"
    if not f.exists(): C.texte_brut(uid)
    t = f.read_text(encoding="utf-8", errors="ignore")
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", t)).split())

if __name__ == "__main__":
    a, b, taille = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    s = json.loads((ROOT / "site" / "data" / "scrutins.json").read_text(encoding="utf-8"))
    c = collections.Counter(cle_texte(r[3]) for r in s["rows"])
    ds = dossiers()
    tops = [(k, v) for k, v in c.most_common() if k.startswith(("projet de loi", "proposition de loi"))][a:b]
    for i, (k, v) in enumerate(tops, a):
        d = trouve(k, ds)
        print(f"\n===== [{i}] {v} scrutins | {k}")
        if not d: print("   (pas de dossier)"); continue
        uids = C.documents(d)
        print("   dossier:", d["titreDossier"]["titreChemin"], "| docs:", uids[:4])
        if not uids: continue
        t = brut(uids[0])
        j = t.upper().find("EXPOSÉ DES MOTIFS")
        print("   ", t[max(j, 0):max(j, 0) + taille])
