"""Vérifie le classement par thèmes sur les textes actuels : python scripts/themes_test.py"""
import json, re, sys, unicodedata, collections
sys.path.insert(0, ".")
from build import themes_de, charge_themes
themes = charge_themes()
lignes = [l.rstrip("\n").split("\t") for l in open("cache/textes.txt", encoding="utf-8")]
compte = collections.Counter(); sans = []
for _, n, titre in lignes:
    ids = themes_de(titre, themes)
    for i in ids: compte[i] += int(n)
    if not ids: sans.append((int(n), titre))
    elif "-v" in sys.argv: print(",".join(ids), "|", titre[:110])
print(compte.most_common())
print(f"{len(sans)} textes sans thème :")
for n, t in sorted(sans, reverse=True): print(" ", n, t[:140])
