# Deployment Documentation — Agentic Cinema

**Project**: Script Notes-to-Outline Matrix Agent (Agentic Cinema)  
**Hackathon submission**: Yes — GitHub link on webpage required  
**Deployment model**: Vercel (frontend/Next.js) + GCP Cloud Run (backend/FastAPI JSON API)  
**Date started**: 2026-08-14

---

## Architecture

```
Browser
  │
  ├── Vercel (free): agentic-cinema-frontend (Next.js SPA)
  │   • Routes: / , /login , /callback , /project/[id]
  │   • Auth: Google OAuth redirect → JWT stored in browser → Bearer on API calls
  │   • GitHub link: navbar + footer on every page
  │
  └─── HTTPS (CORS) ───▶
  Cloud Run (free/paid): script-matrix-api (FastAPI)
  │   • /api/auth/google/login        — start OAuth (302 to Google)
  │   • /api/auth/google/callback     — verify + issue JWT (302 to frontend)
  │   • /api/analyze                  — upload + agent run + ClickHouse persist
  │   • /api/projects                 — list projects from ClickHouse
  │   • /api/project/{id}             — notes, conflicts, analytics, checklist
  │   • /api/export/fdx              — generate .fdx file
  │   • /api/health                  — health check
  │   • Auth: JWT Bearer validation on protected endpoints
  │   • ClickHouse Cloud: tr94hevi75.germanywestcentral.azure.clickhouse.cloud:8443
  │   • Vertex AI Agent Engine: already deployed (AGENT_ENGINE_ID set)
  │
  └─── Google Cloud (ADC) ───▶
      Vertex AI (Gemini) + Agent Engine
```

---

## Status Tracker

| Phase | Task | Status | Notes |
|-------|------|--------|-------|
|| 0 | Create docs/ + tracker | ✅ Done | This file |
|| 1a | Refactor auth.py — JWT issuance + verification | ✅ Done | PyJWT, HS256, 1h expiry, `make_jwt_token()` + `verify_jwt_token()` + `require_jwt()` |
|| 1b | Refactor app.py — JSON API, CORS, 401 auth | ✅ Done | 7 endpoints: health, auth/*, analyze, projects, project/{id}, export/fdx |
|| 1c | Create Dockerfile | ✅ Done | python:3.10-slim, slim (no templates/static) |
|| 1d | Create Google OAuth 2.0 client (console) | ⏳ **BLOCKER — user action** | See `docs/oauth-setup.md` |
|| 1e | Deploy backend to Cloud Run | ⏳ Pending | After OAuth client created |
|| 2a | Scaffold Next.js frontend/ | ✅ Done | package.json, tsconfig, next.config, Layout, useAuth, api client |
|| 2b | Auth flow pages (login, callback, token) | ✅ Done | /login, /callback pages; useAuth hook; api.ts |
|| 2c | Home page — upload form | ✅ Done | Port from Jinja2 template; drag-drop, title, analyze button |
|| 2d | Project view — KPIs, tabs, notes, checklist, conflicts | ✅ Done | Port from Jinja2 template; all tabs functional |
|| 2e | Analytics charts (Chart.js, 12 charts) | ✅ Done | Port from Jinja2 template; react-chartjs-2 + chart.js |
|| 2f | GitHub link on all pages | ✅ Done | Navbar (desktop + mobile), footer, login page |
|| 3 | Deploy frontend to Vercel | ⏳ Pending | After backend URL known. Frontend compiles cleanly (`tsc` passes) |
|| 4 | End-to-end verification | ⏳ Pending | |
|| 5 | Final docs update | ⏳ Pending | |

---

## Key Configuration

### GCP Project
- Project ID: `acinema-hack-0807`
- Region: `us-central1`
- gcloud authenticated as: `asifdotpy@gmail.com`

### ClickHouse Cloud
- Host: `tr94hevi75.germanywestcentral.azure.clickhouse.cloud`
- Port: `8443`
- Secure: `true`
- User: `default`
- DB: `default`

### Vertex AI Agent Engine (already deployed)
- Resource: `projects/572921285869/locations/us-central1/reasoningEngines/112072670463393792`

### GitHub
- Repo: `https://github.com/asifdotpy/script-notes-outline-matrix-agent`
- Frontend subdirectory: `frontend/` (within the monolith repo)

### Auth
- Google OAuth 2.0 client: **NOT YET CREATED** — see `oauth-setup.md`
- Whitelist: `asifdotpy@gmail.com`
- JWT: HS256, 1-hour expiry, signed with `JWT_SECRET` env var

---

## File Inventory

### Backend (repo root)
- `src/web/app.py` — FastAPI app (being refactored from HTML to JSON API)
- `src/web/auth.py` — Google OAuth + session + JWT (being extended)
- `src/web/templates/` — Jinja2 templates (NO LONGER NEEDED on backend)
- `src/web/static/` — static assets (NO LONGER NEEDED on backend)
- `Dockerfile` — NEW, for Cloud Run
- `requirements.txt` — dependencies (needs PyJWT added)

### Frontend (repo root /frontend/)
- `frontend/` — NEW Next.js app (subdirectory in monolith repo)

### Docs
- `docs/deployment.md` — this file
- `docs/architecture.md` — architecture deep-dive
- `docs/oauth-setup.md` — Google OAuth client setup steps
- `docs/cloud-run-deploy.md` — gcloud commands + env vars
- `docs/vercel-deploy.md` — vercel commands + env vars
- `docs/api-reference.md` — API endpoint catalog
