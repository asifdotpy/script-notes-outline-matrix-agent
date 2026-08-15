# Register agentic-cinema as a Hermes Project (idea-tracker profile) — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Register the existing `/home/asif1/agentic-cinema/` git repo as a managed Hermes project under the `idea-tracker` profile, so its tasks/status are tracked in the same profile that holds the ideas vault.

**Architecture:** `hermes project create` indexes a filesystem folder (with an optional primary git repo) as a Hermes project. The repo already exists, is public, pushed to GitHub, and has a clean `main` at commit `64b2a1d`. We only register it — no code changes. The action is profile-scoped: it must run under the `idea-tracker` profile (the current active profile).

**Tech Stack:** Hermes CLI `project` subcommand (profile-local state). No Python/library changes.

---

## Context / Assumptions

- Active profile: `idea-tracker` (confirmed by session context; `hermes project list` shows "No projects yet").
- Repo already at `/home/asif1/agentic-cinema/`, git root = same path, branch `main`, remote `https://github.com/asifdotpy/script-notes-outline-matrix-agent.git`.
- 25 tracked files; last commit `64b2a1d`.
- The ideas-vault (`~/ideas-vault`) is a SEPARATE repo and must NOT be touched.
- `hermes project create` flags (from `--help`):
  - positional `name` (human name) + optional `folders ...` (first = primary)
  - `--slug SLUG`, `--primary PATH`, `--description`, `--icon`, `--color`, `--board SLUG`, `--use`
- Creating a project is a mutating CLI action (writes profile state). Per plan mode, do NOT run it now — execute only after plan approval.

## Proposed approach

1. Create the project with a clear slug, the repo path as the primary folder, a one-line description, and set it active (`--use`).
2. Verify it appears in `hermes project list` and `hermes project show`.
3. Update the ideas-vault brief cross-reference so the tracker knows the build project is registered (doc-only, in the hackathon brief).

## Step-by-step plan

### Task 1: Create the Hermes project for agentic-cinema

**Objective:** Register `/home/asif1/agentic-cinema` as a managed project under the idea-tracker profile and make it the active project.

**Files:** (none changed in the repo; only Hermes profile state written)
- Profile project state: `~/.hermes/profiles/idea-tracker/projects/` (managed by Hermes)

**Step 1: Run the create command**

```bash
hermes project create "Script Notes-to-Outline Matrix Agent" \
  --slug agentic-cinema \
  --primary /home/asif1/agentic-cinema \
  --description "Agentic Cinema hackathon build (ClickHouse track): Gemini/ADK agent that ingests external PDF coverage + producer emails, flags conflicts, writes a Draft-2 checklist, persists to ClickHouse via mcp-clickhouse." \
  --use
```

Expected output: a confirmation line that the project was created (and set active). No error.

**Step 2: Verify it is registered and active**

```bash
hermes project list
```

Expected: a row named "Script Notes-to-Outline Matrix Agent" (slug `agentic-cinema`).

```bash
hermes project show
```

Expected: shows the project name, slug `agentic-cinema`, primary path `/home/asif1/agentic-cinema`, and (if Hermes surfaces it) the linked git remote.

**Step 3: Confirm no side effects on the repo or ideas-vault**

```bash
cd /home/asif1/agentic-cinema && git status --short
cd /home/asif1/ideas-vault && git status --short
```

Expected: both clean (no untracked/modified files from the project registration).

### Task 2: Cross-reference the project in the ideas-vault hackathon brief (doc-only)

**Objective:** Record in the research tracker that the build repo is now a managed Hermes project, so future sessions find it.

**Files:**
- Modify: `/home/asif1/ideas-vault/ideas/_hackathon/agentic-cinema-brief.md`

**Step 1: Append a project-registration note**

Add a short bullet under the build section:

```markdown
- Build repo registered as Hermes project `agentic-cinema` (idea-tracker profile) on 2026-08-06.
  Path: /home/asif1/agentic-cinema — `hermes project show` to inspect; tasks tracked there.
```

**Step 2: Commit the brief update**

```bash
cd /home/asif1/ideas-vault && git add ideas/_hackathon/agentic-cinema-brief.md && git commit -m "idea: agentic-cinema build repo registered as Hermes project"
```

Expected: clean commit, single file.

## Files likely to change

- `~/.hermes/profiles/idea-tracker/projects/*` (Hermes-managed — created by the CLI, not hand-edited)
- `/home/asif1/ideas-vault/ideas/_hackathon/agentic-cinema-brief.md` (doc-only append)

No source files in `/home/asif1/agentic-cinema` change.

## Tests / validation

- `hermes project list` shows the new project.
- `hermes project show` reflects slug `agentic-cinema` + primary path.
- `git status` clean in both `agentic-cinema` and `ideas-vault`.

## Risks / tradeoffs / open questions

- **Profile scope:** `hermes project create` writes to the ACTIVE profile. Confirm the shell is on `idea-tracker` before running (the session is). If not, switch first.
- **`--use` side effect:** makes this the active project, which may change default `hermes project show` context for later commands. That is the intended outcome here.
- **`folders` vs `--primary`:** passing the repo path as a positional folder AND `--primary` is redundant; the plan uses `--primary` explicitly for clarity. If Hermes rejects both, drop the positional and keep `--primary`.
- **Existing projects:** `hermes project list` currently reports "No projects yet", so the slug `agentic-cinema` is free — no collision risk.
- **Open build next-steps NOT in scope here** (track later as project tasks): GitHub Actions CI, ClickHouse Cloud trial start (~Sep 5), GC $100 coupon redemption, re-run live Gemini demo after quota reset. These can become Hermes project tasks once the project exists.

## Execution handoff

Plan complete. Ready to execute — the only mutating action is the single `hermes project create` command (Task 1) plus a doc commit in ideas-vault (Task 2). Shall I proceed?
