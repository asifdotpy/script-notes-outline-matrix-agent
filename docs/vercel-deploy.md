# Vercel Deployment — Agentic Cinema Frontend

## Prerequisites
- Node.js 18+ installed
- `vercel` CLI installed and authenticated: `vercel login`
- Next.js app scaffolded in `frontend/` subdirectory

## CLI Deployment

```bash
cd /home/asif1/agentic-cinema/frontend

# First time — link to Vercel project (creates new project)
vercel

# Follow prompts:
# 1. "Link to existing project?" → No → "Create new Project"
# 2. Project name: agentic-cinema-frontend
# 3. Framework: Next.js (auto-detected)
# 4. Root directory: . (the frontend/ dir)
# 5. Build command: next build
# 6. Output directory: .next
# 7. Development command: next dev

# Deploy to production
vercel --prod --confirm
```

## Dashboard Deployment (Alternative)

1. Go to https://vercel.com/dashboard
2. "Add New → Project"
3. Import GitHub repo: `asifdotpy/script-notes-outline-matrix-agent`
4. Configure:
   - Framework: Next.js
   - Root Directory: `frontend`
   - Build Command: `next build`
   - Output Directory: `.next`
5. Environment Variables (add before deploying):
   - `NEXT_PUBLIC_API_BASE` = `https://script-matrix-api-<hash>-uc.a.run.app`
   - `NEXT_PUBLIC_FRONTEND_URL` = `https://agentic-cinema-frontend.vercel.app`
6. Click "Deploy"

## Environment Variables

Set these in Vercel project settings (dashboard or CLI):

```bash
vercel env add NEXT_PUBLIC_API_BASE https://script-matrix-api-<hash>-uc.a.run.app --prod
vercel env add NEXT_PUBLIC_FRONTEND_URL https://agentic-cinema-frontend.vercel.app --prod
```

`NEXT_PUBLIC_` prefix makes them available in client-side Next.js code (browser bundler).

## After Deploy

The Vercel dashboard will show the production URL:
```
https://agentic-cinema-frontend.vercel.app
```

This is the URL to put on your hackathon submission. The GitHub link on the webpage points to:
```
https://github.com/asifdotpy/script-notes-outline-matrix-agent
```

## Vercel Free Tier

- Hobby plan: free for personal/non-commercial projects
- Bandwidth: 100GB/month
- Serverless function execution: 100GB-h/month
- Build minutes: 6000 minutes/month
- For a hackathon demo, this is more than enough

## Custom Domain

Not required (you said no custom domain). The `*.vercel.app` URL works fine.
To add one later: Vercel dashboard → project → Domains → add custom domain.

## GitHub Integration

The frontend is in the `frontend/` subdirectory of the monolith repo.
When you push to `main` on GitHub, Vercel can auto-deploy (if you enable Git integration).
For now, manual `vercel --prod` deploys are fine.
