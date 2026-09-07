# 📖 PropHunter Backend — Documentation Complète de l'Architecture & des APIs

Bienvenue dans la documentation officielle du backend **PropHunter TN**. Ce document présente l'architecture des 4 microservices, le pipeline de scraping IA & synchronisation automatique, ainsi que le catalogue exhaustif de toutes les APIs du projet avec des exemples concrets pour le développement Frontend et les tests Postman.

---

## 🏛️ 1. Architecture Globale des Microservices

PropHunter repose sur une architecture moderne de microservices conteneurisée avec **Docker & Docker Compose** :

```
                        [ Client / Postman / Frontend ]
                                       │
                                       ▼ (Port 3000)
                         ┌───────────────────────────┐
                         │    API GATEWAY (NestJS)   │
                         │  - Routage & Reverse Proxy│
                         │  - Sécurité JwtAuthGuard  │
                         │  - Sécurité JwtAdminGuard │
                         │  - Service statique images│
                         └─────────────┬─────────────┘
                                       │
       ┌───────────────────────────────┼───────────────────────────────┐
       │                               │                               │
       ▼ (Port 3003)                   ▼ (Port 3001)                   ▼ (Port 3002)
┌───────────────┐              ┌───────────────┐              ┌───────────────┐
│ AUTH SERVICE  │              │  AI SERVICE   │              │ CRUD SERVICE  │
│    (NestJS)   │              │   (FastAPI)   │              │   (NestJS)    │
│               │              │               │              │               │
│ - Inscription │              │ - 6 Scrapers  │              │ - Annonces    │
│ - Connexion   │              │ - Upsert IA   │              │   Publiques   │
│ - Tokens JWT  │              │ - Auto-Sync   │              │ - CRUD User   │
│ - Profil/Avatar│             │ - Scoring IA  │              │ - Modération  │
│ - Hard Delete │              │ - Async Jobs  │              │ - Multer File │
└───────┬───────┘              └───────┬───────┘              └───────┬───────┘
        │                              │                              │
        ▼                              ▼                              ▼
┌──────────────────┐           ┌──────────────────┐           ┌──────────────────┐
│ prophunter_auth  │           │  prophunter_ia   │           │    prophunter    │
│  - users         │           │  - 6 collections │           │  - properties    │
│  - refresh_tokens│           │  - scraping_jobs │           │  - sync_metadata │
└──────────────────┘           └──────────────────┘           └──────────────────┘
                                 (MongoDB - Port 27018)
```

---

## 🔄 2. Pipeline de Scraping & Synchronisation Automatique

Lorsqu'un scraping est déclenché (`POST /v1/service-ia/scraping/all` ou `/v1/service-ia/scraping/{source}`) :

```
Déclenchement API (POST) ──▶ Réponse 202 Accepted immédiate (Tâche de fond Playwright)
                                       │
                                       ▼
                        Étape 1 : Scraping & Normalisation
                         (Liens, détails, prix, photos, contacts)
                                       │
                                       ▼
                        Étape 2 : Enregistrement dans l'IA
                         (Upsert par listing.id_universel dans prophunter_ia.<source>_properties)
                                       │
                                       ▼
                        Étape 3 : Synchronisation Automatique vers CRUD
                         (Upsert dans prophunter.properties avec scraping=true, status="accepted")
                                       │
                                       ▼
                        Étape 4 : Mise à jour des Métadonnées
                         (Enregistrement de last_sync_date dans prophunter.sync_metadata)
                                       │
                                       ▼
                                Statut = COMPLETED
```

### 🛡️ Garanties Techniques :
- **Anti-Doublons** : Index unique MongoDB sparse sur `listing.id_universel`.
- **Anti-Concurrence** : Verrou par site (`threading.Lock`) renvoyant `HTTP 409 Conflict` si un scraping est déjà en cours pour la même source.
- **Scraping Parallèle Indépendant** : Chaque site s'exécute dans son propre thread isolé.

---

## 📡 3. Catalogue Exhaustif des APIs

