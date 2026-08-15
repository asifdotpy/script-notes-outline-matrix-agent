# Maximize Hackathon Score to 10/10 — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Turn the Script Notes-to-Outline Matrix Agent from a non-submittable build (~7.6/10 composite if blockers were cleared) into a complete, competitive submission that maximizes each Stage Two criterion toward 10/10, and clears Stage One so the project is actually in the running.

**Architecture:** No new code architecture is needed. The build is structurally complete. This plan is about (1) turning the agent on (Gemini credentials), (2) assembling the submission artifacts (hosted URL + demo video + Devpost form), and (3) sharpening the narrative for the criteria that are argument-based (Potential Impact, Quality of the Idea). The chDB-vs-Cloud decision is a strategic call, not a code change.

**Tech Stack (already in place):** google-adk 2.6.3, google-genai, google-cloud-aiplatform, mcp-clickhouse 0.4.1, chdb, FastAPI 0.141.1, pytest 9.1.1, Jinja2 + Tailwind + Chart.js (web UI). Deploy scripts: `deploy/deploy_agent.py` (Vertex AI Agent Engine), `deploy/cloud_run.yaml` (Cloud Run). Demo script: `docs/demo_script.md`. Pitch: `docs/pitch_why_this_wins.md`.

**Scoring target:** Stage One pass → Stage Two composite 9+ (realistic ceiling is ~9.3 because the LLM-quality axis has irreducible variance; 10/10 requires a flawless demo + live Cloud instance + airtight narrative — achievable but not guaranteed).

**Contest window:** Jul 27 – Sep 7, 2026 2:00 PM PT. Judging Stage One: after Sep 7. Stage Two: Sep 23 – Oct 7. Winners: ~Oct 7. Winner list requestable after Oct 12.

---

## Current State (as of 2026-08-12)

**What's built and tested (36 tests pass):**
- Ingestion (PDF + email, 11 tests), deterministic categorization (7 tests), conflict detection (7 tests), checklist assembly (10 tests), ClickHouse schema + analytics smoke test (chDB), Google OAuth gate (6 tests).
- ADK agent written (`src/agent/agent.py`): gemini-2.5-flash, 6 FunctionTools, complete instruction text. Imports cleanly. **Cannot run without Gemini credentials.**
- Web app boots and serves (FastAPI + Jinja2 + Tailwind + Chart.js). GET / returns HTML. POST /analyze is wired but can't complete without Gemini.
- `run_agent_demo.py`: full end-to-end CLI harness with retry logic (503/429), Vertex + Developer API modes, ClickHouse persistence fallback. **Cannot run without credentials.**
- `deploy/deploy_agent.py`: Vertex AI Agent Engine deploy script (complete, needs `gcloud auth` + ADC + GCP project).
- `deploy/cloud_run.yaml`: Cloud Run deploy instructions for the web app.
- `.env.example`: complete (chDB mode default + ClickHouse Cloud mode + Gemini/GC + web app settings).
- CI: `.github/workflows/ci.yml` present, runs pytest + eval harness on push/PR using chDB.
- Repo: public, LICENSE (Apache-2.0) at top, README corrected to honest state, `uvicorn_output.log` removed, `*.log` in .gitignore.

**What's NOT done (the 4 Stage One blockers):**
1. Hosted project URL — web app runs locally only.
2. 3-minute demo video — no video exists.
3. ClickHouse track declared on Devpost — no submission created.
4. Completed Devpost submission form — no submission exists.

**What's NOT proven:**
- The Gemini agent producing real categorized + conflict-flagged + checklist output. (Credentials missing.)
- ClickHouse Cloud instance live at demo time (chDB is the default; Cloud is env-flip away but SIGNUP100 confirmation pending).

**What's already strong (don't touch unless improving):**
- Validated pain (screenwriting-revision-paralysis.md: ~12 signals, validated status).
- Verified unowned competitive gap (SoCreate + Arc Studio both checked; neither ingests external notes + auto-structures + flags conflicts + outputs checklist).
- ClickHouse integration engineering (mcp-clickhouse driven in client.py, 3 analytical queries, persist fallback).
- Rules-aware design (admin/planning automation, not auto-writing creative text; instruction text forbids creative script generation).

---

## Strategic Decisions (make these first)

### Decision 1: chDB or ClickHouse Cloud for the demo?

**Recommendation: record the demo on chDB (free, no expiry), and ALSO spin up ClickHouse Cloud for the live submission if the SIGNUP100 credits confirm.**

