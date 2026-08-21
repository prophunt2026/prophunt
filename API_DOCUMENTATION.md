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

#### 2. Recherche Multi-Critères Avancée (`/search`)
- **Méthode** : `GET`
- **URL** : `http://localhost:3000/v1/crud/properties/search`
- **Paramètres combinables (Publics)** :
  - `ville` : filtre par ville (insensible à la casse, ex: `Tunis`, `Sousse`)
  - `delegation` : filtre par délégation (ex: `La Marsa`, `Sahloul`)
  - `type` : type de bien (`Appartement`, `Villa`, `Terrain`, `Local Commercial`, `Duplex`, `Studio`, `Immeuble`)
  - `transaction` : type de transaction (`Vente`, `Location`)
  - `prixMin` / `prixMax` : fourchette de prix en TND
  - `surfaceMin` / `surfaceMax` : surface totale en m²
  - `nombreChambres` : nombre de pièces/chambres
- **Exemples** :
  - `http://localhost:3000/v1/crud/properties/search?ville=Tunis&type=Appartement&transaction=Vente`
  - `http://localhost:3000/v1/crud/properties/search?prixMin=200000&prixMax=500000&surfaceMin=100`
  - `http://localhost:3000/v1/crud/properties/search?ville=Sousse&type=Appartement&prixMax=400000`

#### 3. Détail d'une Annonce Publique (`/:id`)
- **Méthode** : `GET`
- **URL** : `http://localhost:3000/v1/crud/properties/:id`
- **Description** : Récupère la fiche détaillée complète d'une annonce (scrapée ou utilisateur approuvée).

---

## 👤 4. Profil Utilisateur (`/v1/auth/profile`)

Tous ces endpoints nécessitent un JWT valide dans le header `Authorization: Bearer <access_token>`.

| Méthode | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/v1/auth/profile` | 🔑 User/Admin | Récupère les données du profil connecté (`email`, `nom`, `telephone`, `avatar`, `role`, etc.) |
| `PATCH` | `/v1/auth/profile` | 🔑 User/Admin | Met à jour les informations du profil (`nom`, `telephone`) |
| `DELETE` | `/v1/auth/profile` | 🔑 User/Admin | Désactive le compte utilisateur et révoque ses tokens |
| `POST` | `/v1/auth/profile/avatar` | 🔑 User/Admin | Upload de l'avatar du profil (`multipart/form-data`, champ `avatar`, max 5MB) |

#### Exemple : Upload de l'avatar (Postman)
- **Méthode** : `POST`
- **URL** : `http://localhost:3000/v1/auth/profile/avatar`
- **Headers** : `Authorization: Bearer <TOKEN>`
- **Body** : `form-data`
  - Clé : `avatar` (type `File`)
  - Valeur : *sélectionner une image (jpg, jpeg, png, webp)*

---

## 🏠 5. Annonces Utilisateurs (`/v1/crud/properties`)

Gestion des annonces créées manuellement par les utilisateurs connectés.

| Méthode | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/v1/crud/properties/upload-images` | 🔑 User/Admin | Upload de photos pour une annonce (`multipart/form-data`, champ `images`, jusqu'à 10 photos) |
| `POST` | `/v1/crud/properties` | 🔑 User/Admin | Soumettre une nouvelle annonce (`scraping: false`, `status: "pending"`, `addedBy: <userId>`) |
| `GET` | `/v1/crud/properties/my-properties` | 🔑 User/Admin | Liste paginée de toutes ses propres annonces soumises (tous statuts) |
| `PATCH` | `/v1/crud/properties/my-properties/:id` | 🔑 User/Admin | Mettre à jour sa propre annonce (repasse le statut à `pending`) |
| `DELETE` | `/v1/crud/properties/my-properties/:id` | 🔑 User/Admin | Supprimer sa propre annonce |

#### Exemple 1 : Uploader des photos pour une annonce
- **Méthode** : `POST`
- **URL** : `http://localhost:3000/v1/crud/properties/upload-images`
- **Headers** : `Authorization: Bearer <TOKEN>`
- **Body** : `form-data`
  - Clé : `images` (type `File` — sélectionner 1 ou plusieurs images)
- **Réponse reçue** :
  ```json
  {
    "message": "2 image(s) uploadée(s) avec succès.",
    "photos": [
      {
        "url": "/uploads/properties/prop_66b0a_1724151234_123456.jpg",
        "legende": "salon.jpg",
        "ordre": 1
      },
      {
        "url": "/uploads/properties/prop_66b0a_1724151234_789012.jpg",
        "legende": "chambre.jpg",
        "ordre": 2
      }
    ]
  }
  ```

