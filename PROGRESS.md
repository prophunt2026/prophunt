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

---

## Phase 1 – Microservices Architecture ✅

**Goal:** Scaffold three independent microservices, each with a `/health` endpoint.

### Completed

- [x] NestJS Gateway — port **3000**
- [x] NestJS CRUD Service — port **3002**
- [x] FastAPI AI Service — port **3001**
- [x] `GET /health` on each service returns `{ status, service }`
- [x] Postman collection `PropHunterTN-Phase1.postman_collection.json`
- [x] All three services start independently

---

## Phase 2 – Gateway Communication ✅

**Goal:** Turn the Gateway into the single entry point; proxy health checks to downstream services.

### Completed

- [x] `@nestjs/axios` + `axios` installed in Gateway
- [x] `AiModule` — `GET /service-ia/health` → proxies to AI Service `:3001/health`
- [x] `CrudModule` — `GET /crud/health` → proxies to CRUD Service `:3002/health`
- [x] `GET /health` on Gateway aggregates status of all three services
- [x] Error handling: unreachable service returns `{ "status": "unavailable" }`, gateway never crashes
- [x] Postman collection `PropHunterTN-Phase2.postman_collection.json`

---

## Phase 3 – MongoDB Setup + Property Schema ✅

**Goal:** Connect CRUD Service to MongoDB and model the real estate listing document.

### Completed

- [x] `@nestjs/mongoose@11` + `mongoose@8` installed in `crud-service`
- [x] `MongooseModule.forRoot()` wired into `AppModule` (reads `MONGODB_URI` from `.env`)
- [x] `property.schema.ts` — 11 sub-schemas matching all 6 scraping sources
- [x] MongoDB indexes on `listing.id_universel`, `metadonnees_scraping.source`, `localisation.ville`, `bien.type`, `transaction.prix` + compound
- [x] `PropertiesModule` scaffolded with stubbed service methods
- [x] `nest build` passes with zero errors

### CRUD Service file structure

```
crud-service/src/
├── app.module.ts
├── app.controller.ts             ← GET /health
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

### Completed

- [x] `scripts/import-properties.ts` — reads all 6 JSON sources, normalizes missing `id_universel`, detects duplicates, prints summary
- [x] `npm run import` added to `package.json`
- [x] **6 526 annonces imported, 0 errors** — re-running is safe (duplicates skipped)

### Import results

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

### Completed

- [x] `class-validator` + `class-transformer` installed
- [x] `ValidationPipe` enabled globally in `main.ts`
- [x] DTOs: `PaginationDto`, `LatestDto`, `SearchDto`
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

### Completed

- [x] `gateway/src/properties/` module — proxied all 8 property routes through the Gateway
- [x] Postman collection `PropHunterTN-Phase6.postman_collection.json`

---

## Phase 7 – Gateway Refactoring: True Reverse Proxy ✅

**Goal:** Replace all per-endpoint modules with a single generic reverse proxy. No business logic in the Gateway.

### Iterations

Three incremental refactors led to the final architecture:

**7.1 — Generic proxy** — deleted `ai/`, `crud/`, `properties/` modules. Created `ProxyModule` with `ProxyService.proxyRequest()` and `V1Controller` using `@All()`.

**7.2 — Routes into AppController** — merged `v1.controller.ts` into `app.controller.ts`. `V1Controller` deleted.

**7.3 — URL logic into ProxyService** — removed `resolveTarget()` from controller. Controller now only calls `this.proxyService.proxyRequest(req, res, this.url('ENV_VAR'))`. URL reconstruction moved into `ProxyService.buildTargetUrl()`.

**7.4 — Dead code removed** — `services.config.ts` (`servicesConfig`, `proxyRoutes`) was no longer imported anywhere → deleted. `url()` now logs via `Logger.error` before throwing.

### Final Gateway file structure

```
gateway/src/
├── app.controller.ts    ← @Controller('v1'), Logger, url(), @All() handlers
├── app.service.ts       ← getHello()
├── app.module.ts        ← imports [ProxyModule]
├── main.ts
└── proxy/
    ├── proxy.module.ts  ← HttpModule + ProxyService
    └── proxy.service.ts ← proxyRequest() + buildTargetUrl()
```

### Responsibilities

| File | Responsibility |
|---|---|
| `AppController` | Receive request · log · read env var · call ProxyService |
| `ProxyService` | Build target URL · forward everything · handle errors |

### Routing

| Client request | Proxied to |
|---|---|
| `ANY /v1/service-ia/*` | `AI_SERVICE_URL/*` |
| `ANY /v1/crud/*` | `CRUD_SERVICE_URL/*` |

### URL reconstruction (inside ProxyService)

```
baseUrl  = http://localhost:3001
req.path = /v1/service-ia/scraping/tayara
result   = http://localhost:3001/scraping/tayara

baseUrl  = http://localhost:3002
req.path = /v1/crud/properties?ville=Tunis
result   = http://localhost:3002/properties?ville=Tunis
```

### Error handling

| Situation | Response |
|---|---|
| Downstream 4xx / 5xx | Same status code forwarded |
| `ECONNREFUSED` / `ENOTFOUND` | `503 Service Unavailable` |
| Other network error | `502 Bad Gateway` |

### Adding a new microservice

1. Add `NEW_SERVICE_URL=http://localhost:3003` to `gateway/.env`
2. Add `@All('new-service/*path')` in `app.controller.ts` calling `this.url('NEW_SERVICE_URL')`
3. Done — all HTTP methods handled automatically

---

## Upcoming

### Phase 8 – Authentication (Sign Up / Sign In) ⏸ DELAYED

> On hold — database technology not yet decided. Will resume once confirmed.

- [ ] User model / schema in CRUD Service
- [ ] `POST /auth/register` + `POST /auth/login` (returns JWT)
- [ ] JWT guards in CRUD Service
- [ ] Routed via `POST /v1/crud/auth/signup` + `POST /v1/crud/auth/signin` (no Gateway changes needed)

### Phase 9 – AI Scoring Service 🔲

- [ ] Scraping / scoring endpoints in AI Service
- [ ] Routed via `POST /v1/service-ia/scraping/:source` (no Gateway changes needed)

### Phase 10 – Full CRUD Operations 🔲

- [ ] `POST`, `PUT`, `DELETE` on `/properties`
- [ ] Routed via `/v1/crud/properties` (no Gateway changes needed)