Rationale:
- chDB is free, has no credit expiry, and IS ClickHouse (embedded). The rules say "connecting to a ClickHouse Cloud or self-hosted cluster." chDB is self-hosted. mcp-clickhouse officially supports it. The demo video recorded on chDB shows real ClickHouse analytics.
- The Devpost host ruling (resolved 2026-08-07) says judging uses submitted artifacts (hosted URL + demo video + repo), NOT a live env after credits lapse. So the demo video is the durable proof — record it while ClickHouse (whatever backend) is live.
- Risk of ClickHouse Cloud: the 30-day credit clock from activation. If you activate Aug 12, it lapses ~Sep 11 — AFTER the Sep 7 deadline AND during the judging window. The host ruling mitigates this for judging, but you'd still want the demo video recorded before lapse. And if SIGNUP100 $400 vs existing-account $300 trial is still unresolved (email to Mit Vaidya pending), you don't know your credit duration.
- **Decision:** record the demo on chDB (zero risk, zero cost, real analytics). Keep ClickHouse Cloud as an option for the live hosted URL if credits confirm and timing works. Don't let the Cloud-credit question block the demo video.

### Decision 2: Vertex AI or Developer API for Gemini?

**Recommendation: Vertex AI via Application Default Credentials (ADC).**

Rationale:
- The hackathon $100 GCP credit form was submitted Aug 6 and redeemed Aug 7, coupon valid to Oct 6 — past the Sep 7 deadline. So the $100 credits are available and cover the post-deadline judging window.
- Vertex mode (`GOOGLE_GENAI_USE_VERTEXAI=true`) uses ADC — no API key needed, no separate billing setup if `gcloud auth application-default login` is configured. The deploy script (`deploy/deploy_agent.py`) is written for this path.
- Developer API key mode needs a billing-enabled GCP project on the key's project and is subject to the 429/quota cap that the demo harness explicitly warns about.
- **Decision:** use Vertex AI + ADC. This is the path the code is written for.

### Decision 3: Hosted URL — Cloud Run or tunnel?

**Recommendation: Cloud Run for permanence, ngrok/ccloud tunnel as a fast fallback for the demo window if Cloud Run deploy is blocked.**

Rationale:
- Cloud Run (`deploy/cloud_run.yaml`) is the clean permanent option. `gcloud run deploy script-matrix-web --source . --platform managed --region us-central1 --allow-unauthenticated --set-env-vars CLICKHOUSE_MCP_AUTH_DISABLED=true`. Needs `gcloud` auth + GCP project.
- A tunnel (ngrok or cloudflare tunnel) running uvicorn locally is faster to set up and sufficient for the demo window + submission URL. The rules need a hosted URL for judging/testing — a tunnel URL works for that. It's not permanent (tunnel restarts drop the URL), but if you record the demo and submit before the tunnel dies, it's fine.
- **Decision:** try Cloud Run first (cleaner, permanent). If it's blocked (auth issue, region quota, etc.), fall back to a tunnel for the submission window. The web app's auth gate auto-disables without OAuth creds, so an open app is fine for the demo.

### Decision 4: Demo video — single cut or multi-file?

**Recommendation: one clean 3-minute cut on the sample_feedback.eml fixture, with a prepared real-looking PDF coverage report as a second upload if time permits.**

Rationale:
- The demo_script.md calls for showing the pain, the product, the agent running, the ClickHouse analytics, and the close. The sample_feedback.eml fixture already contains a planted conflict pair ("cut at least two pages from the intro" vs "loved the slow build — don't rush it; let it breathe"). That's the cleanest demo: one upload, one clear conflict, one checklist.
- Adding a PDF coverage report as a second upload demonstrates the PDF ingestion path and makes the demo richer, but it also adds complexity and time pressure. If the first cut is clean and under 3 minutes, add the PDF as a second act. If not, ship the single-file cut.
- The demo must show: upload → agent output (categorized notes) → conflict flag → checklist → ClickHouse analytics panel. All of this is wired in the web UI (index.html).
- **Decision:** primary cut on sample_feedback.eml. Secondary PDF upload if time permits and the first cut is solid.

### Decision 5: Devpost submission narrative — what to emphasize?

**Recommendation: frame around the validated pain + verified unowned gap + load-bearing ClickHouse analytics. Lead with impact, back it with evidence.**

The pitch doc (`docs/pitch_why_this_wins.md`) has the bones. The submission text should:
- Lead with the problem: screenwriters drown in unstructured external notes (PDFs, emails) and face conflicting guidance. Cite the validated evidence (Reddit, Facebook, Blacklist/Nicholls conflict, 4 verified WGA/produced-writer X posts).
- Name the gap: existing tools (SoCreate, Arc Studio) don't ingest external notes, auto-categorize, flag conflicts, or output a checklist. This is verified unowned.
- Show the solution: Gemini does the reasoning; ClickHouse holds the structured matrix + serves live analytics. Rules-compliant: planning automation, not auto-writing.
- Make the ClickHouse story concrete: notes_raw + notes_conflicts fact tables + notes_matrix view + 3 analytical queries (scene density, stakeholder disagreement, draft progress). This is relational analytics, not a key-value dump.
- Be honest about what's demonstrated vs. aspirational. The corrected README already does this. The Devpost text should match.

**Decision:** use the pitch doc as the backbone, expand it into the Devpost submission text, cite the evidence sources, and keep the tone specific and credible (not hype).

