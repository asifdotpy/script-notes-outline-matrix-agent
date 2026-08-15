# Agentic Cinema — Frontend Fix Plan

## Current state

- Vercel deployment WORKS now (CSS returns 200, page renders).
- The 302 SSO redirect was from an old deployment (Aug 14, 23h ago). Latest is fine.
- Frontend is a bare-minimum single-page app inside `frontend/` of the monorepo.
- Vercel project is NOT connected to GitHub — deploys via `vercel --prod` only.
- Backend API surface is rich (8 endpoints + auth) but the frontend only scratches the surface.
- The frontend build crashes locally on WSL (SIGBUS, only 3.8GB RAM).

## Problems

1. **Frontend trapped inside monorepo** — must deploy from `frontend/` subdir, can't use Vercel Git integration, every deploy is manual.
2. **Vercel project has no GitHub link** — other projects in the account are Git-connected, this one is orphaned.
3. **Frontend is too minimal** — single page, no dashboard, no analytics views, no project management. The backend has 12 analytics views (per README) but the frontend shows 4 tabs at most.
4. **Auth flow is fragile** — token passed as URL param to `/callback`, stored in localStorage, no refresh token.
5. **No loading/error boundaries** — one crash kills the app.
6. **WSL can't run it locally** — `next build` and `next dev` crash with SIGBUS due to low RAM.

---

## Plan

### Phase 1: Separate frontend repo (30 min)

Create `asifdotpy/agentic-cinema-frontend` on GitHub.

Steps:
1. Create GitHub repo `agentic-cinema-frontend` (public, for the hackathon submission link).
2. Move `frontend/` contents into the new repo root. The current layout:
   ```
   frontend/
     src/app/layout.tsx, page.tsx, globals.css, callback/page.tsx, login/page.tsx
     src/components/Layout.tsx
     src/hooks/useAuth.ts
     src/lib/api.ts
     package.json, next.config.js, tsconfig.json, postcss.config.js
   ```
   becomes the new repo root.
3. Delete the old `frontend/` from the monorepo (after confirming the new repo works).
4. Push to GitHub:
   ```bash
   cd /home/asif1/agentic-cinema/frontend
   git init
   git remote add origin git@github.com:asifdotpy/agentic-cinema-frontend.git
   git add -A
   git commit -m "feat: standalone frontend for agentic cinema"
   git push -u origin main
   ```
5. Connect to Vercel: import the new repo as a project. Set root directory to `.` (repo root, not subdir).

### Phase 2: Fix Vercel config (15 min)

1. Remove the current orphaned Vercel project (or keep it as a backup alias).
2. In the new Git-connected project, set env vars:
   ```
   NEXT_PUBLIC_API_BASE = https://script-matrix-api-572921285869.us-central1.run.app
   NEXT_PUBLIC_FRONTEND_URL = https://agentic-cinema-frontend.vercel.app
   ```
3. Vercel auto-deploys on push to `main`.
4. `vercel --prod` is no longer needed.

### Phase 3: Expand frontend (1-2 hours)

The backend exposes:
- `POST /api/analyze` — upload + get results (done)
- `GET /api/projects` — list all projects (done)
- `GET /api/project/{id}?draft_version=N` — project detail (done)
- `POST /api/export/fdx` — download FDX file (done)
- `GET /api/health` — health check (NOT used)
- Analytics views: scene_density, stakeholder_disagreement, severity_heatmap, category_severity_matrix, stakeholder_influence, conflict_type_breakdown, conflict_aging, draft_progression, revision_risk_score, expected_scenes_to_revise, stakeholder_alignment (NOT shown in frontend)
- Benchmarks: headline, risk_leaderboard, global_category_dist, global_conflict_type_dist (partially shown)

New pages/routes:
1. **Landing/Dashboard (`/`)** — when authenticated, show project list + quick stats + upload CTA. When not authenticated, show login screen with app description.
2. **Upload (`/analyze`)** — separate page with the upload form, drag-drop, progress.
3. **Project Detail (`/project/[id]`)** — full project view with all 12 analytics tabs (chart.js is already installed).
4. **Benchmarks page (`/benchmarks`)** — cross-project leaderboard.
5. **Health badge** — small indicator in navbar showing backend status from `/api/health`.

UI improvements:
- Add a proper loading skeleton (not just `animate-pulse`).
- Add error boundaries.
- Add a "draft version" selector (the API supports `?draft_version=N`).
- Use Tailwind CSS instead of custom CSS (the project already has `@tailwindcss/postcss` in the unused `postcss.config.mjs`).

### Phase 4: Local dev workaround

Since WSL can't run `next build` or `next dev` (memory SIGBUS), options:
1. Use Tailwind CDN + plain HTML for local mockups, then commit.
2. Develop on a remote dev box (Cloud Shell, GitHub Codespaces) with more RAM.
3. Add `next.config.js` option `output: 'export'` to build a static site that can be served with any static server (no Node.js runtime needed).

The cleanest path for a hackathon: **option 3** — static export means the frontend is pure HTML/CSS/JS, faster to load, cheaper to host, and no Node.js memory issues anywhere.

---

## Decisions needed

1. **Static export (`output: 'export'` in next.config.js)** — yes/no?
   - Pro: works everywhere, no Node.js runtime, faster, no memory issues.
   - Con: no API routes (we don't have any, so fine), no SSR for auth pages (we use client-side JWT, so fine).
2. **Tailwind CSS** — adopt it for the redesign? The custom CSS works but is verbose.
3. **Monorepo cleanup** — delete `frontend/` from the monorepo after migration, or keep it as a copy?

---

## File inventory

Current frontend files (9 source files, ~1500 LOC):
```
src/app/layout.tsx        — root layout, imports Layout component
src/app/page.tsx          — main page (upload + results + tabs)
src/app/globals.css       — all custom CSS (~330 lines)
src/app/callback/page.tsx — OAuth callback handler
src/app/login/page.tsx    — login redirect
src/components/Layout.tsx — navbar + footer
src/hooks/useAuth.ts      — JWT auth state
src/lib/api.ts            — fetch wrapper + api object
package.json              — next 14.2.5, react 18, chart.js, lucide-react
next.config.js            — env var wiring
tsconfig.json             — path aliases (@/*)
postcss.config.js         — empty (plain CSS, no tailwind)
```

The entire frontend is ~1500 lines of code. Expanding it to a full multi-page app with proper analytics views is very doable.
