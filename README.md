# Paris à l'Assemblée

Site statique qui montre comment votent les 18 députés de Paris, à partir de l'open data de l'Assemblée nationale. Il est régénéré et republié chaque nuit par GitHub Actions.

## Générer le site en local

Python 3.10 ou plus, sans dépendance.

```bash
python build.py            # réutilise les données déjà téléchargées dans cache/
python build.py --refresh  # retélécharge l'open data
python -m http.server 8765 --directory site
```

Puis ouvrir http://localhost:8765.

## Mettre en ligne sur GitHub Pages

1. Créer un dépôt sur GitHub et y pousser ce dossier (branche `main`).
2. Dans le dépôt : **Settings → Pages → Build and deployment → Source : GitHub Actions**.
3. Le workflow `.github/workflows/deploy.yml` se lance à chaque push, chaque nuit à 5h30 UTC, et à la demande depuis l'onglet **Actions**.

Le site est alors en ligne sur `https://<compte>.github.io/<depot>/`. Pour un nom de domaine, voir **Settings → Pages → Custom domain**.

Le site est publié anonymement : les commits utilisent une identité neutre (configurée dans ce dépôt uniquement) et les mentions légales indiquent un éditeur non professionnel anonyme.

## Organisation

| Chemin | Rôle |
| --- | --- |
| `build.py` | Télécharge les données, calcule les statistiques, écrit `site/` |
| `data/circonscriptions-75.json` | Arrondissements et quartiers de chaque circonscription (découpage de 2010) |
| `static/assets/` | Style et scripts des pages |
| `content/` | Pages de texte (méthode, mentions légales) |

## Étendre à d'autres départements

1. Ajouter le département dans `DEPARTEMENTS` dans `build.py`.
2. Ajouter éventuellement un fichier `data/circonscriptions-XX.json` pour le choix par commune.
3. Adapter la page d'accueil (`page_index`), aujourd'hui centrée sur Paris.

## Sources

- Députés et mandats : `AMO20_dep_sen_min_tous_mandats_et_organes.json.zip`
- Scrutins : `Scrutins.json.zip`

Toutes deux sur https://data.assemblee-nationale.fr, sous Licence Ouverte.