---

## Task Plan

### Task 1: Secure Gemini credentials (Vertex AI + ADC)

**Objective:** Get the ADK agent running end-to-end so the demo can be recorded and the hosted app can call the agent live.

**Why this is task 1:** Everything else (demo video, hosted app calling the agent, live analytics in the video) depends on the agent actually executing. This is the single highest-leverage action.

**Preconditions:**
- Access to a GCP project (the hackathon project `acinema-hack-0807` is referenced in the deploy script and .env.example, but the actual project ID + credentials are yours to provide).
- `gcloud` CLI installed and authenticated.
- The redeemed $100 GC coupon (submitted Aug 6, redeemed Aug 7, valid to Oct 6).

**Step 1: Authenticate gcloud + set up ADC**

Run:
```bash
gcloud auth login
gcloud auth application-default login
```

This sets up both user auth and Application Default Credentials for theVertex AI path. Verify:
```bash
gcloud auth list                    # should show active account
gcloud config get-value project     # or set: gcloud config set project acinema-hack-0807
```

**Step 2: Create .env with Vertex mode + project info**

Copy `.env.example` to `.env` and set:
```bash
GOOGLE_GENAI_USE_VERTEXAI=true
GCP_PROJECT=acinema-hack-0807          # or your actual project ID
GCP_LOCATION=us-central1
# GOOGLE_APPLICATION_CREDENTIALS is optional if gcloud ADC is set;
# set it to a service-account key path if you prefer SA auth.
CLICKHOUSE_MCP_AUTH_DISABLED=true
# chDB defaults (free, no account needed):
CHDB_ENABLED=true
CLICKHOUSE_ENABLED=false
CHDB_DATA_PATH=/tmp/agentic_cinema_chdb
```

**Step 3: Test the agent runs (CLI, no web app yet)**

Run:
```bash
source .venv/bin/activate
GOOGLE_GENAI_USE_VERTEXAI=true python run_agent_demo.py tests/sample_feedback.eml "The Tunnel — Draft 1"
```

Expected: the agent ingests the 9-line sample email, Gemini categorizes + detects the conflict ("cut the intro" vs "let it breathe"), persists to chDB via mcp-clickhouse, and prints the summary + analytics. If it works, you have a working end-to-end path on chDB with zero cloud credits spent.

If it fails with a credential error, debug ADC (`gcloud auth application-default print-access-token` should return a token). If it fails with a quota error (429 RESOURCE_EXHAUSTED), the harness already prints a clear message pointing to Vertex mode — verify `GOOGLE_GENAI_USE_VERTEXAI=true` is set.

**Step 4: (Optional) Deploy the agent to Vertex AI Agent Engine**

If you want the web app to call a remote agent (rather than the in-process runner), deploy:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=.sa-key.json   # if using SA auth
export GCP_PROJECT=acinema-hack-0807
python -m deploy.deploy_agent
```

This writes `AGENT_ENGINE_ID` to `.env`. The web app (`src/web/app.py`) reads `AGENT_ENGINE_ID` and calls the remote engine via `aiplatform.agent_engines.get(engine_id).stream_query()` instead of the in-process runner.

**Note:** deploying to Agent Engine consumes GCP resources. For the demo video, the in-process runner (no deployment needed) is sufficient — the demo video shows the web UI, which can use the in-process runner locally. The remote deployment is for the live hosted URL. Decide based on whether you deploy the web app to Cloud Run (remote agent needed) or tunnel uvicorn locally (in-process runner fine).

**Files:** `.env` (create from `.env.example`), possibly `.sa-key.json` (gitignored).

**Verification:** `run_agent_demo.py` produces categorized notes + conflict flag + ClickHouse persistence + analytics output. This is the proof the agent works.

**Risk:** Gemini quota (free tier is 20 requests/day for gemini-2.5-flash on the Developer API; Vertex AI has its own quota). The demo harness has retry logic for 503/429. If you hit quota during the demo recording, retry after the quota resets, or use a different Gemini model variant if available. The chDB persistence fallback means even a degraded agent still produces a ClickHouse-backed result.

---

### Task 2: Deploy the web app to a hosted URL

**Objective:** Clear the Stage One "hosted project URL" blocker and give the demo a real URL to show.

**Step 1: Try Cloud Run deploy**

Run from the repo root:
```bash
gcloud run deploy script-matrix-web \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars CLICKHOUSE_MCP_AUTH_DISABLED=true,CHDB_ENABLED=true,CLICKHOUSE_ENABLED=false,CHDB_DATA_PATH=/tmp/agentic_cinema_chdb
```

Expected: Cloud Run builds the container from the source, deploys, and prints a URL like `https://script-matrix-web-XXXXXX.us-central1.run.app`.

