# API Reference — Agentic Cinema Backend

Base URL: `https://script-matrix-api-<hash>-uc.a.run.app`

All endpoints return JSON. Protected endpoints require `Authorization: Bearer <JWT>` header.

---

## Authentication

### `GET /api/auth/google/login`
Start Google OAuth 2.0 Authorization Code flow.
- **Auth**: None
- **Returns**: 302 redirect to Google OAuth consent screen
- **Frontend use**: `window.location = `${API_BASE}/api/auth/google/login``

### `GET /api/auth/google/callback`
OAuth callback — verifies Google ID token, issues JWT.
- **Auth**: None
- **Query**: `?code=...` (from Google)
- **Returns**: 302 redirect to frontend with `?token=JWT`
- **Side effect**: JWT issued, email checked against whitelist

---

## Public

### `GET /api/health`
Health check — verifies ClickHouse and Agent Engine connectivity.
- **Auth**: None
- **Response**:
```json
{
  "status": "ok",
  "clickhouse": "connected",
  "agent_engine": "connected"
}
```

---

## Protected (require JWT)

### `POST /api/analyze`
Upload a PDF/email file, run the agent, persist to ClickHouse, return results.
- **Auth**: JWT required
- **Content-Type**: `multipart/form-data`
- **Body**:
  - `file` (binary): PDF (`.pdf`) or email (`.eml`, `.txt`)
  - `title` (string): Script/project title
- **Response**:
```json
{
  "project_id": "the-tunnel-draft-1",
  "result": "Agent output text (Draft-2 revision plan)",
  "notes": [{ "note_id": "...", "scene_number": 1, "category": "Character", "severity": "Major", "raw_note_text": "...", "source_author": "..." }],
  "conflicts": [{ "conflict_id": "...", "scene_number": 1, "conflict_type": "...", "stakeholder_a": "...", "stakeholder_b": "...", "note_a": "...", "note_b": "..." }],
  "analytics": { "scene_density": [...], "stakeholder_disagreement": [...], "draft_progress": [...], "revision_risk_score": {...}, ... },
  "benchmarks": { "headline": {...}, "risk_leaderboard": [...], ... },
  "checklist": [{ "scene": 1, "items": ["...", "..."], "conflicts": ["..."] }],
  "n_lines": 42
}
```

### `GET /api/projects`
List all previously processed projects from ClickHouse.
- **Auth**: JWT required
- **Response**:
```json
[
  { "project_id": "the-tunnel-draft-1", "total_notes": 42, "last_updated": "2026-08-14T12:00:00Z" }
]
```

### `GET /api/project/{project_id}`
Get full project detail — notes, conflicts, analytics, checklist.
- **Auth**: JWT required
- **Query**: `?draft_version=N` (default: 1)
- **Response**:
```json
{
  "title": "The Tunnel Draft 1",
  "notes": [...],
  "conflicts": [...],
  "analytics": {...},
  "checklist": [...]
}
```

### `POST /api/export/fdx`
Generate a .fdx (Final Draft XML) file from the revision checklist.
- **Auth**: JWT required
- **Content-Type**: `application/json`
- **Body**:
```json
{
  "revision_checklist": [{ "scene": 1, "items": ["..."], "conflicts": ["..."] }],
  "agent_text": "Agent output text (optional)",
  "fdx_content": "Existing .fdx XML to inject into (optional)"
}
```
- **Response**: Binary XML file with `Content-Disposition: attachment; filename=Draft2_Revision_Matrix.fdx`
- **Content-Type**: `application/xml`

---

## Error Responses

All errors return:
```json
{ "detail": "Error message here" }
```

HTTP status codes:
- `401 Unauthorized` — missing or invalid JWT → frontend should redirect to `/login`
- `400 Bad Request` — invalid request body
- `500 Internal Server Error` — backend error (agent unavailable, ClickHouse down, etc.)
