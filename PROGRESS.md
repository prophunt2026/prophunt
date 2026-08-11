# PropHunter TN – Progress Tracker

## Architecture

```
prophunter-backend/
├── gateway/          → NestJS  (Port 3000)  ← single entry point
├── auth-service/     → FastAPI (Port 3003)
├── ai-service/       → FastAPI (Port 3001)
└── crud-service/     → NestJS  (Port 3002)
```

---

## How to Start the Stack

```powershell
# Terminal 1 – Gateway
cd gateway
npm run start:dev

# Terminal 2 – Auth Service
cd auth-service
$env:PYTHONUNBUFFERED="1"
.\.venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 3003 --reload

# Terminal 3 – AI Service
cd ai-service
$env:PYTHONUNBUFFERED="1"
.\.venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 3001 --reload

# Terminal 4 – CRUD Service
cd crud-service
npm run start:dev
```

---

## Environment Variables

| File | Variables |
|---|---|
| `gateway/.env` | `PORT=3000` · `AI_SERVICE_URL=http://localhost:3001` · `CRUD_SERVICE_URL=http://localhost:3002` · `AUTH_SERVICE_URL=http://localhost:3003` · `JWT_SECRET_KEY=...` · `JWT_ALGORITHM=HS256` |
| `auth-service/.env` | `PORT=3003` · `MONGODB_URI=mongodb://localhost:27017` · `MONGODB_DATABASE=prophunter_auth` · `JWT_SECRET_KEY=...` · `JWT_ALGORITHM=HS256` · `ACCESS_TOKEN_EXPIRE_MINUTES=30` · `REFRESH_TOKEN_EXPIRE_DAYS=7` · `AUTH_ADMIN_EMAIL=admin@prophunter.tn` · `AUTH_ADMIN_PASSWORD=...` |
| `crud-service/.env` | `PORT=3002` · `MONGODB_URI=mongodb://localhost:27017/prophunter` |
| `ai-service/.env` | `MONGODB_URI=mongodb://localhost:27017` · `MONGODB_DATABASE=prophunter_ia` |

---

## MongoDB Databases

| Database | Service | Collections |
|---|---|---|
| `prophunter` | crud-service | `properties` |
| `prophunter_ia` | ai-service | `tecnocasa_properties` · `mubawab_properties` · `tayara_properties` · `tunisie_annonce_properties` · `fi_dari_properties` · `home_in_tunisia_properties` · `scraping_jobs` |
| `prophunter_auth` | auth-service | `users` · `refresh_tokens` |

---

## Phase 1 – Microservices Architecture ✅

- [x] NestJS Gateway — port **3000**
- [x] NestJS CRUD Service — port **3002**
- [x] FastAPI AI Service — port **3001**
- [x] `GET /health` on each service returns `{ status, service }`

---

## Phase 2 – Gateway Communication ✅

- [x] Gateway acts as single entry point
- [x] `ProxyModule` + `ProxyService.proxyRequest()` — generic reverse proxy
- [x] `ANY /v1/service-ia/*` → AI Service `:3001`
- [x] `ANY /v1/crud/*` → CRUD Service `:3002`
- [x] `ANY /v1/auth/*` → Auth Service `:3003`
- [x] Downstream errors forwarded with correct status codes
- [x] `ECONNREFUSED` → `503 Service Unavailable`

---

## Phase 3 – MongoDB Setup + Property Schema ✅

- [x] `property.schema.ts` — 11 sub-schemas matching all 6 scraping sources
- [x] MongoDB indexes on `listing.id_universel`, `metadonnees_scraping.source`, `localisation.ville`, `bien.type`, `transaction.prix`

---

## Phase 4 – Data Import (JSON → MongoDB) ✅

- [x] `scripts/import-properties.ts` — 6 526 annonces imported, 0 errors

| Source | Annonces |
|---|---|
| mubawab | 2 407 |
| tecnocasa | 1 132 |
| tayara | 1 000 |
| tunisie_annonce | 1 000 |
| home_in_tunisia | 454 |
| fi_dari | 533 |
| **Total** | **6 526** |

---

## Phase 5 – Properties REST API ✅

### API Routes (CRUD Service — port 3002)

| Route | Description |
|---|---|
| `GET /properties` | Paginated listing (`page`, `limit`) |
| `GET /properties/sources` | Distinct scraping sources |
| `GET /properties/stats` | Totals, by-source, by-ville, price range |
| `GET /properties/latest` | Most recent (`limit`) |
| `GET /properties/search` | Multi-criteria search |
| `GET /properties/source/:source` | All from one source |
| `GET /properties/:id` | Single doc by ObjectId |
| `GET /properties/health` | Module health check |

---

## Phase 6 – Gateway Proxy for Properties API ✅

- [x] All 8 property routes proxied through Gateway

---