If this works, you have a permanent hosted URL. Set `AGENT_ENGINE_ID` in the Cloud Run env vars if you deployed the agent to Vertex AI (Task 1, Step 4); otherwise the web app will use the in-process runner (which works if the Cloud Run container has google-adk + google-genai installed — they are in requirements.txt).

**Step 1b (fallback): tunnel uvicorn locally**

If Cloud Run is blocked, run uvicorn locally and tunnel:
```bash
source .venv/bin/activate
uvicorn src.web.app:app --host 0.0.0.0 --port 8080
```

In another terminal, tunnel with ngrok or cloudflare tunnel:
```bash
ngrok http 8080
# or
cloudflared tunnel --url http://localhost:8080
```

This gives a public URL that forwards to your local uvicorn. Use this URL for the Devpost submission + demo video. Note: tunnel URLs are transient — if the tunnel restarts, the URL changes. For the submission window, keep the tunnel up until after the Sep 7 deadline.

**Step 2: Verify the hosted app works**

Open the URL in a browser (or curl):
```bash
curl -s https://your-app-url/ | head -20   # should return HTML
```

Upload the sample feedback via the web form (or curl POST) and confirm the agent runs and returns results. If the agent isn't deployed (no AGENT_ENGINE_ID + in-process runner fails), you'll see an "agent unavailable" message — fix Task 1 first.

**Files:** possibly `deploy/cloud_run.yaml` (already written, no change needed unless you want to adjust the deploy command).

**Verification:** a public URL that serves the web app and responds to /analyze with real agent output.

**Risk:** Cloud Run deploy may fail on region quota, source-build timeout, or missing GCP project permissions. The tunnel fallback avoids these. Auth: the web app's Google OAuth gate auto-disables without OAuth creds, so the hosted app is open by default — fine for the demo.

---

### Task 3: Record the 3-minute demo video

**Objective:** Produce a public YouTube/Vimeo video that demonstrates the agent working end-to-end, satisfying the rules §7 requirement and the Design + Impact criteria.

**Step 1: Prepare the demo input**

The sample_feedback.eml fixture is sufficient for a clean cut. Optionally prepare a real-looking PDF coverage report as a second upload (a 2–3 page PDF with cover-page notes + scene-specific feedback, including at least one conflict pair). The PDF parser is tested (suite A, 11 tests) — it should handle a clean text-layer PDF. Scanned PDFs are flagged, not silently dropped (test_a2), so use a text-layer PDF for the demo.

**Step 2: Run the demo live and capture the flow**

Open the hosted app (Task 2 URL) in a browser. Follow `docs/demo_script.md`:
- 0:00–0:30: show the pain (optional intro slide or voiceover — or just start at the app).
- 0:30–1:15: upload sample_feedback.eml, show the form.
- 1:15–2:15: show the agent output: categorized notes, the conflict flag ("cut the intro" vs "let it breathe"), the scene-by-scene checklist.
- 2:15–2:45: show the ClickHouse analytics panel (note-category frequencies, conflict count, scene coverage). If you have a ClickHouse Cloud instance live, show a `SELECT * FROM notes_matrix` result too.
- 2:45–3:00: close with the project name + hackathon + track.

**Step 3: Record**

Use screen recording (OBS, QuickTime, or similar). Keep it under 3 minutes — the rules say "If it is longer than 3 minutes, only the first 3 minutes will be evaluated." Aim for 2:45 to leave margin.

Audio: voiceover is optional (the demo_script.md says "no voiceover needed" for the pain section). If you do voiceover, speak clearly in English. If you don't, the on-screen text + flow must be self-explanatory.

**Step 4: Upload to YouTube or Vimeo**

Upload as unlisted first, verify it plays and is under 3 minutes, then make it public. Copy the URL.

**Step 5: Capture evidence screenshots**

Per `docs/demo_script.md`: screenshot of the web form with uploaded file + rendered checklist, and a screenshot of the ClickHouse analytics (or a `SELECT * FROM notes_matrix` result). These are useful for the Devpost submission text and the repo README.

**Files:** the video file (local), the YouTube/Vimeo URL, screenshots (optional, for the submission text).

**Verification:** a public YouTube/Vimeo URL, under 3 minutes, in English, showing the agent working end-to-end with ClickHouse analytics visible.

**Risk:** if the agent is flaky during recording (quota, latency), re-run. The demo harness (`run_agent_demo.py`) has retry logic; the web app's `/analyze` endpoint also retries. If the agent degrades, the fallback summary (from persisted ClickHouse data) still shows something useful — but for a 10/10 demo, you want the full Gemini output. Record when Gemini is responsive.

---

### Task 4: Create the Devpost submission + declare ClickHouse track

**Objective:** Clear the last 2 Stage One blockers (track declaration + submission form) and write a submission narrative that maximizes Potential Impact + Quality of the Idea.

**Step 1: Register on Devpost + create the submission**