### 🔑 A. Authentification & Profil (`/v1/auth`)

#### 1. Inscription Utilisateur (`POST /v1/auth/signup`)
- **Public** (Sans token)
- **Body** :
  ```json
  {
    "email": "user_demo@test.tn",
    "password": "Pass@1234!",
    "nom": "Mohamed Ben Ali",
    "telephone": "+216 55 123 456"
  }
  ```
- **Réponse (201 Created)** : Renvoie l'ID utilisateur, nom, téléphone, email et rôle `USER`.

#### 2. Connexion Utilisateur / Admin (`POST /v1/auth/signin`)
- **Public** (Sans token)
- **Body** :
  ```json
  {
    "email": "user_demo@test.tn",
    "password": "Pass@1234!"
  }
  ```
  *(Admin par défaut : `admin@prophunter.tn` / `Admin@PropHunter2026!`)*
- **Réponse (200 OK)** :
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "refresh_token": "eyJhbGciOi...",
    "token_type": "bearer",
    "expires_in": 86400
  }
  ```

#### 3. Rafraîchissement du Token (`POST /v1/auth/refresh`)
- **Body** : `{ "refresh_token": "<VOTRE_REFRESH_TOKEN>" }`
- **Réponse (200 OK)** : Nouvel `access_token` et nouveau `refresh_token` avec rotation.

#### 4. Consulter son Profil (`GET /v1/auth/profile`)
- **Headers** : `Authorization: Bearer <USER_TOKEN>`
- **Réponse (200 OK)** :
  ```json
  {
    "id": "66b5f9...",
    "email": "user_demo@test.tn",
    "nom": "Mohamed Ben Ali",
    "telephone": "+216 55 123 456",
    "avatar": "http://localhost:3000/uploads/avatars/avatar_66b5f9_1725638.jpg",
    "role": "USER",
    "isActive": true
  }
  ```

#### 5. Mettre à jour son Profil (`PATCH /v1/auth/profile`)
- **Headers** : `Authorization: Bearer <USER_TOKEN>`
- **Body** :
  ```json
  {
    "nom": "Mohamed Ben Ali Modifié",
    "telephone": "+216 99 888 777"
  }
  ```

#### 6. Uploader sa Photo de Profil (`POST /v1/auth/profile/avatar`)
- **Headers** : `Authorization: Bearer <USER_TOKEN>`
- **Format** : `multipart/form-data` (champ fichier `avatar`)
- **Réponse (200 OK)** :
  ```json
  {
    "message": "Avatar mis à jour avec succès.",
    "avatar": "http://localhost:3000/uploads/avatars/avatar_66b5f9_1725638920.jpg"
  }
  ```

#### 7. Supprimer Définitivement son Compte (`DELETE /v1/auth/profile`)
- **Headers** : `Authorization: Bearer <USER_TOKEN>`
- **Action** : **Hard Delete** (Suppression de l'utilisateur dans MongoDB, suppression du fichier avatar sur disque, révocation des tokens, et suppression en cascade de **toutes ses annonces et photos** dans `crud-service`).
- **Réponse (200 OK)** : `{ "message": "Compte et données associées supprimés définitivement avec succès." }`

---

### 🕷️ B. Scraping IA (`/v1/service-ia/scraping` — Admin Only)

> ⚠️ Tous ces endpoints nécessitent le Header : `Authorization: Bearer <ADMIN_TOKEN>`

| Méthode | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/service-ia/scraping/all` | Déclenche le scraping parallèle des **6 sites** tunisiens |
| `GET` | `/v1/service-ia/scraping/all/status` | Statut et métriques globales des 6 scrapers |
| `POST` | `/v1/service-ia/scraping/mubawab` | Lancer le scraper Mubawab |
| `GET` | `/v1/service-ia/scraping/mubawab/status` | Statut du scraper Mubawab |
| `POST` | `/v1/service-ia/scraping/tayara` | Lancer le scraper Tayara |
| `GET` | `/v1/service-ia/scraping/tayara/status` | Statut du scraper Tayara |
| `POST` | `/v1/service-ia/scraping/tecno_casa` | Lancer le scraper Tecnocasa |
| `GET` | `/v1/service-ia/scraping/tecno_casa/status` | Statut du scraper Tecnocasa |
| `POST` | `/v1/service-ia/scraping/tunisie_vente` | Lancer le scraper Tunisie Vente |
| `GET` | `/v1/service-ia/scraping/tunisie_vente/status` | Statut du scraper Tunisie Vente |
| `POST` | `/v1/service-ia/scraping/dar_immo` | Lancer le scraper Dar Immo |
| `GET` | `/v1/service-ia/scraping/dar_immo/status` | Statut du scraper Dar Immo |
| `POST` | `/v1/service-ia/scraping/tunisie_annonce` | Lancer le scraper Tunisie Annonce |
| `GET` | `/v1/service-ia/scraping/tunisie_annonce/status` | Statut du scraper Tunisie Annonce |

