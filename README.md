# Votes des députés

Site statique qui montre comment votent les 577 députés à l'Assemblée nationale, à partir de l'open data officiel. Il est régénéré et republié chaque nuit par GitHub Actions.

## Générer le site en local

Python 3.10 ou plus, sans dépendance.

```bash
python build.py            # réutilise les données déjà téléchargées dans cache/
python build.py --refresh  # retélécharge l'open data
python -m http.server 8765 --directory site
```

Puis ouvrir http://localhost:8765.

## Publication

Le workflow `.github/workflows/deploy.yml` publie le site sur GitHub Pages (Settings → Pages → Source : GitHub Actions) à chaque push, chaque nuit à 5h30 UTC, et à la demande depuis l'onglet **Actions**.

Le site est publié anonymement : les commits utilisent une identité neutre (configurée dans ce dépôt uniquement) et les mentions légales indiquent un éditeur non professionnel anonyme.

## Organisation

| Chemin | Rôle |
| --- | --- |
| `build.py` | Télécharge les données de l'Assemblée, calcule les statistiques, écrit `site/` |
| `scripts/carte.py` | Construit `data/carte.json` (contours simplifiés des circonscriptions). À relancer seulement si le découpage change |
| `scripts/communes.py` | Construit `data/communes.json` (communes, codes postaux, circonscriptions). À relancer seulement si le découpage change |
| `data/themes.json` | Les 15 sujets et leurs mots-clés (classement des scrutins). `python scripts/themes_test.py -v` affiche le classement de chaque texte |
| `data/contenu.json` | Sujets ajoutés d'après le contenu des textes, avec les termes trouvés. Produit par `scripts/contenu.py`, à relancer quand de nouveaux textes sont votés |
| `data/circonscriptions-75.json` | Arrondissements et quartiers de chaque circonscription de Paris (découpage de 2010) |
| `static/assets/` | Style et scripts des pages |
| `content/` | Pages de texte (méthode, mentions légales) |

Pages produites : `index.html` (recherche par commune ou code postal), `<dep>/index.html` (un département), `<dep>/<circo>/index.html` (un député).

## Sources

- Assemblée nationale : `AMO20_dep_sen_min_tous_mandats_et_organes.json.zip` et `Scrutins.json.zip` (data.assemblee-nationale.fr)
- Ministère de l'Intérieur : résultats du 1er tour des législatives 2024 par circonscription et par bureau de vote (data.gouv.fr)
- La Poste : base officielle des codes postaux
- Contours des circonscriptions : « Contours géographiques des circonscriptions législatives » (data.gouv.fr, 2024)
- Polices (SIL Open Font License) et Leaflet (licence BSD) hébergés dans `static/assets/`

Toutes sous Licence Ouverte.