Go to https://agentic-cinema.devpost.com/, sign in (or create an account as asifdotpy), click "Submit Project" (or "Join hackathon" → submit), and:
- Select **ClickHouse** as the partner track.
- Fill in the project title: "Script Notes-to-Outline Matrix Agent".
- Enter the hosted project URL (Task 2).
- Enter the demo video URL (Task 3).
- Enter the repo URL: https://github.com/asifdotpy/script-notes-outline-matrix-agent
- Write the submission description (Step 2).

**Step 2: Write the submission description**

Use `docs/pitch_why_this_wins.md` as the backbone. Structure:

1. **One-sentence summary:** "An agent that ingests external PDF coverage + producer emails, auto-categorizes notes, flags conflicting stakeholder feedback, and outputs a scene-by-scene Draft-2 revision checklist — with everything persisted to ClickHouse for live analytics."

2. **The problem (with evidence):** Screenwriters face "revision paralysis" — unstructured notes from multiple readers, conflicting guidance, no structured path from feedback to Draft 2. Cite the validated evidence briefly (Reddit r/Screenwriting thread, Facebook screenwriter group, Blacklist-vs-Nicholls conflict thread, 4 verified X posts from produced/WGA writers). Link to the idea file if you want to show the evidence depth.

3. **The gap (verified unowned):** Existing tools (SoCreate Feedback, Arc Studio) don't ingest external PDF/email notes, auto-categorize, flag conflicts, or output a scene-by-scene checklist. This is verified — cite the competitor check.

4. **The solution:** Gemini (Google Cloud Agent Platform / ADK) does the reasoning; ClickHouse (official mcp-clickhouse MCP server) holds the structured notes-matrix + conflict flags and serves live relational analytics (scene density, stakeholder disagreement, draft progress). Rules-compliant: automates planning/administration, never writes creative script text.

5. **ClickHouse story (concrete, not hand-wavy):** notes_raw fact table (one row per note, keyed by project + draft + scene), notes_conflicts fact table (one row per detected contradictory pair), notes_matrix view (notes joined to conflict tally). Three analytical queries demonstrated at runtime. This is relational analytics, not a vector DB — be explicit that ClickHouse is used for aggregation, not vector search (the pitch doc flags this; technical judges will appreciate the honesty).

6. **What's demonstrated:** the demo video shows upload → categorization → conflict flag → checklist → ClickHouse analytics. The repo contains the full source + tests (36 passing) + CI.

7. **Honest scope notes:** ClickHouse is used for relational aggregation, not vector search. .fdx export is format interchange, not a live in-editor plugin (Final Draft has no public plugin API). Be brief — judges respect honesty about scope.

**Step 3: Review against the rules**

Confirm the submission includes:
- [ ] Hosted project URL
- [ ] Demo video URL (YouTube/Vimeo, public, English, ≤3 min)
- [ ] Repo URL (public, Apache-2.0 license visible at top)
- [ ] ClickHouse track declared
- [ ] Submission form completed
- [ ] Text description with features, technologies, data sources, findings/learnings

**Files:** the Devpost submission (created on the site, not in the repo).

**Verification:** the submission appears on the hackathon site under the ClickHouse track, with all required fields populated.

**Risk:** the submission text overclaims (e.g., claiming a live Vertex AI deployment that doesn't exist, or claiming ClickHouse Cloud when it's chDB). Keep it honest — the corrected README is the model. JudgesValue accuracy over hype.

---

### Task 5: Sharpen the narrative for Potential Impact + Quality of the Idea

**Objective:** Maximize the two criteria where the project is already strongest (8/10 each) toward 9–10, by making the evidence + gap + ClickHouse-fit story as airtight as possible in the submission text + demo video.

This task is mostly writing + framing, not code. It depends on Tasks 1–4 being done (you need the working demo + submission to frame).

**Step 1: Make the pain evidence prominent, not buried**

The screenwriting-revision-paralysis.md file has ~12 verified signals. The Devpost submission text should name the strongest 3–4 and link them. Judges don't need all 12, but they need to see that the pain is real and evidenced, not invented. The 4 verified X posts from produced/WGA writers (Martell, Giglio, Vaughan, Jones) are especially strong — they're primary sources from named professionals.

**Step 2: Make the competitive gap explicit and verified**

State clearly: "We checked SoCreate Feedback and Arc Studio — the two closest competitors. Neither ingests external PDF/email notes, auto-categorizes by type/character/scene, flags conflicting stakeholder guidance, or outputs a scene-by-scene Draft-2 checklist. The gap is unowned." This is a strong Quality-of-Idea signal because it shows genuine problem-space understanding, not just a cool technical build.

**Step 3: Make the ClickHouse fit load-bearing, not decorative**

Explain WHY ClickHouse is the right tool: the notes-matrix is a write-heavy fact table (notes + conflicts arriving from multiple sources), and the analytics are aggregation-heavy (scene density, conflict rates, stakeholder disagreement breakdowns, draft-to-draft progress). ClickHouse excels at exactly this. The 3 analytical queries are the proof. Don't claim vector search — ClickHouse isn't a vector DB, and technical judges will catch it. The pitch doc already flags this; keep it.

