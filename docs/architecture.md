# Architecture — Agentic Cinema Deployment (v2)

## Architecture Diagram

```
Internet
  │
  ├── Browser ─────────────────────────────────────────────────────────────┐
  │                                                                       │
  │   Vercel (Free Tier) ─────────────────────┐                           │
  │   https://agentic-cinema-frontend.vercel.app                       │
  │   ┌─────────────────────────────────────┐                           │
  │   │ Next.js 14 App Router              │                           │
  │   │ • /           → Home (upload page) │                           │
  │   │ • /login      → Sign-in page       │                           │
  │   │ • /callback   → Token capture      │                           │
  │   │ • /project/[id] → not used (API-driven)                     │
  │   └─────────────────────────────────────┘                           │
  │       │                                                       │
  │       │  HTTPS (CORS)                                        │
  │       ▼                                                       ▼
  │                                                                       │
  │   Google Cloud Platform ─────────────────────────────────────────────┐
  │   ┌─────────────────────────────────────────────────────────────┐     │
  │   │ Cloud Run (managed)                                      │     │
  │   │ https://script-matrix-api-<hash>-uc.a.run.app            │     │
  │   │ ┌─────────────────────────────────────────────────────┐   │     │
  │   │ │ FastAPI 0.110+ (src/web/app.py — JSON API version) │   │     │
  │   │ │                                                     │   │     │
  │   │ │ Endpoints:                                         │   │     │
  │   │ │  GET  /api/health          (public)               │   │     │
  │   │ │  GET  /api/auth/google/login        (starts OAuth)│   │     │
  │   │ │  GET  /api/auth/google/callback     (issues JWT)  │   │     │
  │   │ │  GET  /api/auth/logout             (clears cookie)│   │     │
  │   │ │  POST /api/analyze          (multipart upload)    │   │     │
  │   │ │  GET  /api/projects          (list all projects)  │   │     │
  │   │ │  GET  /api/project/{id}     (project detail)     │   │     │
  │   │ │  POST /api/export/fdx       (binary .fdx file)   │   │     │
  │   │ └─────────────────────────────────────────────────────┘   │     │
  │   │     │                                                     │     │
  │   │     │  Identity: Google OAuth 2.0 + JWT                  │     │
  │   │     ▼                                                     ▼     │
  │   │   Google Identity                                        JWT     │
  │   │   (accounts.google.com)                           (HS256)      │
  │   └─────────────────────────────────────────────────────────────┘     │
  │       │                                                               │
  │       │  Data plane:                                               │
  │       ▼                                                               ▼
  │   Vertex AI Agent Engine                          ClickHouse Cloud     │
  │   (Gemini 2.5 Flash)                             tr94hevi75...:8443   │
  │   Already deployed                                Already provisioned  │
  │   projects/572921285869/...                      Germany West Central  │
  └────────────────────────────────────────────────────────────────────────┘
```

## Auth Flow (Step by Step)

```
1. User visits https://agentic-cinema-frontend.vercel.app/
   └─ Frontend checks localStorage for JWT → not found → shows landing page with "Sign in with Google"

2. User clicks "Sign in with Google"
   └─ Frontend redirects: window.location = https://script-matrix-api-<hash>-uc.a.run.app/api/auth/google/login
   └─ Backend (Cloud Run) returns 302 → https://accounts.google.com/o/oauth2/v2/auth?...
   └─ Browser follows redirect to Google

3. User consents on Google's consent screen
   └─ Google redirects: https://script-matrix-api-<hash>-uc.a.run.app/api/auth/google/callback?code=<auth_code>

4. Backend callback:
   └─ authlib exchanges code for tokens
   └─ google.oauth2.id_token.verify_oauth2_token() verifies the ID token
   └─ Checks email against whitelist (GOOGLE_ALLOWED_EMAILS=asifdotpy@gmail.com)
   └─ Issues JWT: make_jwt_token("asifdotpy@gmail.com") → HS256, 1h expiry
   └─ Redirects: https://agentic-cinema-frontend.vercel.app/callback?token=<jwt>

5. Frontend /callback page:
   └─ Reads ?token= from URL
   └─ setToken(token) → localStorage.setItem("ac_jwt", <token>)
   └─ window.location.href = "/"

6. User now on home page, authenticated:
   └─ api.get("/api/projects") → reads JWT from localStorage → Authorization: Bearer <jwt>
   └─ Backend: require_jwt() → verify_jwt_token() → 200 with project list

7. User uploads a file:
   └─ POST /api/analyze with FormData (file + title)
   └─ JWT in Authorization header
   └─ Backend runs agent → persists to ClickHouse → returns JSON

8. Token expiry (after 1h):
   └─ Next API call returns 401
   └─ api.ts clears localStorage, calls on401()
   └─ Frontend redirects to /login
```