## Phase 7 – Gateway Refactoring: True Reverse Proxy ✅

### Gateway file structure

```
gateway/src/
├── app.controller.ts    ← @Controller('v1'), @UseGuards(JwtGuard, RolesGuard), @All() handlers
├── app.service.ts
├── app.module.ts        ← imports [ProxyModule, AuthModule]
├── main.ts
├── proxy/
│   ├── proxy.module.ts
│   └── proxy.service.ts ← proxyRequest() + buildTargetUrl()
└── auth/
    ├── auth.module.ts
    ├── jwt.guard.ts     ← vérifie JWT (signature + exp + type=access)
    ├── roles.guard.ts   ← vérifie role ADMIN
    └── route-config.ts  ← table permissions centralisée (PUBLIC/AUTHENTICATED/ADMIN)
```

---

## Phase 8 – AI Service Scraping ✅

### 6 sources actives

| Source | Technologie | Collection |
|---|---|---|
| `tecnocasa` | requests | `tecnocasa_properties` |
| `mubawab` | requests + Selenium | `mubawab_properties` |
| `tayara` | requests (API JSON) | `tayara_properties` |
| `tunisie_annonce` | requests | `tunisie_annonce_properties` |
| `fi_dari` | Playwright async | `fi_dari_properties` |
| `home_in_tunisia` | Playwright sync + requests | `home_in_tunisia_properties` |

### Background job tracking

```
POST /scraping/{source}       → 202 Accepted { job_id, status: "pending" }
GET  /scraping/{source}/status → { status, step, result, error }
```

- Job statuses : `pending` → `running` → `completed` / `failed`
- `409 Conflict` si un job tourne déjà pour cette source
- `404` si la source est inconnue
- Cleanup automatique des jobs orphelins au démarrage (lifespan)
- Logs dans `ai-service/app/scrapers/logs/scraping.log`

### Called via Gateway (ADMIN only)

```
POST http://localhost:3000/v1/service-ia/scraping/tecnocasa
POST http://localhost:3000/v1/service-ia/scraping/mubawab
POST http://localhost:3000/v1/service-ia/scraping/tayara
POST http://localhost:3000/v1/service-ia/scraping/tunisie_annonce
POST http://localhost:3000/v1/service-ia/scraping/fi_dari
POST http://localhost:3000/v1/service-ia/scraping/home_in_tunisia
GET  http://localhost:3000/v1/service-ia/scraping/{source}/status
```

### Pour augmenter le nombre d'annonces (production)

| Source | Fichier | Variable |
|---|---|---|
| tecnocasa | `scrapers/tecnocasa/tecnocasa_scraper.py` | `MAX_PAGES = 50` |
| mubawab | `scrapers/mubawab/mubawab_scraper.py` | `MAX_PAGES = 100` |
| tayara | `scrapers/tayara/scraper.py` | `TARGET_ANNONCES = 1000` |
| tunisie_annonce | `scrapers/tunisie_annonce/scraper.py` | `MAX_PAGES = 40` + supprimer `unique[:10]` |
| fi_dari | `scrapers/fi_dari/scraper.py` | `TEST_LIMIT = None` |
| home_in_tunisia | `scrapers/scraper_Home_in_Tunisia/pipeline.py` | `TEST_LIMIT = None` + `max_scrolls=50` |

---

## Phase 9 – Git Setup ✅

- [x] Branch : **`darine`**
- [x] Remote : `https://github.com/prophunt2026/prophunt.git`

```powershell
cd C:\Users\ASUS\Desktop\prophunter-backend
git push -u origin darine
```

---

## Phase 10 – Auth Service ✅

### Architecture

```
auth-service/
├── main.py                          ← lifespan: indexes + ADMIN auto-création
├── requirements.txt
├── .env                             ← variables JWT + MongoDB + ADMIN credentials
├── .env.example
└── app/
    ├── api/auth.py                  ← POST /signup · POST /signin · POST /refresh
    ├── database/mongodb.py          ← singleton client
    ├── models/
    │   ├── user.py                  ← UserRole enum · UserDocument.create() · create_admin()
    │   └── refresh_token.py        ← RefreshTokenDocument (UTC naive)
    ├── repositories/
    │   ├── user_repository.py       ← find_by_email · insert · admin_exists · create_admin_if_needed
    │   └── refresh_token_repository.py ← insert · find_valid · revoke · ensure_indexes
    ├── schemas/auth.py              ← SignupRequest · UserResponse · SigninRequest · TokenResponse · RefreshRequest · RefreshResponse
    ├── security/
    │   ├── password.py              ← hash_password · verify_password (bcrypt rounds=12)
    │   └── jwt.py                   ← create_access_token · create_refresh_token (jti unique) · decode_*
    └── services/auth_service.py    ← signup · signin · refresh (rotation)
```

### Endpoints Auth (port 3003)

