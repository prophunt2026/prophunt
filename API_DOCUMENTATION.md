# 📖 PropHunter Backend — Documentation Complète de l'Architecture & des APIs

Bienvenue dans la documentation officielle du backend **PropHunter**. Ce document résume l'architecture des 4 microservices, le fonctionnement du pipeline de scraping et de synchronisation automatique, ainsi que le guide complet de test des APIs.

---

## 🏛️ 1. Architecture Globale des 4 Microservices

PropHunter repose sur une architecture orientée microservices conteneurisée via Docker :

```
                        [ Client / Postman / Frontend ]
                                       │
                                       ▼ (Port 3000)
                         ┌───────────────────────────┐
                         │      API GATEWAY (NestJS) │
                         │   - Routage & Reverse Proxy│
                         │   - Sécurité JwtAdminGuard │
                         └─────────────┬─────────────┘
                                       │
       ┌───────────────────────────────┼───────────────────────────────┐
       │                               │                               │
       ▼ (Port 3003)                   ▼ (Port 3001)                   ▼ (Port 3002)
┌───────────────┐              ┌───────────────┐              ┌───────────────┐
│ AUTH SERVICE  │              │  AI SERVICE   │              │ CRUD SERVICE  │
│    (NestJS)   │              │   (FastAPI)   │              │   (NestJS)    │
│               │              │               │              │               │
│ - Inscription │              │ - 6 Scrapers  │              │ - Pagination  │
│ - Connexion   │              │ - Upsert IA   │              │   (10 / page) │
│ - Tokens JWT  │              │ - Auto-Sync   │              │ - Filtrage par│
│               │              │ - Scoring IA  │              │   site/source │
└───────┬───────┘              └───────┬───────┘              └───────┬───────┘
        │                              │                              │
        ▼                              ▼                              ▼
┌──────────────────┐           ┌──────────────────┐           ┌──────────────────┐
│ prophunter_auth  │           │  prophunter_ia   │           │    prophunter    │
│  - users         │           │  - 6 collections │           │  - properties    │
│                  │           │  - scraping_jobs │           │  - sync_metadata │
└──────────────────┘           └──────────────────┘           └──────────────────┘
                                 (MongoDB - Port 27018)
```

---

## 🔄 2. Pipeline de Scraping & Synchronisation Automatique

Lorsqu'un scraping est déclenché (`POST /v1/service-ia/scraping/all` ou `/v1/service-ia/scraping/{site}`) :

```
Déclenchement API (POST) ──▶ Réponse 202 Accepted immédiate (Tâche en arrière-plan)
                                       │
                                       ▼
                       Étape 1 : Scraping & Normalisation
                         (Scrape des liens, détails, téléphones)
                                       │
                                       ▼
                       Étape 2 : Enregistrement dans l'IA
                         (Upsert par listing.id_universel dans prophunter_ia.<site>_properties)
                                       │
                                       ▼
                       Étape 3 : Synchronisation Automatique vers CRUD
                         (Filtre : date_scraping > last_sync_date ➔ Upsert dans prophunter.properties)
                                       │
                                       ▼
                       Étape 4 : Mise à jour des Métadonnées
                         (Enregistrement de la nouvelle last_sync_date dans prophunter.sync_metadata)
                                       │
                                       ▼
                               Statut = COMPLETED
```

### 🛡️ Garanties Techniques :
- **Anti-Doublons** : Index unique MongoDB sparse sur `listing.id_universel` sur l'ensemble des collections.
- **Anti-Concurrence** : Verrou par site (`threading.Lock` + vérification de statut) qui renvoie une erreur `HTTP 409 Conflict` si une tentative de relance a lieu alors qu'un scraper tourne déjà.
- **Indépendance totale** : Chaque site s'exécute dans son propre thread sans bloquer ni attendre les autres sites.

---

## 📡 3. Catalogue des APIs

### 🔑 A. Authentification (Auth Service)

#### 1. Connexion Admin (Obtention du Token)
- **Méthode** : `POST`
- **URL** : `http://localhost:3000/v1/auth/signin`
- **Headers** : `Content-Type: application/json`
- **Body** :
```json
{
  "email": "admin@prophunter.tn",
  "password": "Admin@PropHunter2026!"
}
```
- **Réponse (200 OK)** :
```json
{
  "access_token": "eyJhbGciOi...",
  "refresh_token": "eyJhbGciOi...",
  "user": {
    "id": "...",
    "email": "admin@prophunter.tn",
    "role": "ADMIN"
  }
}
```

