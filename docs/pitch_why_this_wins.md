# Why This Wins — Hackathon Pitch Section

> Use in the Devpost submission and the 3-minute demo video script.

**Why This Wins:**
Screenwriting development suffers from a fundamental workflow disconnect: feedback arrives as
fragmented PDFs, producer emails, and raw notes, while writers draft in isolated script editors
like Final Draft. Rather than attempting an impossible native plugin inside closed desktop
software, **Script Notes-to-Outline Matrix Agent** acts as a **Development Middleware Hub**.
Powered by **Google ADK + Gemini** for multimodal parsing and complex narrative reasoning, and
**ClickHouse** for ultra-fast *relational analytical aggregation* over multi-document note
matrices, the agent ingests raw `.pdf` coverage and `.eml` feedback, auto-categorizes notes by
scene, flags contradictory producer/agent feedback, and outputs an actionable Draft-2 revision
checklist — with seamless, open-format export back into `.fdx` XML for standard screenwriting
tools.

## Honest scope notes (for the team, not the public deck)
- ClickHouse is used for **relational aggregation** (category breakdowns, conflict ratios,
  scene-by-scene note density) — NOT vector search. Do not claim vector indexing; ClickHouse is
  not a vector DB. Technical judges (ClickHouse/Google engineers) will catch this.
- `.fdx` export is **format interchange** (write a .fdx with injected scene notes), NOT a live
  in-editor plugin. Final Draft has no public plugin API.
- Web app + Gemini/ADK + ClickHouse analytics are built and verified. `.fdx` exporter is a
  build task (see kanban), not yet shipped.

## Demo video checklist
1. Upload 2 messy coverage PDFs + 1 producer `.eml` email.
2. Watch Gemini parse and ClickHouse aggregate notes into the Matrix Dashboard.
3. Highlight a Flagged Conflict (e.g. Exec A vs Exec B on Scene 14).
4. Click "Generate Draft-2 Checklist & Export to FDX", open the exported script, show notes
   embedded where the writer needs them.
