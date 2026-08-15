# Google OAuth 2.0 Client Setup — Agentic Cinema

**Status**: NOT YET CREATED — needs to be done before backend deploy

## Why We Need This

The backend's Google OAuth login gate (`src/web/auth.py`) needs a Google OAuth 2.0 Client ID
and Client Secret to start the Authorization Code flow. These are created in the Google Cloud
Console, NOT via `gcloud` CLI (the CLI doesn't have a direct command for creating OAuth 2.0
web application clients).

## Steps (User Action — 5 minutes)

### 1. Go to the Credentials page
Open: https://console.cloud.google.com/apis/credentials  
Make sure you're in the `acinema-hack-0807` project (top navigation bar).

### 2. Configure the OAuth Consent Screen (if not already done)
- Click "OAuth consent screen" tab
- Choose "External" user type (unless you have a Google Workspace org — unlikely)
- App name: `Agentic Cinema`
- User support email: `asifdotpy@gmail.com`
- Authorized domains: add `vercel.app` and `a.run.app` (the domains of our frontend + backend)
- Scopes: add `.../auth/userinfo.email`, `.../auth/userinfo.profile`, `openid`
- Test users: add `asifdotpy@gmail.com` (since it's External, only test users can auth until verified)
- Save and publish (or keep in "Testing" mode — Testing mode is fine for a hackathon as long as
  your email is a test user)

### 3. Create the OAuth 2.0 Client ID
- Click "Credentials" tab → "+ CREATE CREDENTIALS" → "OAuth client ID"
- Application type: **Web application**
- Name: `Agentic Cinema Web`
- **Authorized redirect URIs**:
  ```
  https://script-matrix-api-*-uc.a.run.app/api/auth/google/callback
  ```
  Replace `*-uc` with the actual Cloud Run service URL hash — but we don't know it yet.
  **Two approaches:**
  
  **Approach A (recommended)**: Deploy the backend FIRST without auth (or with auth disabled),
  get the Cloud Run URL from the deploy output, then come back and create the OAuth client with
  the real URL. This avoids a chicken-and-egg problem.
  
  **Approach B**: Create the OAuth client now with a placeholder, then edit the redirect URIs
  after deploy. Google lets you add/remove redirect URIs on an existing OAuth client.

  Also add for local dev (optional):
  ```
  http://localhost:8080/api/auth/google/callback
  ```
- **Authorized JavaScript origins**:
  ```
  https://script-matrix-api-*-uc.a.run.app
  ```
  (And `http://localhost:8080` for local dev if needed)
- Click "Create"

### 4. Copy the credentials
You'll get:
- **Client ID**: `*.apps.googleusercontent.com`
- **Client Secret**: `GOCSPX-...`

### 5. Store in GCP Secret Manager (recommended for Cloud Run)
```bash
# Create secrets
gcloud secrets create oauth-client-id --data-file=- <<< "YOUR_CLIENT_ID"
gcloud secrets create oauth-client-secret --data-file=- <<< "YOUR_CLIENT_SECRET"
gcloud secrets create jwt-secret --data-file=- <<< "A_RANDOM_32_CHAR_STRING"

# Grant Cloud Run service account access to these secrets
gcloud secrets add-iam-policy-binding oauth-client-id \
  --member="serviceAccount:<CLOUD_RUN_SA>@acinema-hack-0807.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
# Repeat for oauth-client-secret and jwt-secret
```

Or simpler for a hackathon: pass them as environment variables directly in the `gcloud run deploy`
command with `--set-env-vars`. Less secure but faster. The deployment plan uses Secret Manager
references where possible.

### 6. Also set the environment variables
After creating the OAuth client, set these in your local `.env` (for testing) and in Cloud Run:

```
GOOGLE_OAUTH_CLIENT_ID=*.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=GOCSPX-...
GOOGLE_ALLOWED_EMAILS=asifdotpy@gmail.com
JWT_SECRET=<random 32+ char string>
```

## What the Backend Does With These

1. `GOOGLE_OAUTH_CLIENT_ID` + `GOOGLE_OAUTH_CLIENT_SECRET` → authlib OAuth client (starts the
   Google Authorization Code flow)
2. `GOOGLE_ALLOWED_EMAILS` → email whitelist (`asifdotpy@gmail.com`) — only this email can log in
3. `JWT_SECRET` → signs the JWT issued after successful OAuth callback

## Timeline Note

This is the one piece that requires user action in the Google Cloud Console. Everything else
(code, Dockerfile, deployments) can be done programmatically. The OAuth client creation is
estimated at 5 minutes if the consent screen is already configured, or 10-15 minutes if it
needs to be set up from scratch.

**Blocker**: Backend cannot serve authenticated requests until this is done. The `/api/health`
endpoint is unprotected and can be used to verify the deployment is live before auth is configured.