---

### 🕷️ B. Scraping & Synchronisation (AI Service — Admin Only)
> ⚠️ **Tous ces endpoints nécessitent le Header** :  
> `Authorization: Bearer <VOTRE_ACCESS_TOKEN_ADMIN>`

#### 1. Lancer le Scraping Global (6 sites en parallèle)
- **Méthode** : `POST`
- **URL** : `http://localhost:3000/v1/service-ia/scraping/all`
- **Réponse (202 Accepted)** :
```json
{
  "message": "Scraping global initié (6 lancés, 0 ignorés).",
  "launched": [
    { "source": "tecnocasa", "job_id": "...", "status": "pending" },
    { "source": "mubawab", "job_id": "...", "status": "pending" },
    { "source": "tayara", "job_id": "...", "status": "pending" },
    { "source": "tunisie_annonce", "job_id": "...", "status": "pending" },
    { "source": "fi_dari", "job_id": "...", "status": "pending" },
    { "source": "home_in_tunisia", "job_id": "...", "status": "pending" }
  ],
  "skipped": []
}
```

#### 2. Lancer le Scraping d'un Site Spécifique
- **Méthode** : `POST`
- **URLs disponibles** :
  - `http://localhost:3000/v1/service-ia/scraping/tecnocasa`
  - `http://localhost:3000/v1/service-ia/scraping/mubawab`
  - `http://localhost:3000/v1/service-ia/scraping/tayara`
  - `http://localhost:3000/v1/service-ia/scraping/tunisie_annonce`
  - `http://localhost:3000/v1/service-ia/scraping/fi_dari`
  - `http://localhost:3000/v1/service-ia/scraping/home_in_tunisia`

---

### 📊 C. Suivi des Statuts de Scraping (AI Service)

#### 1. Statut Global de TOUS les 6 Sites
- **Méthode** : `GET`
- **URL** : `http://localhost:3000/v1/service-ia/scraping/all/status`
- **Headers** : `Authorization: Bearer <TOKEN>`
- **Exemple de Réponse (200 OK)** :
```json
{
  "tecnocasa": {
    "job_id": "a1bb91a4-...",
    "source": "tecnocasa",
    "status": "completed",
    "step": "done",
    "result": {
      "scraped": 15,
      "inserted": 0,
      "updated": 15,
      "synced_crud": 15,
      "last_sync_date": "2026-08-14T14:05:35.186447+00:00"
    }
  },
  "tayara": {
    "job_id": "b80f16c9-...",
    "source": "tayara",
    "status": "completed",
    "step": "done",
    "result": {
      "scraped": 1000,
      "inserted": 72,
      "updated": 928,
      "synced_crud": 1000
    }
  },
  "tunisie_annonce": { "status": "completed", ... },
  "mubawab": { "status": "completed", ... },
  "fi_dari": { "status": "completed", ... },
  "home_in_tunisia": { "status": "completed", ... }
}
```

#### 2. Statut Individuel par Site
- **Méthode** : `GET`
- **URL** : `http://localhost:3000/v1/service-ia/scraping/{site}/status`
  - Exemple : `http://localhost:3000/v1/service-ia/scraping/tunisie_annonce/status`

---

### 🏡 D. Consultation & Pagination des Annonces (CRUD Service)

#### 1. Récupérer les Annonces avec Pagination (10 par page par défaut)
- **Méthode** : `GET`
- **URL** : `http://localhost:3000/v1/crud/properties?page=1&limit=10`
- **Réponse (200 OK)** :
```json
{
  "data": [
    {
      "_id": "...",
      "listing": {
        "id_universel": "HIT_87151378",
        "url_source": "...",
        "date_scraping": "2026-08-14T12:32:12.246274+00:00"
      },
      "bien": { "type": "appartement", "superficie_habitable": 74 },
      "transaction": { "type": "vente", "prix": 716880, "devise": "TND" },
      "localisation": { "ville": "Les Berges du Lac", "gouvernorat": "Tunis" },
      "metadonnees_scraping": { "source": "home_in_tunisia" }
    }
  ],
  "meta": {
    "total": 1105,
    "page": 1,
    "limit": 10,
    "totalPages": 111,
    "hasNextPage": true,
    "hasPrevPage": false
  }
}
```