## CORS

| Resource | Origin |
|----------|--------|
| Frontend | `https://agentic-cinema-frontend.vercel.app` |
| Backend (prod) | `https://script-matrix-api-<hash>-uc.a.run.app` |
| Backend (local dev) | `http://localhost:8080` |

CORS middleware on the backend:
- `allow_origins`: FRONTEND_URL env var (or `*` for local dev fallback)
- `allow_credentials`: true (so cookies work for the OAuth session)
- `allow_methods`: GET, POST, OPTIONS
- `allow_headers`: Authorization, Content-Type
- `expose_headers`: Set-Cookie (so the frontend can see cookie ops if needed)

The JWT is sent as `Authorization: Bearer` — NOT a cookie — so CORS preflight is the main concern. The OAuth flow itself uses cookies on the backend domain for authlib's session state, but that's same-origin (browser → Cloud Run).

## Environment Variables

### Backend (Cloud Run) — set via --set-env-vars / --set-secrets
```
GOOGLE_GENAI_USE_VERTEXAI=true          # Use Vertex AI, not developer API
GCP_PROJECT=acinema-hack-0807           # GCP project ID
GCP_LOCATION=us-central1                # Region
CLICKHOUSE_ENABLED=true                 # Enable ClickHouse
CLICKHOUSE_HOST=tr94hevi75.germanywestcentral.azure.clickhouse.cloud
CLICKHOUSE_PORT=8443
CLICKHOUSE_USER=default
CLICKHOUSE_SECURE=true
CLICKHOUSE_ALLOW_WRITE_ACCESS=true
AGENT_ENGINE_ID=projects/572921285869/locations/us-central1/reasoningEngines/112072670463393792
GOOGLE_ALLOWED_EMAILS=asifdotpy@gmail.com
FRONTEND_URL=https://agentic-cinema-frontend.vercel.app   # For CORS + callback redirect

# Secrets (Secret Manager recommended):
GOOGLE_OAUTH_CLIENT_ID=<from console>
GOOGLE_OAUTH_CLIENT_SECRET=<from console>
CLICKHOUSE_PASSWORD=<from .env>
JWT_SECRET=<random 32+ chars>
```

### Frontend (Vercel) — set via dashboard or `vercel env add`
```
NEXT_PUBLIC_API_BASE=https://script-matrix-api-<hash>-uc.a.run.app
NEXT_PUBLIC_FRONTEND_URL=https://agentic-cinema-frontend.vercel.app
```

## Cost Breakdown (Free Tier)

| Component | Free Allowance | Estimated Usage (Hackathon) |
|-----------|---------------|---------------------------|
| Vercel (Hobby) | 100GB bandwidth/mo, 100GB-h serverless/mo, 6000 build min/mo | <1GB bandwidth, <1GB-h serverless |
| Cloud Run | 2M requests/mo, 180k vCPU-seconds, 360k GB-seconds | <1000 requests, <100 vCPU-seconds |
| Vertex AI / Agent Engine | Covered by hackathon credits | Per-token pricing (negligible for demo) |
| ClickHouse Cloud | Covered by existing setup | Already running |
| GCS (staging bucket) | 5GB standard storage free | Minimal (agent engine staging) |
| **Total estimated cost** | **$0** (all within free tier) | |

## Files

| File | Purpose |
|------|---------|
| `src/web/app.py` | FastAPI JSON API (refactored from Jinja2 monolith) |
| `src/web/auth.py` | Google OAuth + JWT layer (extended with PyJWT) |
| `Dockerfile` | Cloud Run container (python:3.10-slim, no templates/static) |
| `frontend/` | Next.js 14 frontend (Vercel deployment) |
| `frontend/src/app/page.tsx` | Home page — upload form, project view, analytics, tabs |
| `frontend/src/app/login/page.tsx` | Login page — "Sign in with Google" |
| `frontend/src/app/callback/page.tsx` | Callback — captures JWT from URL, stores in localStorage |
| `frontend/src/components/Layout.tsx` | Navbar (GitHub link, login/logout) + footer (GitHub link) |
| `frontend/src/lib/api.ts` | Authenticated fetch client (auto-attaches JWT) |
| `frontend/src/hooks/useAuth.ts` | Auth state hook |
| `docs/deployment.md` | This deployment tracker |
| `docs/architecture.md` | Architecture details |
| `docs/oauth-setup.md` | Google OAuth client setup (user action) |
| `docs/cloud-run-deploy.md` | gcloud commands |
| `docs/vercel-deploy.md` | vercel commands |
| `docs/api-reference.md` | API endpoint catalog |
