# PropHunter TN – Progress Tracker

## Architecture

```
prophunter-backend/
├── gateway/          → NestJS  (Port 3000)  ← single entry point
├── ai-service/       → FastAPI (Port 3001)
└── crud-service/     → NestJS  (Port 3002)
```

---

## How to Start the Stack

```bash
# Terminal 1 – Gateway
cd gateway && npm run start:dev

# Terminal 2 – CRUD Service
cd crud-service && npm run start:dev

# Terminal 3 – AI Service
cd ai-service && .\.venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 3001 --reload
```

## Environment Variables

| File | Variables |
|---|---|
| `gateway/.env` | `PORT=3000` · `AI_SERVICE_URL=http://localhost:3001` · `CRUD_SERVICE_URL=http://localhost:3002` |
| `crud-service/.env` | `PORT=3002` · `MONGODB_URI=mongodb://localhost:27017/prophunter` |
| `ai-service/.env` | `MONGODB_URI=mongodb://localhost:27017` · `MONGODB_DATABASE=prophunter_ia` |

---

## Phase 1 – Microservices Architecture ✅

**Goal:** Scaffold three independent microservices, each with a `/health` endpoint.

- [x] NestJS Gateway — port **3000**
- [x] NestJS CRUD Service — port **3002**
- [x] FastAPI AI Service — port **3001**
- [x] `GET /health` on each service returns `{ status, service }`
- [x] Postman collection `PropHunterTN-Phase1.postman_collection.json`

---

## Phase 2 – Gateway Communication ✅

**Goal:** Turn the Gateway into the single entry point; proxy health checks to downstream services.

- [x] `@nestjs/axios` + `axios` installed in Gateway
- [x] `AiModule` — `GET /service-ia/health` → proxies to AI Service `:3001/health`
- [x] `CrudModule` — `GET /crud/health` → proxies to CRUD Service `:3002/health`
- [x] `GET /health` on Gateway aggregates status of all three services
- [x] Error handling: unreachable service returns `{ "status": "unavailable" }`
- [x] Postman collection `PropHunterTN-Phase2.postman_collection.json`

---

## Phase 3 – MongoDB Setup + Property Schema ✅

**Goal:** Connect CRUD Service to MongoDB and model the real estate listing document.

- [x] `@nestjs/mongoose@11` + `mongoose@8` installed in `crud-service`
- [x] `MongooseModule.forRoot()` wired into `AppModule` (reads `MONGODB_URI` from `.env`)
- [x] `property.schema.ts` — 11 sub-schemas matching all 6 scraping sources
- [x] MongoDB indexes on `listing.id_universel`, `metadonnees_scraping.source`, `localisation.ville`, `bien.type`, `transaction.prix` + compound
- [x] `PropertiesModule` scaffolded with stubbed service methods

### CRUD Service file structure

```
crud-service/src/
├── app.module.ts
├── app.controller.ts
└── properties/
    ├── properties.module.ts
    ├── properties.controller.ts
    ├── properties.service.ts
    └── schemas/
        └── property.schema.ts
```

---

## Phase 4 – Data Import (JSON → MongoDB) ✅

**Goal:** Load all scraped JSON files into MongoDB via a standalone TypeScript script.

- [x] `scripts/import-properties.ts` — reads 6 JSON sources, normalizes missing `id_universel`, detects duplicates
- [x] `npm run import` added to `package.json`
- [x] **6 526 annonces imported, 0 errors** — re-running is safe (duplicates skipped)

| Source          | Annonces |
|-----------------|----------|
| mubawab         | 2 407    |
| tecnocasa       | 1 132    |
| tayara          | 1 000    |
| tunisie_annonce | 1 000    |
| home_in_tunisia | 454      |
| fi_dari         | 533      |
| **Total**       | **6 526**|

---

## Phase 5 – Properties REST API ✅

**Goal:** Expose all 6 526 listings through a professional REST API in the CRUD Service.

- [x] `class-validator` + `class-transformer` installed
- [x] `ValidationPipe` enabled globally in `main.ts`
- [x] DTOs : `PaginationDto`, `LatestDto`, `SearchDto`
- [x] `PropertiesService` — 7 methods fully implemented with Mongoose
- [x] `PropertiesController` — 8 routes
- [x] Postman collection `PropHunterTN-Phase5.postman_collection.json`