| Endpoint | Auth | Description |
|---|---|---|
| `GET /health` | Public | Health check |
| `POST /auth/signup` | Public | Crée un compte USER |
| `POST /auth/signin` | Public | Retourne access_token + refresh_token |
| `POST /auth/refresh` | Public | Rotation refresh token |

### Via Gateway

| Endpoint | Auth | Description |
|---|---|---|
| `POST /v1/auth/signup` | Public | |
| `POST /v1/auth/signin` | Public | |
| `POST /v1/auth/refresh` | Public | |

### JWT Access Token payload

```json
{
  "sub":   "<user_id>",
  "email": "user@test.com",
  "role":  "USER",
  "type":  "access",
  "exp":   1234567890
}
```

### Refresh Token

- JWT signé avec `jti` unique (UUID) — garantit zéro collision en base
- Stocké dans `prophunter_auth.refresh_tokens`
- Rotation : l'ancien RT est révoqué à chaque utilisation
- Index TTL : suppression automatique après expiration
- `type: "refresh"` — refusé comme Access Token

### Rôles & Permissions

| Rôle | Créé via | Accès scraping |
|---|---|---|
| `USER` | `POST /signup` (toujours) | ❌ 403 Forbidden |
| `ADMIN` | Créé automatiquement au démarrage | ✅ Autorisé |

- Le signup public crée **toujours** un `USER` — impossible de passer `role=ADMIN`
- L'ADMIN initial est créé au démarrage si aucun ADMIN n'existe (`AUTH_ADMIN_EMAIL` + `AUTH_ADMIN_PASSWORD` depuis `.env`)
- Redémarrage idempotent : si un ADMIN existe déjà → aucune création

### Gateway — table des permissions (`route-config.ts`)

| Pattern | Niveau | Comportement |
|---|---|---|
| `/v1/auth/*` | PUBLIC | Pas de JWT requis |
| `/v1/service-ia/*` | ADMIN | JWT valide + role=ADMIN |
| `/v1/crud/*` | AUTHENTICATED | JWT valide (USER ou ADMIN) |

### Codes d'erreur

| Situation | Code |
|---|---|
| Pas de token | 401 Unauthorized |
| Token invalide / expiré | 401 Unauthorized |
| Refresh Token utilisé comme Access Token | 401 Unauthorized |
| Token valide + role USER sur route ADMIN | 403 Forbidden |
| Email déjà utilisé (signup) | 409 Conflict |
| Email ou password incorrect (signin) | 401 Unauthorized (message générique) |

### Tests Postman — Auth complet

```
# 1. Signup USER
POST http://localhost:3000/v1/auth/signup
Body: { "email": "user@test.com", "password": "Password123!" }
→ 201 { role: "USER" }

# 2. Signin USER
POST http://localhost:3000/v1/auth/signin
Body: { "email": "user@test.com", "password": "Password123!" }
→ 200 { access_token, refresh_token, token_type, expires_in }

# 3. Refresh
POST http://localhost:3000/v1/auth/refresh
Body: { "refresh_token": "..." }
→ 200 { access_token (nouveau), refresh_token (nouveau), ... }

# 4. Signin ADMIN
POST http://localhost:3000/v1/auth/signin
Body: { "email": "admin@prophunter.tn", "password": "Admin@PropHunter2026!" }
→ 200 { access_token avec role=ADMIN }

# 5. Scraping sans token → 401
POST http://localhost:3000/v1/service-ia/scraping/tecnocasa
→ 401

# 6. Scraping avec token USER → 403
POST http://localhost:3000/v1/service-ia/scraping/tecnocasa
Header: Authorization: Bearer <USER_ACCESS_TOKEN>
→ 403

# 7. Scraping avec token ADMIN → 202
POST http://localhost:3000/v1/service-ia/scraping/tecnocasa
Header: Authorization: Bearer <ADMIN_ACCESS_TOKEN>
→ 202 { job_id, status: "pending" }
```

### Vérifier MongoDB Compass

- `prophunter_auth.users` → `email`, `password_hash` (jamais le mot de passe en clair), `role`, `created_at`, `updated_at`
- `prophunter_auth.refresh_tokens` → `token`, `user_id`, `expires_at`, `is_revoked`, `created_at`

---

## Upcoming

### Phase 11 – CRUD Service → exploiter les données du AI Service 🔲

- [ ] Modifier le CRUD Service pour lire depuis `prophunter_ia` (collections scrapées)
- [ ] Ou pipeline de transfert `prophunter_ia` → `prophunter`

### Phase 12 – Full CRUD Operations 🔲

- [ ] `POST`, `PUT`, `DELETE` sur `/properties`
- [ ] Routed via `/v1/crud/properties`

### Phase 13 – OTP / OAuth 2.0 🔲

- [ ] Google Login
- [ ] OTP par email
