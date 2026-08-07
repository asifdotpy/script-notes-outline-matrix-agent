# ClickHouse Cloud Provisioning Checklist — Agentic Cinema submission

**Purpose:** stand up ACTIVE ClickHouse runtime (rules requirement) and prove the live
path before the demo video + submission.

**Source of truth:** `agentic-cinema-brief.md` + Devpost clickhouse-resources page
(fetched 2026-08-07).
**Google credit:** REDEEMED, valid to **Oct 6, 2026** (covers deadline Sep 7 + judging).
**Deadline:** Sep 7, 2026 2:00 PM PT (~31 days out). Winner list requestable after Oct 12.

---

## EVIDENCE (fetched 2026-08-07 — corrects the earlier assumption)

- Devpost clickhouse-resources page documents **ONE** promo only:
  "new accounts get **$400** in credits — redeem via SIGNUP100"
  (link carries `utm_campaign=202608-WORLD-Google-Hackathon`, so it IS the hackathon promo).
- There is **NO** separate "$300 hackathon" credit on the Devpost page. The $300 is
  ClickHouse's **standard free trial** ($300), not a hackathon-specific longer credit.
- ClickHouse billing doc: "Trial credits expire at the end of the 30-day trial period."
- **Correction:** the theory "$400 = 1 month, $300 = longer hackathon period" is
  UNSUPPORTED. Both likely look 30-day. Do NOT rely on a long-lived $300.
- **Implication:** SIGNUP100 $400 (new account) is the submission workhorse. The existing
  $300 trial (if still live) is a dev sandbox only — use it to de-risk the live path NOW.

## OFFICIAL RULING (Devpost host reply, 2026-08-06 thread "How will judges test projects
after cloud credits expire?") — RESOLVES the timing blocker
Janet Fang (Devpost Manager) confirmed, in reply to a ClickHouse+GCP participant whose
credits expired ~Aug 31:
- Judges evaluate what is SUBMITTED — hosted Project URL, demo video, and repo — NOT a
  live environment running indefinitely.
- If Google Cloud OR ClickHouse credits expire before judging, **the demo video is the
  backstop**: as long as it clearly shows the agent working end-to-end, that is fully
  acceptable for judging even if the live environment goes down later.
- Keep the hosted URL live as long as credits last; ensure the demo video captures the
  FULL workflow.
**Effect on us:** the "instance must survive to Oct 12" fear is GONE. We no longer need a
long-lived credit. We need: (1) public repo, (2) hosted URL live at submission, (3) a demo
video showing the full workflow with LIVE ClickHouse on screen. The video is permanent
judging proof. This also means the duplicate discussion post is UNNECESSARY — the answer is
official and ClickHouse-specific.

## STRATEGY (updated per ruling)
1. No need to keep ClickHouse alive through judging — the video covers it.
2. Spin up whichever credit (SIGNUP100 $400 preferred for runway; standard $300 also fine)
   with enough lead time to RECORD THE DEMO VIDEO while live, then deploy + submit while
   the URL is still live. A ~Aug 28–30 spin-up keeps the URL live past the Sep 7 deadline
   with margin; earlier is fine too.
3. The demo video MUST show the full workflow end-to-end (ingestion → categorize →
   conflicts → checklist → LIVE ClickHouse analytics panel). This is the judging backstop.
4. Keep hosted URL live while credits last; submit before Sep 7 2:00 PM PT.

---

## PART A — YOUR actions (need ClickHouse login + promo code; agent will NOT do these)

- [ ] **A1. Confirm account/promo facts:**
  - Is the existing ClickHouse account on the standard $300 / 30-day trial?
  - Does SIGNUP100 $400 require a *new* account (Devpost says "new accounts")? If yes,
    existing account can't get the $400 → need a fresh account.
  - Is the existing $300 trial still live, or already lapsed (brief risk noted it could
    lapse ~Sep 5 if started Aug 6)?
- [ ] **A2. Create / claim the SIGNUP100 $400 account** (new account if required) and
      capture: `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT` (8443), `CLICKHOUSE_USER`,
      `CLICKHOUSE_PASSWORD`.