### API Routes (CRUD Service — port 3002)

| Route | Description |
|-------|-------------|
| `GET /properties` | Paginated listing (`page`, `limit`) |
| `GET /properties/sources` | Distinct scraping sources |
| `GET /properties/stats` | Totals, by-source, by-ville, price range |
| `GET /properties/latest` | Most recent (`limit`) |
| `GET /properties/search` | Multi-criteria search |
| `GET /properties/source/:source` | All from one source |
| `GET /properties/:id` | Single doc by ObjectId |
| `GET /properties/health` | Module health check |

### Search filters — all optional, combinable

| Param | MongoDB field | Notes |
|---|---|---|
| `source` | `metadonnees_scraping.source` | exact |
| `ville` | `localisation.ville` | regex |
| `delegation` | `localisation.delegation` | regex |
| `type` | `bien.type` | regex |
| `transaction` | `transaction.type` | `vente` or `location` |
| `prixMin` / `prixMax` | `transaction.prix` | range |
| `surfaceMin` / `surfaceMax` | `bien.superficie_totale` | range |
| `nombreChambres` | `bien.nombre_chambres` | exact |
| `statut` | `listing.statut` | exact |

---

## Phase 6 – Gateway Proxy for Properties API ✅

**Goal:** Expose CRUD Service properties API through the Gateway (port 3000 only).

- [x] `gateway/src/properties/` module — proxied all 8 property routes
- [x] Postman collection `PropHunterTN-Phase6.postman_collection.json`

---

## Phase 7 – Gateway Refactoring: True Reverse Proxy ✅

**Goal:** Replace all per-endpoint modules with a single generic reverse proxy. No business logic in the Gateway.

### Iterations

**7.1** — Deleted `ai/`, `crud/`, `properties/` modules. Created `ProxyModule` with `ProxyService.proxyRequest()` and `V1Controller` using `@All()`.

**7.2** — Merged `v1.controller.ts` into `app.controller.ts`. `V1Controller` deleted.

**7.3** — Removed `resolveTarget()` from controller. URL reconstruction moved into `ProxyService.buildTargetUrl()`. Controller now only calls `this.proxyService.proxyRequest(req, res, this.url('ENV_VAR'))`.

**7.4** — `services.config.ts` deleted (dead code). `url()` now logs via `Logger.error` before throwing.

### Final Gateway file structure

```
gateway/src/
├── app.controller.ts    ← @Controller('v1'), Logger, url(), @All() handlers
├── app.service.ts
├── app.module.ts        ← imports [ProxyModule]
├── main.ts
└── proxy/
    ├── proxy.module.ts  ← HttpModule + ProxyService
    └── proxy.service.ts ← proxyRequest() + buildTargetUrl()
```

### Routing

| Client request | Proxied to |
|---|---|
| `ANY /v1/service-ia/*` | `AI_SERVICE_URL/*` |
| `ANY /v1/crud/*` | `CRUD_SERVICE_URL/*` |

### Supported calls

```
GET  /v1/service-ia/health
POST /v1/service-ia/scraping/tecnocasa
GET  /v1/crud/health
GET  /v1/crud/properties
GET  /v1/crud/properties/search?ville=Tunis&transaction=vente
POST /v1/crud/auth/signup
POST /v1/crud/auth/signin
```

### Error handling

| Situation | Response |
|---|---|
| Downstream 4xx / 5xx | Same status code forwarded |
| `ECONNREFUSED` / `ENOTFOUND` | `503 Service Unavailable` |
| Other network error | `502 Bad Gateway` |

---

## Phase 8 – AI Service Scraping (Tecnocasa) ✅

**Goal:** Integrate the Tecnocasa scraper into the FastAPI microservice and store results in MongoDB.

### File structure