---

### 🏡 C. Propriétés Publiques & Recherche (`/v1/crud/properties` — Sans Auth)

#### 1. Liste Paginée des Annonces Publiques (`GET /v1/crud/properties`)
- **Query Params** : `page` (défaut: 1), `limit` (défaut: 10)
- **Description** : Renvoie les annonces scrapées + les annonces utilisateurs acceptées par l'administrateur (`status: "accepted"`).

#### 2. Recherche Multi-Critères (`GET /v1/crud/properties/search`)
- **Paramètres combinables** :
  - `ville` : Ex: `Tunis`, `Sousse`, `Ariana`
  - `delegation` : Ex: `La Marsa`, `El Menzah`
  - `type` : Ex: `Appartement`, `Villa`, `Terrain`, `Bureau`
  - `transaction` : Ex: `Vente`, `Location`
  - `prixMin` / `prixMax` : Fourchette de prix en TND
  - `surfaceMin` / `surfaceMax` : Surface en m²
  - `nombreChambres` : Nombre de chambres
- **Exemple** :
  `GET http://localhost:3000/v1/crud/properties/search?ville=Tunis&type=Appartement&transaction=Vente&prixMin=100000&prixMax=600000`

#### 3. Détail d'une Annonce (`GET /v1/crud/properties/:id`)
- Renvoie toutes les caractéristiques, équipements, contacts et galerie de photos d'une annonce.

#### 4. Filtrer par Source (`GET /v1/crud/properties/source/:source`)
- Exemples : `/v1/crud/properties/source/mubawab`, `/v1/crud/properties/source/tayara`

---

### 👤 D. Annonces Utilisateurs — User CRUD (`/v1/crud/properties` — Auth Required)

Toutes ces actions sont accessibles depuis la page **Profil** de l'utilisateur connecté.

#### 1. Publier une Annonce Tout-en-un (`POST /v1/crud/properties`)
- **Headers** : `Authorization: Bearer <USER_TOKEN>`
- **Format** : `multipart/form-data` (Envoi direct des champs texte + fichiers images dans la même requête)
- **Champs du formulaire** :
  - `titre` : `"Appartement S+2 Haut Standing"`
  - `texte` : `"Superbe appartement vue mer..."`
  - `type_transaction` : `"Location"`
  - `prix` : `1800`
  - `type_bien` : `"Appartement"`
  - `superficie_totale` : `115`
  - `nombre_pieces` : `3`
  - `nombre_chambres` : `2`
  - `nombre_salles_bain` : `1`
  - `ville` : `"Tunis"`
  - `delegation` : `"La Marsa"`
  - `nom_contact` : `"Mohamed Ben Ali"`
  - `images` : *1 à 10 fichiers photos (.jpg, .png, .webp)*
- **Comportement** : Multer enregistre les fichiers physiques dans `/app/uploads/properties/`, construit les URLs complètes, crée l'annonce dans MongoDB avec `scraping: false` et lui attribue le statut automatique **`status: "pending"`**.