**Step 4: Frame the "rules-compliant" design as a strength**

The project deliberately automates admin/planning (ingest → categorize → flag → checklist) rather than auto-writing creative script text. The agent's instruction text explicitly forbids creative script generation. This is a thoughtful response to the hackathon's spirit ("Lights. Camera. Code." — building agentic workflows, not content generators). Frame it as intentional, not defensive.

**Step 5: In the demo video, make the ClickHouse analytics visible and legible**

The Design + Impact criteria are judged from the demo video. If the analytics panel is tiny or illegible in the video, the ClickHouse story is weakened. Make sure the Chart.js analytics panel is visible, the conflict flag is highlighted, and the checklist is readable. A 3-minute video that clearly shows: upload → conflict flag → checklist → analytics, is a strong Design score.

**Step 6: Add a "findings and learnings" section to the submission**

The rules ask for "your findings and learnings as you worked through the project." Write 2–3 genuine learnings:
- The chDB-vs-Cloud decision and why chDB was chosen for the demo (credit-timing risk, host ruling on submitted artifacts).
- The persist_from_raw fallback design — why guaranteeing the ClickHouse story regardless of Gemini state matters for a hackathon submission.
- The conflict-detection heuristic design — why opposing-guidance (cut vs expand) is the right signal, and why agreement + different-concerns + self-restatement should NOT be flagged.

Genuine learnings signal real engagement with the problem, which scores on Quality of the Idea.

**Files:** Devpost submission text (Task 4, Step 2), demo video (Task 3).

**Verification:** the submission text + demo video make the pain + gap + ClickHouse-fit + rules-compliant design explicit and credible.

**Risk:** overclaiming. Don't claim a live Vertex AI deployment unless it's deployed. Don't claim ClickHouse Cloud unless it's Cloud. Don't claim 100% categorization accuracy unless the eval harness ran. Honesty is a strength here — the corrected README is the model.

---

### Task 6: Final submission readiness check (Stage One pass/fail self-audit)

**Objective:** Confirm the submission clears Stage One before the Sep 7 deadline, so it's actually in the running.

**Step 1: Run the Stage One checklist**

Per the official rules §7 (from the fetched rules file), confirm:

- [ ] Functional agent powered by Gemini + Google Cloud Agent Builder — YES (ADK agent, gemini-2.5-flash, written + imports cleanly; running end-to-end after Task 1).
- [ ] Integrates ClickHouse via official mcp-clickhouse MCP server at runtime — YES (src/clickhouse/client.py drives mcp-clickhouse; notes_raw + notes_conflicts + notes_matrix + 3 analytical queries; persist fallback guarantees the write even if the agent degrades).
- [ ] Project created during contest period (Jul 27 – Sep 7, 2026) — YES (repo initialized within the window).
- [ ] New, original work — YES (built from scratch in-contest).
- [ ] Team ≤ 4 — YES (solo).
- [ ] AI restriction: only Google Cloud AI + ClickHouse built-in AI — YES (Gemini via google-adk + google-genai + google-cloud-aiplatform; no other AI vendor in the codebase).
- [ ] Platform: web / Android / iOS — YES (web, FastAPI + Jinja2).
- [ ] Hosted project URL — Task 2.
- [ ] Demo video (YouTube/Vimeo, public, English, ≤3 min) — Task 3.
- [ ] Public OSS repo with license file visible at top (About section) — YES (Apache-2.0, at the top).
- [ ] Repo demonstrates runtime use of Google Cloud + ClickHouse in code (imported & called, not just named in README) — YES (google-adk + google-genai + google-cloud-aiplatform imported and called in agent.py; mcp-clickhouse imported and called in client.py).
- [ ] ClickHouse track declared — Task 4.
- [ ] Completed Devpost submission form — Task 4.
- [ ] Text description with features, technologies, data sources, findings/learnings — Task 4/5.

**Step 2: Address any misses**

If any item is unchecked, that's the priority. The 4 blockers (hosted URL, demo video, track declaration, form) are Tasks 2–4. Everything else is already met.

**Step 3: Submit before the deadline**

The deadline is Sep 7, 2026 @ 2:00 PM PT. Submit well before — don't cut it close. If the demo video or hosted URL isn't ready by Sep 7, the submission can't be completed. Work backward from the deadline: target having the submission ready by Sep 5 (2-day buffer for fixes).

**Verification:** the submission appears on the hackathon site, all fields populated, all checkboxes met. Stage One passed.

---

### Task 7: Post-submission — optional ClickHouse Cloud live instance (only if credits + timing work)

**Objective:** Optionally strengthen the submission with a live ClickHouse Cloud instance (instead of chDB) for the judging period, if the SIGNUP100 credits confirm and the timing works.

