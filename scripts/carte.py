"""Construit data/carte.json : contours simplifiés des circonscriptions, pour la carte de l'accueil.

À relancer seulement si le découpage change.
Source : « Contours géographiques des circonscriptions législatives » (data.gouv.fr, 2024, Licence Ouverte),
agrégés à partir des bureaux de vote. Les contours sont simplifiés (Douglas-Peucker) puis arrondis
pour rester légers sur mobile.

    python scripts/carte.py
"""
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ("https://static.data.gouv.fr/resources/contours-geographiques-des-circonscriptions-legislatives/"
          "20240613-191520/circonscriptions-legislatives-p10.geojson")
CACHE = ROOT / "cache" / "circos-p10.geojson"
# Codes du fichier → codes de l'Assemblée nationale.
DEP_AN = {"ZA": "971", "ZB": "972", "ZC": "973", "ZD": "974", "ZS": "975", "ZM": "976"}
# Tolérance en degrés, proportionnelle à la taille de la circonscription : environ 30 m à Paris,
# jusqu'à 400 m pour les grandes circonscriptions rurales.
TOLERANCE_MIN, TOLERANCE_MAX, TOLERANCE_PART = 0.0003, 0.004, 0.012
DECIMALES = 4


def simplifie(points, tol):
    """Douglas-Peucker itératif."""
    if len(points) < 4:
        return points
    garde = [False] * len(points)
    garde[0] = garde[-1] = True
    pile = [(0, len(points) - 1)]
    while pile:
        a, b = pile.pop()
        (x1, y1), (x2, y2) = points[a], points[b]
        dx, dy = x2 - x1, y2 - y1
        norme = (dx * dx + dy * dy) ** 0.5 or 1e-12
        loin, idx = 0, None
        for i in range(a + 1, b):
            x, y = points[i]
            d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norme
            if d > loin:
                loin, idx = d, i
        if idx is not None and loin > tol:
            garde[idx] = True
            pile += [(a, idx), (idx, b)]
    return [p for p, k in zip(points, garde) if k]


def anneau(ring, tol):
    # Un contour est fermé (premier point = dernier) : on le coupe au point le plus éloigné du départ.
    x0, y0 = ring[0]
    loin = max(range(len(ring)), key=lambda i: (ring[i][0] - x0) ** 2 + (ring[i][1] - y0) ** 2)
    pts = simplifie(ring[:loin + 1], tol) + simplifie(ring[loin:], tol)[1:]
    pts = [[round(x, DECIMALES), round(y, DECIMALES)] for x, y in pts]
    pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
    return pts if len(pts) >= 4 else None


def main():
    if not CACHE.exists():
        CACHE.parent.mkdir(exist_ok=True)
        print(f"Téléchargement {SOURCE}")
        urllib.request.urlretrieve(SOURCE, CACHE)
    features, avant, apres = [], 0, 0
    for f in json.loads(CACHE.read_text(encoding="utf-8"))["features"]:
        p, g = f["properties"], f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        xs = [x for poly in polys for x, _ in poly[0]]
        ys = [y for poly in polys for _, y in poly[0]]
        taille = ((max(xs) - min(xs)) * (max(ys) - min(ys))) ** 0.5
        tol = min(TOLERANCE_MAX, max(TOLERANCE_MIN, taille * TOLERANCE_PART))
        out = []
        for poly in polys:
            rings = [anneau(r, tol) for r in poly]
            if rings[0]:
                out.append([r for r in rings if r])
        avant += sum(len(r) for poly in polys for r in poly)
        apres += sum(len(r) for poly in out for r in poly)
        dep = DEP_AN.get(p["codeDepartement"], p["codeDepartement"])
        features.append({"type": "Feature", "properties": {"dep": dep, "circo": int(p["codeCirconscription"][-2:])},
                         "geometry": {"type": "MultiPolygon", "coordinates": out}})
    out = ROOT / "data" / "carte.json"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    print(f"{len(features)} circonscriptions, {avant} → {apres} points, {out.stat().st_size // 1024} Ko")


if __name__ == "__main__":
    main()