#### 2. Mes Annonces (`GET /v1/crud/properties/my-properties`)
- **Headers** : `Authorization: Bearer <USER_TOKEN>`
- **Description** : Renvoie la liste paginée de toutes les annonces publiées par l'utilisateur connecté avec leurs photos et leurs statuts (`pending`, `accepted`, `rejected`).

#### 3. Modifier mon Annonce (`PATCH /v1/crud/properties/my-properties/:id`)
- **Headers** : `Authorization: Bearer <USER_TOKEN>`
- **Format** : `multipart/form-data` ou `application/json`
- **Comportement** : Permet de modifier le prix, le texte ou d'ajouter de nouvelles photos. **Toute modification repasse automatiquement le statut à `"pending"`** pour ré-approbation obligatoire par l'administrateur.

#### 4. Supprimer mon Annonce (`DELETE /v1/crud/properties/my-properties/:id`)
- **Headers** : `Authorization: Bearer <USER_TOKEN>`
- **Description** : Supprime définitivement l'annonce et ses photos.

---

### 🛡️ E. Modération & Administration (`/v1/crud/admin/properties` — Admin Only)

> ⚠️ Headers requis : `Authorization: Bearer <ADMIN_TOKEN>`

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/crud/admin/properties?page=1&limit=20` | Voir **toutes** les annonces de la plateforme |
| `GET` | `/v1/crud/admin/properties?status=pending` | Filtrer les annonces **en attente de validation** |
| `GET` | `/v1/crud/admin/properties?status=accepted` | Filtrer les annonces **acceptées** (en ligne) |
| `GET` | `/v1/crud/admin/properties?status=rejected` | Filtrer les annonces **rejetées** |
| `GET` | `/v1/crud/admin/properties?scraping=true&site=tayara` | Filtrer les annonces scrapées par site source |
| `GET` | `/v1/crud/admin/properties?startDate=2026-08-01&endDate=2026-08-20` | Filtrer les annonces par période de scraping |
| `PATCH` | `/v1/crud/admin/properties/:id/status` | Changer le statut : `{"status": "accepted"}` ou `{"status": "rejected"}` |
| `PATCH` | `/v1/crud/admin/properties/:id` | Modifier n'importe quelle annonce de la base |
| `DELETE` | `/v1/crud/admin/properties/:id` | Supprimer définitivement une annonce |

---

### 📊 F. Métadonnées Scraping & Statistiques (`/v1/crud/properties` — Admin Only)

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/crud/properties/sources` | Liste de toutes les sources de scraping actives |
| `GET` | `/v1/crud/properties/stats` | Statistiques globales (par site, par ville, prix moyen/min/max) |
| `GET` | `/v1/crud/properties/latest?limit=10` | Les N dernières annonces scrapées |

---

## 🖼️ 4. Accès Direct aux Images Uploadées (Static Serve)

Toutes les images sauvegardées sont servies publiquement par l'API Gateway :
* **Avatar Utilisateur** : `http://localhost:3000/uploads/avatars/<nom_fichier>`
* **Photos d'Annonce** : `http://localhost:3000/uploads/properties/<nom_fichier>`

---

## 🗄️ 5. Schémas de Base de Données MongoDB (Compass : `localhost:27018`)

| Base de Données | Collection | Contenu |
|---|---|---|
| **`prophunter_auth`** | `users` | Utilisateurs & Admins (`nom`, `telephone`, `avatar`, `role`, `isActive`) |
| **`prophunter_auth`** | `refresh_tokens` | Tokens de rafraîchissement avec rotation et révocation |
| **`prophunter`** | `properties` | Base unifiée des annonces (`scraping`, `addedBy`, `status`, `medias.photos`) |
| **`prophunter`** | `sync_metadata` | Suivi des dates et compteurs de synchronisation par site |
| **`prophunter_ia`** | `<site>_properties` | Collections brutes scrapées par site (`mubawab_properties`, etc.) |
| **`prophunter_ia`** | `scraping_jobs` | Historique et état des tâches de scraping en arrière-plan |
