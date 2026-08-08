# PropHunter TN – Gateway

The API Gateway is the single entry point for all client requests.  
Built with **NestJS** — runs on **port 3000**.

---

## Architecture

```
                         Client / Postman
                                │
                    http://localhost:3000
                                │
                         API Gateway
                        NestJS (3000)
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
                 ▼                             ▼
      AI Service (FastAPI)          CRUD Service (NestJS)
           Port 3001                     Port 3002
```

### Request flow (target – Phase 2+)

```
Client  →  Gateway (3000)  →  AI Service (3001)
                           →  CRUD Service (3002)
```

The Gateway will be responsible for:
- Routing incoming requests to the appropriate downstream service
- Centralising cross-cutting concerns (auth, rate-limiting, logging)
- Returning a unified response to the client

> Phase 1 scope: the Gateway does **not** yet proxy requests to downstream services.  
> Routing logic will be added in Phase 2.

---

## Endpoints

| Method | Path      | Description            |
|--------|-----------|------------------------|
| GET    | `/health` | Health check           |

### GET /health

```json
{
  "status": "ok",
  "service": "gateway"
}
```

---

## Getting started

```bash
# Install dependencies
npm install

# Development (watch mode)
npm run start:dev

# Production
npm run build
npm run start:prod
```

---

## Project structure

```
gateway/
├── src/
│   ├── app.controller.ts   # Routes: GET /, GET /health
│   ├── app.module.ts
│   ├── app.service.ts
│   └── main.ts             # Bootstraps on port 3000
├── package.json
└── tsconfig.json
```

---

## Related services

| Service      | Technology | Port |
|-------------|------------|------|
| Gateway      | NestJS     | 3000 |
| AI Service   | FastAPI    | 3001 |
| CRUD Service | NestJS     | 3002 |