#### 2. Filtrer par Source / Site Web
- **Méthode** : `GET`
- **Exemples** :
  - `http://localhost:3000/v1/crud/properties?site=mubawab&page=1&limit=10`
  - `http://localhost:3000/v1/crud/properties?site=tayara&page=1&limit=10`
  - `http://localhost:3000/v1/crud/properties?site=tunisie_annonce&page=1&limit=10`
  - `http://localhost:3000/v1/crud/properties?site=tecnocasa&page=1&limit=10`
  - `http://localhost:3000/v1/crud/properties?site=fi_dari&page=1&limit=10`
  - `http://localhost:3000/v1/crud/properties?site=home_in_tunisia&page=1&limit=10`

#### 3. Filtrer par Date & Période de Scraping (Nouveau)
- **Méthode** : `GET`
- **Paramètres supportés** : `startDate` (ISO), `endDate` (ISO)
- **Exemples** :
  - `http://localhost:3000/v1/crud/properties?startDate=2026-08-01&page=1&limit=10`
  - `http://localhost:3000/v1/crud/properties?endDate=2026-08-15&page=1&limit=10`
  - `http://localhost:3000/v1/crud/properties?startDate=2026-08-09&endDate=2026-08-14&page=1&limit=10`
  - `http://localhost:3000/v1/crud/properties?site=tayara&startDate=2026-08-01&page=1&limit=10`

#### 4. Recherche Multi-Critères Avancée (`/search`)
- **Méthode** : `GET`
- **URL** : `http://localhost:3000/v1/crud/properties/search`
- **Paramètres combinables** :
  - `source` : nom du site (`mubawab`, `tayara`, etc.)
  - `ville` : filtre par ville (insensible à la casse, ex: `Tunis`, `Sousse`)
  - `delegation` : filtre par délégation (ex: `La Marsa`, `Sahloul`)
  - `type` : type de bien (`appartement`, `villa`, `terrain`, `local_commercial`, `duplex`, `studio`, `immeuble`)
  - `transaction` : type de transaction (`vente`, `location`)
  - `prixMin` / `prixMax` : fourchette de prix en TND
  - `surfaceMin` / `surfaceMax` : surface totale en m²
  - `nombreChambres` : nombre de pièces/chambres
  - `startDate` / `endDate` : filtre par date de scraping
- **Exemples** :
  - `http://localhost:3000/v1/crud/properties/search?ville=Tunis&type=appartement&transaction=vente`
  - `http://localhost:3000/v1/crud/properties/search?prixMin=200000&prixMax=500000&surfaceMin=100`
  - `http://localhost:3000/v1/crud/properties/search?source=mubawab&ville=Sousse&type=appartement&prixMax=400000&startDate=2026-08-01`

#### 5. Statistiques & Sources Actives
- **Liste des sources actives** :
  - `GET http://localhost:3000/v1/crud/properties/sources`
- **Statistiques globales (comptes par site, par ville, prix min/max/moyen)** :
  - `GET http://localhost:3000/v1/crud/properties/stats`
- **Dernières annonces scrappées** :
  - `GET http://localhost:3000/v1/crud/properties/latest?limit=10`
- **Détail d'une annonce par son ID** :
  - `GET http://localhost:3000/v1/crud/properties/:id`

---

## 🗄️ 4. Visualisation dans MongoDB Compass

Pour inspecter les données en temps réel dans votre interface graphique :

- **URI de Connexion Compass** : `mongodb://localhost:27018`

| Base de Données | Collection | Description |
| :--- | :--- | :--- |
| `prophunter` | `properties` | Base principale unifiée utilisée par le CRUD service. |
| `prophunter` | `sync_metadata` | Suivi de l'état, de la date de sync (`last_sync_date`) et des compteurs par site. |
| `prophunter_ia` | `<site>_properties` | Collections dédiées par site (`mubawab_properties`, `tayara_properties`, etc.). |
| `prophunter_ia` | `scraping_jobs` | Historique et état en direct des exécutions des scrapers. |
| `prophunter_auth`| `users` | Comptes utilisateurs et administrateurs. |