This is OPTIONAL. The chDB demo + the Devpost host ruling (submitted artifacts are what judges use) mean a Cloud instance is not required. But a live Cloud instance at demo time would remove the "is chDB really ClickHouse?" doubt and use the $400 credit.

**Step 1: Confirm SIGNUP100 eligibility + credit duration**

Check the reply from Mit Vaidya (mit.vaidya@clickhouse.com, email sent 2026-08-06). If no reply by the time you're ready to deploy, sign up for a fresh ClickHouse Cloud account with the SIGNUP100 promo code (https://console.clickhouse.cloud/signUp?promo=SIGNUP100) and confirm the $400 credit + 30-day duration.

**Step 2: If the timing works, spin up ClickHouse Cloud**

Activate the trial, create a service, set the env vars in the web app's deployment (CLICKHOUSE_HOST/PORT/USER/PASSWORD/SECURE, CLICKHOUSE_ALLOW_WRITE_ACCESS=true, CLICKHOUSE_ENABLED=true, CHDB_ENABLED=false). The code is already env-driven — no code change.

**Step 3: Re-record the demo on ClickHouse Cloud (if you want the Cloud impression)**

If you record the demo on Cloud, do it early (before the 30-day credit lapses). The demo video is the durable proof — record it while ClickHouse Cloud is live.

**Step 4: If the timing doesn't work, stay on chDB**

chDB is fine. The demo video on chDB shows real ClickHouse analytics. The host ruling says submitted artifacts are what judges use. Don't stress about Cloud if the timing is tight.

**Verification (if pursued):** a live ClickHouse Cloud instance serving the web app's analytics at demo time + in the submission.

**Risk:** credit expiry during judging (if activated too early). Mitigation: record the demo video early, rely on submitted artifacts for judging. If in doubt, stay on chDB.

---

## Files Likely to Change

| File | Change | Task |
|------|--------|------|
| `.env` | Create from `.env.example` with Vertex mode + project info + chDB defaults | Task 1 |
| `.sa-key.json` (optional) | Service-account key for Vertex AI SA auth (gitignored) | Task 1 |
| `deploy/cloud_run.yaml` | Possibly no change (already written); adjust if needed | Task 2 |
| `.github/workflows/ci.yml` | No change needed (already runs pytest + eval harness on chDB) | — |
| `README.md` | No change needed (already corrected to honest state) | — |
| `docs/demo_script.md` | Possibly refine timing/sequence after a test run | Task 3 |
| `docs/pitch_why_this_wins.md` | Possibly refine after the demo is recorded | Task 5 |
| Devpost submission (on the site) | Create + fill in | Task 4 |
| YouTube/Vimeo video (external) | Upload + publish | Task 3 |

**Files NOT likely to change:** the core code (agent.py, note_tools.py, client.py, schema.sql, queries.py, app.py, ingestion modules) is complete and tested. This plan doesn't add features — it turns the agent on and assembles the submission.

---

## Validation (after each task)

| Task | Validation |
|------|-----------|
| Task 1 | `run_agent_demo.py tests/sample_feedback.eml "The Tunnel — Draft 1"` produces categorized notes + conflict flag + ClickHouse persistence + analytics output. If it does, the agent works end-to-end on chDB. |
| Task 2 | A public URL serves the web app and responds to /analyze with real agent output. Confirm via curl or browser. |
| Task 3 | A public YouTube/Vimeo URL, ≤3 minutes, in English, showing upload → categorized notes → conflict flag → checklist → ClickHouse analytics. |
| Task 4 | The submission appears on agentic-cinema.devpost.com under the ClickHouse track, with hosted URL + video URL + repo URL + track declared + form completed + text description. |
| Task 5 | The submission text + demo video make the pain + gap + ClickHouse-fit + rules-compliant design explicit and credible (not hype). |
| Task 6 | The Stage One checklist is fully green. The submission is in the running. |
| Task 7 (optional) | A live ClickHouse Cloud instance serves the web app's analytics at demo time (only if credits + timing work). |

---

## Risks, Tradeoffs, and Open Questions

**R1 — Gemini quota / credential access (task 1 blocker):**
The agent cannot run without Gemini credentials. If you don't have GCP project access or the `gcloud` CLI set up, Task 1 blocks everything. The $100 GC coupon is redeemed (valid to Oct 6), but you need to actually authenticate + set the project. If Vertex AI ADC doesn't work for some reason, fall back to a Developer API key (GOOGLE_API_KEY in .env), but that needs billing enabled on the key's project and is subject to the 429 cap. The demo harness warns about this explicitly.

**R2 — ClickHouse Cloud credit timing (task 7):**
If you spin up ClickHouse Cloud too early, the 30-day trial may lapse during judging. The Devpost host ruling says submitted artifacts are what judges use, so the demo video is the durable proof — but if you want a live Cloud instance for the demo, record the video early. If the SIGNUP100 reply from Mit Vaidya doesn't come back, sign up fresh with the promo code and confirm the credit duration before activating. If in doubt, stay on chDB — it's free, has no expiry, and is ClickHouse-compatible.

