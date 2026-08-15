# Cloud Run Deployment — Agentic Cinema Backend

## Prerequisites
- `gcloud` authenticated: `gcloud auth login` (already done — asifdotpy@gmail.com)
- GCP project set: `gcloud config set project acinema-hack-0807` (already done)
- Google OAuth 2.0 client created (see `docs/oauth-setup.md`) — **BLOCKER**
- JWT secret generated

## Deployment Command

```bash
cd /home/asif1/agentic-cinema

gcloud run deploy script-matrix-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true \
  --set-env-vars GCP_PROJECT=acinema-hack-0807 \
  --set-env-vars GCP_LOCATION=us-central1 \
  --set-env-vars CLICKHOUSE_ENABLED=true \
  --set-env-vars CLICKHOUSE_HOST=tr94hevi75.germanywestcentral.azure.clickhouse.cloud \
  --set-env-vars CLICKHOUSE_PORT=8443 \
  --set-env-vars CLICKHOUSE_USER=default \
  --set-env-vars CLICKHOUSE_SECURE=true \
  --set-env-vars CLICKHOUSE_ALLOW_WRITE_ACCESS=true \
  --set-env-vars AGENT_ENGINE_ID=projects/572921285869/locations/us-central1/reasoningEngines/112072670463393792 \
  --set-env-vars GOOGLE_ALLOWED_EMAILS=asifdotpy@gmail.com \
  --set-secrets GOOGLE_OAUTH_CLIENT_ID=oauth-client-id:latest \
  --set-secrets GOOGLE_OAUTH_CLIENT_SECRET=oauth-client-secret:latest \
  --set-secrets CLICKHOUSE_PASSWORD=clickhouse-password:latest \
  --set-secrets JWT_SECRET=jwt-secret:latest \
  --service-account <CLOUD_RUN_SA>@acinema-hack-0807.iam.gserviceaccount.com
```

If Secret Manager isn't set up yet, use `--set-env-vars` for everything (less secure but faster):

```bash
gcloud run deploy script-matrix-api \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=true,GCP_PROJECT=acinema-hack-0807,GCP_LOCATION=us-central1, \
CLICKHOUSE_ENABLED=true,CLICKHOUSE_HOST=tr94hevi75.germanywestcentral.azure.clickhouse.cloud, \
CLICKHOUSE_PORT=8443,CLICKHOUSE_USER=default,CLICKHOUSE_SECURE=true,CLICKHOUSE_ALLOW_WRITE_ACCESS=true, \
AGENT_ENGINE_ID=projects/572921285869/locations/us-central1/reasoningEngines/112072670463393792, \
GOOGLE_OAUTH_CLIENT_ID=<CLIENT_ID>,GOOGLE_OAUTH_CLIENT_SECRET=<CLIENT_SECRET>, \
CLICKHOUSE_PASSWORD=<PASSWORD>,JWT_SECRET=<JWT_SECRET>, \
GOOGLE_ALLOWED_EMAILS=asifdotpy@gmail.com
```

## Build Configuration

The `Dockerfile` in the repo root is used by `--source .`. It:
1. Uses `python:3.10-slim` base image
2. Copies `pyproject.toml` + `src/` + `requirements.txt`
3. Runs `pip install -r requirements.txt`
4. Runs `uvicorn src.web.app:app --host 0.0.0.0 --port 8080`

The backend no longer needs `src/web/templates/` or `src/web/static/` at runtime (those were
for Jinja2 rendering — now the frontend is a separate Next.js app on Vercel).

## Required IAM Permissions

The Cloud Run service account needs:
- **Vertex AI User**: to call the Agent Engine (`projects/.../reasoningEngines/...`)
- **Storage Object Viewer**: for the Vertex AI staging bucket (`acinema-hack-staging-0807`)
- **Secret Manager Secret Accessor**: if using `--set-secrets` (for OAuth client secrets,
  ClickHouse password, JWT secret)

If deploying with the default compute service account, it may already have some of these.
Check with:
```bash
gcloud run services describe script-matrix-api --region us-central1 --format="value(status)"
```

## Post-Deploy

After successful deploy, the output will show the service URL:
```
Service URL: https://script-matrix-api-abc123-def456-uc.a.run.app
```

Save this URL — it's needed for:
1. Google OAuth client redirect URIs (edit the OAuth client to add this URL)
2. Frontend `NEXT_PUBLIC_API_BASE` environment variable

## Cost

Cloud Run free tier: 2M requests/month, 180,000 vCPU-seconds, 360,000 GB-seconds memory.
For a hackathon demo, this is well within free. After free tier exhaustion:
- ~$0.0000025 per request
- ~$0.0000125 per vCPU-second
- ~$0.0000025 per GB-second

With 0 minimum instances (scale to zero), you only pay for actual requests. Cold start
is 2-5 seconds for a Python container.

To keep a minimum of 1 instance (avoid cold start, costs ~$0.01-0.05/hour):
```bash
gcloud run services update script-matrix-api \
  --region us-central1 \
  --min-instances=1
```
Only do this if the demo needs to be snappy and you're OK with the small cost.