```
ai-service/
├── main.py                          ← FastAPI app + router
├── requirements.txt
├── .env                             ← MONGODB_URI, MONGODB_DATABASE
└── app/
    ├── api/
    │   └── scraping.py              ← POST /scraping/tecnocasa
    ├── services/
    │   └── scraping_service.py      ← pipeline orchestrator
    ├── scrapers/
    │   └── tecnocasa/
    │       ├── tecnocasa_scraper.py ← scrape_links()
    │       ├── tecnocasa_details.py ← scrape_details(links)
    │       └── normaliser_tecnocasa.py ← normaliser(annonces)
    └── database/
        ├── mongodb.py               ← singleton client, reads .env
        └── property_repository.py  ← save_properties() with upsert
```

### Completed

- [x] `tecnocasa_scraper.py` — refactored to expose `scrape_links() → list` (no file output)
- [x] `tecnocasa_details.py` — refactored to expose `scrape_details(links) → list`
- [x] `normaliser_tecnocasa.py` — refactored to expose `normaliser(annonces) → list`
- [x] `scraping_service.py` — orchestrates the 4-step pipeline
- [x] `scraping.py` — `POST /scraping/tecnocasa` FastAPI endpoint
- [x] `mongodb.py` — singleton client, reads `MONGODB_URI` + `MONGODB_DATABASE` from `.env`
- [x] `property_repository.py` — `save_properties()` with **upsert** by `listing.id_universel` (zero duplicates)
- [x] `requirements.txt` updated — `requests`, `beautifulsoup4`, `pymongo` added
- [x] All imports verified — FastAPI starts cleanly

### Data flow (all in memory)

```
POST /scraping/tecnocasa
        ↓
scrape_links()           →  raw links list
        ↓
scrape_details(links)    →  enriched listings list
        ↓
normaliser(details)      →  PropHunter standard format
        ↓
save_properties()        →  upsert into MongoDB
        ↓
{ status, source, scraped, inserted, updated, ignored }
```

### MongoDB storage

- Database : **`prophunter_ia`**
- Collection : **`tecnocasa_properties`**
- Unique index : `listing.id_universel` (sparse) — re-running is safe

### API response

```json
{
  "status": "success",
  "source": "tecnocasa",
  "scraped": 1132,
  "inserted": 1132,
  "updated": 0,
  "ignored": 0
}
```

### Called via Gateway

```
POST http://localhost:3000/v1/service-ia/scraping/tecnocasa
```

---

## Phase 9 – Git Setup ✅

**Goal:** Initialize Git properly and push to the remote repository.

- [x] `.git` was incorrectly initialized in `C:\Users\ASUS` — removed
- [x] Git re-initialized in `prophunter-backend/` (correct root)
- [x] `.gitattributes` created — LF line endings enforced across the project
- [x] `.gitignore` verified — all `.env` files, `node_modules/`, `.venv/` excluded
- [x] Branch created : **`darine`**
- [x] Initial commit : 63 files
- [x] Remote added : `https://github.com/prophunt2026/prophunt.git`

### Push command (to run manually)

```powershell
cd C:\Users\ASUS\Desktop\prophunter-backend
git remote set-url origin https://github.com/prophunt2026/prophunt.git
git push -u origin darine
```

> If blocked by a 403 error: open **Gestionnaire d'informations d'identification Windows** → **Informations d'identification Windows** → delete the `github.com` entry → re-run the push → login with account **prophunt2026**.

---

## Upcoming

### Phase 10 – Authentication (Sign Up / Sign In) ⏸ DELAYED

> On hold — database technology not yet decided.

- [ ] User model / schema in CRUD Service
- [ ] `POST /auth/register` + `POST /auth/login` (returns JWT)
- [ ] JWT guards in CRUD Service
- [ ] Routed via `POST /v1/crud/auth/signup` + `POST /v1/crud/auth/signin`

### Phase 11 – Additional Scrapers 🔲

- [ ] Mubawab scraper → `POST /v1/service-ia/scraping/mubawab`
- [ ] Tayara scraper → `POST /v1/service-ia/scraping/tayara`
- [ ] Other sources follow the same pattern (no Gateway changes needed)

### Phase 12 – Full CRUD Operations 🔲

- [ ] `POST`, `PUT`, `DELETE` on `/properties`
- [ ] Routed via `/v1/crud/properties`