#### Exemple 2 : Créer une annonce avec les URLs de photos obtenues
```http
POST http://localhost:3000/v1/crud/properties
Authorization: Bearer <TOKEN>
Content-Type: application/json

{
  "titre": "Appartement S+2 vue mer La Marsa",
  "texte": "Très bel appartement entièrement rénové...",
  "type_transaction": "Location",
  "prix": 1500,
  "type_bien": "Appartement",
  "superficie_totale": 95,
  "nombre_pieces": 3,
  "nombre_chambres": 2,
  "nombre_salles_bain": 1,
  "ville": "Tunis",
  "delegation": "La Marsa",
  "nom_contact": "Mohamed",
  "telephone": ["+216 55 123 456"],
  "photos": [
    {
      "url": "/uploads/properties/prop_66b0a_1724151234_123456.jpg",
      "legende": "Salon"
    }
  ]
}
```

---

## 🖼️ 6. Accès Direct aux Images Uploadées

Toutes les images stockées dans le volume Docker sont immédiatement consultables via le navigateur ou une application frontend :
- **Avatar** : `http://localhost:3000/uploads/avatars/<nom_fichier>`
- **Photos de Propriété** : `http://localhost:3000/uploads/properties/<nom_fichier>`

---

## 🛡️ 7. Administration & Modération (`/v1/crud/admin/properties`)

Endpoints réservés exclusivement aux administrateurs (`role === 'ADMIN'`).

| Méthode | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/v1/crud/admin/properties` | 🛡️ Admin | Voir **toutes** les annonces (filtres: `status`, `scraping`, `site`, `startDate`, `endDate`, `page`, `limit`) |
| `PATCH` | `/v1/crud/admin/properties/:id/status` | 🛡️ Admin | Valider (`accepted`), Rejeter (`rejected`), Désactiver (`inactive`) ou Remettre en attente (`pending`) |
| `PATCH` | `/v1/crud/admin/properties/:id` | 🛡️ Admin | Mettre à jour n'importe quelle annonce de la base |
| `DELETE` | `/v1/crud/admin/properties/:id` | 🛡️ Admin | Supprimer définitivement n'importe quelle annonce |
| `GET` | `/v1/crud/properties/sources` | 🛡️ Admin | Liste de toutes les sources de scraping actives |
| `GET` | `/v1/crud/properties/stats` | 🛡️ Admin | Statistiques globales (par site, par ville, prix min/max/moyen) |
| `GET` | `/v1/crud/properties/latest?limit=10` | 🛡️ Admin | Dernières annonces scrappées |

#### Exemples de Filtrage Admin :
- **Filtrer par période de scraping (ex: du 1er au 20 août)** :
  ```http
  GET http://localhost:3000/v1/crud/admin/properties?startDate=2026-08-01&endDate=2026-08-20&page=1&limit=20
  Authorization: Bearer <ADMIN_TOKEN>
  ```

- **Filtrer les annonces scrapées par site source (ex: tayara)** :
  ```http
  GET http://localhost:3000/v1/crud/admin/properties?scraping=true&site=tayara&page=1&limit=20
  Authorization: Bearer <ADMIN_TOKEN>
  ```

- **Lister les annonces en attente de modération** :
  ```http
  GET http://localhost:3000/v1/crud/admin/properties?status=pending&page=1&limit=20
  Authorization: Bearer <ADMIN_TOKEN>
  ```

- **Approuver une annonce** :
  ```http
  PATCH http://localhost:3000/v1/crud/admin/properties/66b0a1b2c3d4e5f6a7b8c9d0/status
  Authorization: Bearer <ADMIN_TOKEN>
  Content-Type: application/json

  {
    "status": "accepted"
  }
  ```

---

## 🗄️ 8. Visualisation dans MongoDB Compass

Pour inspecter les données en temps réel dans votre interface graphique :

- **URI de Connexion Compass** : `mongodb://localhost:27018`

| Base de Données | Collection | Description |
| :--- | :--- | :--- |
| `prophunter` | `properties` | Base principale unifiée (`scraping`, `addedBy`, `status`). |
| `prophunter` | `sync_metadata` | Suivi de l'état, de la date de sync (`last_sync_date`) et des compteurs par site. |
| `prophunter_ia` | `<site>_properties` | Collections dédiées par site (`mubawab_properties`, `tayara_properties`, etc.). |
| `prophunter_ia` | `scraping_jobs` | Historique et état en direct des exécutions des scrapers. |
| `prophunter_auth`| `users` | Comptes utilisateurs et administrateurs (`nom`, `telephone`, `avatar`, `role`, `isActive`). |

