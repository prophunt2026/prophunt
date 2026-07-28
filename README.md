# PropHunter TN — Scraper (organisation par dossier + schéma JSON standard v2.0.0)

## Structure du projet
```
prophunter_scraper/
├── common/
│   ├── schema.py       # schéma JSON standard partagé (new_listing())
│   └── utils.py        # rate limiting, retries, export JSON/CSV, dédoublonnage
├── tayara/
│   └── scraper.py      # scraper Tayara.tn
├── tunisie_annonce/
│   └── scraper.py      # scraper Tunisie-Annonce.com
├── main.py              # lance les deux scrapers + fusion
├── test_parsers.py      # tests hors-réseau sur échantillons HTML
├── requirements.txt
└── data/                 # généré à l'exécution
    ├── tayara/tayara.json / .csv
    ├── tunisie_annonce/tunisie_annonce.json / .csv
    └── annonces_merged.json / .csv
```

## Schéma JSON (`common/schema.py`)
Chaque annonce respecte le standard `tunisia_real_estate_listing_standard` (v2.0.0) : `listing`, `transaction`, `bien`, `localisation`, `equipements`, `description`, `medias`, `contact`, `metadonnees_scraping`, `scoring_ia`, `donnees_brutes`.

**Champs remplis à ce stade** (page de liste uniquement) :
- `listing` : id_source, url_source, date_scraping, date_maj (tunisie-annonce), statut, langue
- `transaction` : type, prix, devise
- `bien` : type, nombre_pieces (Tayara, approx. depuis "S+n")
- `localisation` : gouvernorat/délégation (Tayara, depuis l'URL) ou localite (tunisie-annonce)
- `description` : titre
- `metadonnees_scraping` : source, méthode, statut_scraping, temps_scraping_ms

**Champs encore vides** (nécessitent la fiche détail de chaque annonce — prévu pour le module NLP, R3) : superficie, équipements, contact, médias, description complète, coordonnées GPS. Le champ `scoring_ia` sera rempli plus tard, une fois le modèle de scoring (R4) branché.

## Export
- **JSON** : structure imbriquée complète, fidèle au schéma.
- **CSV** : structure "aplatie" automatiquement (`listing.id_source`, `transaction.prix`, etc.) — les listes vides deviennent des chaînes JSON compactes.

## Gestion des erreurs et limites de requêtes (`common/utils.py`)
- Retries avec backoff exponentiel (2s, 4s, 8s), gestion spécifique des codes 429/403/404.
- `RateLimiter` : délai aléatoire de 1.5 à 3 secondes entre deux requêtes.
- Toutes les erreurs sont loggées dans `logs/scraping.log`.

## Utilisation
```bash
pip install -r requirements.txt
python3 test_parsers.py      # vérifie les parseurs sans réseau
python3 main.py               # lance le scraping réel + export
```

## Prochaines étapes
- Compléter les fiches détail (superficie, équipements, contact) pour chaque annonce → module NLP (R3)
- Ajouter Mubawab, Menzili, Fi-Dari (déjà prévus dans `metadonnees_scraping.source`)
- Brancher `scoring_ia` une fois le modèle de décote prêt (R4)

## Mises à jour (retour du manager)

### 1. Objectif : 1000+ annonces par site
- **Tunisie-Annonce** : simple augmentation de `max_pages` (40 pages × ~30 annonces ≈ 1200). Le site a 4453 annonces "Vente" au total, largement suffisant.
- **Tayara** : le site charge ses annonces en scroll infini côté client — `?page=2` renvoie exactement la même chose que `?page=1`, et même le scroll/bouton simulés (Playwright) plafonnaient à ~100 annonces. En analysant le trafic réseau du site, on a trouvé l'**API JSON interne** qu'il utilise réellement pour charger ses résultats :
  ```
  https://www.tayara.tn/_next/data/<BUILD_ID>/en/listing/c/immobilier.json?category=immobilier&page=N
  ```
  `tayara/scraper.py` appelle directement cette API avec de simples requêtes HTTP (`scrape_api()`) — plus besoin de navigateur simulé du tout. Le `<BUILD_ID>` (identifiant de déploiement Next.js) est récupéré automatiquement depuis le HTML de la page catégorie à chaque exécution, pour ne pas dépendre d'une valeur qui expire. Cette méthode est nettement plus rapide et fiable, et renvoie en prime la description complète, les photos, la localisation précise et le vendeur — dès la page de liste.

### 2. Correctif "superficie null"
- **Tayara** : la description complète de l'annonce est incluse directement dans la réponse de l'API (pas besoin de fiche détail séparée) — la superficie, le nombre de chambres et de salles de bain en sont extraits par expression régulière.
- **Tunisie-Annonce** : la superficie **n'existe que sur la fiche détail de chaque annonce**, jamais sur la page de liste. `enrich_with_details()` visite chaque annonce pour la récupérer. C'est plus lent (≈1 requête HTTP en plus par annonce, avec la même pause de 1.5-3s), donc pour 1000 annonces il faut compter **~25-40 minutes**. Pour tester rapidement d'abord, mets `ENRICH_DETAILS_LIMIT = 20` en haut de `main.py`.