- [ ] **A3. Create a ClickHouse Cloud service** (instance) in a region near us-central1.
- [ ] **A4. (Optional but recommended) Ping Mit Vaidya (mit.vaidya@clickhouse.com)** to
      CONFIRM the $400 SIGNUP100 duration (30-day vs longer) and any extension through
      the Oct 12 judging window. This only tightens the timing — not a hard blocker now
      that the 30-day assumption is the conservative baseline.

## PART B — TIMING WINDOW (per official ruling: video is the backstop)

- The live instance does NOT need to survive to Oct 12. It only needs to be live when we
  record the demo video AND at submission (URL live while credits last).
- **Now (dev, optional):** if the existing $300 trial is still live, run C0 to verify the
  live Cloud path — low risk, proves the env-swap. Not required (chDB already verifies logic).
- **Spin-up window:** create the ClickHouse instance with enough lead to record the video
  and submit before it lapses. A ~Aug 28–30 spin-up keeps the URL live past Sep 7 with
  margin. Earlier is also fine — the video remains valid proof regardless of later lapse.
- **Hard requirement:** demo video captures the FULL workflow with live ClickHouse analytics
  on screen. This is what judges will rely on if the env later dies.

## PART C — AGENT-verifiable steps (run after creds/instance available)

- [ ] **C0. Verify live Cloud path NOW (dev sandbox, if $300 trial live):** flip `.env` to
      the existing instance, `python -m src.clickhouse.client` (expect "schema initialized
      OK"), run `python run_agent_demo.py tests/sample_feedback.eml` with `GEMINI_API_KEY`
      set. Proves the env-swap works before the late $400 spin-up.
- [ ] **C1. Flip env for submission instance.** In `agentic-cinema/.env`: set
      `CLICKHOUSE_HOST/PORT/USER/PASSWORD/SECURE=true`, `CLICKHOUSE_ENABLED=true`,
      `CHDB_ENABLED=false`. Keep `CLICKHOUSE_ALLOW_WRITE_ACCESS=true`, `ALLOW_DROP=false`.
- [ ] **C2. Apply schema against Cloud.** `python -m src.clickhouse.client` → "schema OK".
- [ ] **C3. Run live demo.** `python run_agent_demo.py tests/sample_feedback.eml` with
      Google billing enabled (Google credit live) → categorized notes + conflicts persisted
      + live analytics.
- [ ] **C4. Web smoke test.** `uvicorn src.web.app:app --port 8080` → upload sample,
      confirm checklist + analytics render against Cloud (not chDB).
- [ ] **C5. Capture video evidence** per `docs/demo_script.md` (live ClickHouse panel on screen).
- [ ] **C6. Deploy hosted URL.** `gcloud run deploy script-matrix-web --source . \
      --region us-central1 --allow-unauthenticated \
      --set-env-vars CLICKHOUSE_HOST=...,CLICKHOUSE_PORT=8443,CLICKHOUSE_USER=...,\
      CLICKHOUSE_PASSWORD=...,CLICKHOUSE_SECURE=true,CLICKHOUSE_ALLOW_WRITE_ACCESS=true,\
      CLICKHOUSE_MCP_AUTH_DISABLED=true`
- [ ] **C7. Submit Devpost form** with: public repo, hosted URL, video, ClickHouse track.

## VERIFICATION GATE (submission blocked until ALL green)
- [ ] Active ClickHouse Cloud instance reachable from code (C2 proves it).
- [ ] Demo video shows live ClickHouse analytics (not chDB).
- [ ] Hosted URL returns the app and persists to Cloud.
- [ ] Devpost form submitted before Sep 7 2:00 PM PT.

## KNOWN RESIDUAL RISK (downgraded — official ruling removes the hard blocker)
Per the host, judging relies on submitted artifacts (URL + video + repo), not an
indefinitely-live env. So a ClickHouse lapse after submission does NOT fail judging,
provided the demo video shows the full workflow. Remaining diligence: keep the hosted URL
live at submission; record the video while ClickHouse is live; ensure the video clearly
shows end-to-end operation. A4 (Mit) is now optional, not a blocker.