**R3 — Demo video quality (task 3):**
A 10/10 demo is clear, legible, under 3 minutes, and shows the full flow. A rushed or illegible demo drags down Design + Impact regardless of how good the build is. Rehearse the flow once before recording. If the agent is flaky during recording, re-run — don't ship a demo where the agent fails mid-flow. The persist fallback means even a degraded agent shows something, but for 10/10 you want the full Gemini output.

**R4 — Overclaiming in the submission text (task 4/5):**
The corrected README is honest about what's deployed and what's not. The Devpost submission text should match. Don't claim a live Vertex AI deployment unless it's deployed. Don't claim ClickHouse Cloud unless it's Cloud. Don't claim 100% categorization accuracy unless the eval harness ran. Judges penalizing overclaiming is a real risk — honesty is safer and scores better on Quality of the Idea.

**R5 — Stage One pass/fail is a hard gate:**
If the submission misses any of the 4 blockers (hosted URL, demo video, track declaration, form), it doesn't get to Stage Two. The Sep 7 deadline is hard. Work backward from it: target having the submission ready by Sep 5.

**R6 — The vendored references/mcp-clickhouse directory (minor):**
The repo ships a full clone of the mcp-clickhouse repo in `references/` (with its own .git, tests, CI). It's labeled as a vendor reference and is Apache-2.0, but it's messy. Removing it from the tracked tree would improve the submission's cleanliness, but rewriting git history this close to the deadline is risky. Low priority — it won't lose the project the prize, but it's a small credibility tax. If you want to clean it up, the safest approach is to add `references/` to .gitignore (it's already there) and remove it from the tracked tree with `git rm -r --cached references/` (keeping the local copy), then commit. This doesn't rewrite history, just stops tracking the directory. Test that the build still works after (it should, since mcp-clickhouse is installed from PyPI, not from the references copy).

**R7 — Single-submission limit per track:**
The rules say "A Submission can win a maximum of one prize." You're submitting once to the ClickHouse track. Fine.

**Open question — cross-user aggregate reframe:**
The idea file says the cross-user aggregate-reframe (anonymized revision-pattern analytics across many writers) is the load-bearing impact story, but it's a build-scope choice, not locked. The current code supports single-project analytics. If you want the cross-user story for the submission, you'd need to extend the schema + queries to support multi-user aggregation (project_id already exists, so it's a query-scope change, not a schema change). For a 10/10 impact score, the cross-user story is a "nice to have" — the single-project analytics (scene density, conflict rates, stakeholder disagreement) are already a credible impact story. Decide whether to add the cross-user angle based on time + whether it materially strengthens the submission. My read: the single-project story is sufficient for a strong Impact score; the cross-user angle is a marginal upgrade, not a blocker.

---

## What a 10/10 Submission Looks Like (target state)

- **Stage One:** all checkboxes green. Hosted URL live, demo video public, ClickHouse track declared, Devpost form complete, repo public with Apache-2.0 at top, code demonstrates runtime Google Cloud + ClickHouse use.
- **Technological Implementation (target 9–9.5):** the agent runs end-to-end (Gemini categorizing + conflict-detecting + checklist-building), ClickHouse is used at runtime via mcp-clickhouse with a real relational schema + 3 analytical queries + the persist fallback, the web app is deployed and calls the agent, the demo video shows all of it working. No overclaims — what's demonstrated is what's claimed.
- **Design (target 9):** the demo video shows a complete, coherent product experience (upload → conflict flag → checklist → analytics), not a POC. The UI is legible in the video. The .fdx export is demonstrated if time permits.
- **Potential Impact (target 9–9.5):** the pain is real and evidenced (validated, ~12 signals), the gap is verified unowned (SoCreate + Arc Studio checked), the ClickHouse analytics story is concrete (not hand-wavy), and the demo shows a real screenwriter workflow being improved. The submission text makes the impact case clearly.
- **Quality of the Idea (target 9–9.5):** the idea is creative and non-obvious (screenwriting note-matrix agent + ClickHouse analytics is an unusual combination), the ClickHouse fit is load-bearing (not decorative), the rules-compliant design is intentional (planning automation, not content generation), and the submission shows genuine problem-space understanding (evidence + gap + competitive check + honest scope notes).

**The gap between current state (~7.6) and 10/10:** mostly the demo video + hosted URL + submission narrative. The code is ready. The idea is strong. The evidence is deep. What's missing is proof of the agent running (Task 1) and the submission artifacts assembled (Tasks 2–5). That's a short, mostly mechanical path — not a rewrite.

---

*Plan written 2026-08-12 from: judge scorecard (produced same session), official rules fetched from agentic-cinema.devpost.com (landing + /rules + /resources + /details/clickhouse-resources), live repo inspection (build status, test results, .venv state, .env.example, demo_script.md, pitch_why_this_wins.md, kanban plan).*
