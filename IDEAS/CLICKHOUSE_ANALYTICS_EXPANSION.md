# Feature Request — ClickHouse Analytics Expansion
# Script Notes-to-Outline Matrix Agent · Agentic Cinema Hackathon
# Status: approved (2026-08-12) · implements "maximize ClickHouse potential" ask
#
# Context
# -------
# Currently the analytics tab shows 3 charts driven by 3 queries (scene density,
# stakeholder disagreement, draft progress). ClickHouse is a full analytical columnar
# database and we are using maybe 20% of its capability. This document lists the
# expansion: more charts, cross-project aggregates, and decision-outcome probability
# proxies — all derivable from the EXISTING schema (notes_raw + notes_conflicts),
# no DDL change required for Phase 1.
#
# Guiding principle
# ------------------
# Every feature must be a real ClickHouse query (not client-side counting of a Python
# list). The point of the partner track is to show ClickHouse doing analytical work.
# If a metric can be computed in SQL, it belongs here.
#
# Phase 1 — new per-project analytics (this PR)
# ===============================================
#
## 1. Severity Heatmap by Scene (new chart)
#    What: a color-coded grid of scene_number × severity, cell = note count.
#    Why:  shows at a glance where the hot spots are — which scenes are bleeding
#          Criticals vs which are clean. Currently you only see total notes per scene.
#    SQL:  GROUP BY scene_number, severity. Render as a matrix of colored cells
#          (Chart.js matrix plugin, or a hand-built HTML grid with bg color by count).
#    Data: notes_raw only.
#
## 2. Category x Severity Matrix (new chart)
#    What: for each category (Pacing, Character, Dialogue, Structure, Logic, Other)
#          show the count of Minor/Major/Critical notes as a stacked bar or heatmap.
#    Why:  answers "which issue types are actually dangerous?" — Pacing may have the
#          most notes but Logic may have the most Criticals. Currently category and
#          severity are shown separately.
#    SQL:  GROUP BY category, severity.
#    Data: notes_raw only.
#
## 3. Stakeholder Influence Map (new chart)
#    What: bar chart of source_author (or source_type) by total notes AND by critical
#          notes — two series. Shows who is driving the feedback and who is flagging
#          the most severe issues.
#    Why:  "who's shouting loudest and most urgently" is a real revision-management
#          insight. Currently stakeholder_disagreement only shows source_type × category.
#    SQL:  GROUP BY source_author (or source_type), with countIf(severity='Critical').
#    Data: notes_raw only.
#
## 4. Conflict Type Breakdown (new chart)
#    What: pie or bar of conflict_type (Structural, Character Arc, Tone, Unspecified)
#          with unresolved count as a second series.
#    Why:  shows what KIND of disagreements are brewing. Structural conflicts are the
#          hardest to resolve; if they dominate, the revision is high-risk.
#    SQL:  GROUP BY conflict_type, with countIf(resolution_status='Unresolved').
#    Data: notes_conflicts only.
#
## 5. Conflict Aging / Unresolved Shelf-Life (new chart)
#    What: for unresolved conflicts, how long have they been sitting? Histogram of
#          hours_since_created for unresolved conflicts. (If created_at is populated.)
#    Why:  old unresolved conflicts are revision blockers. A 2-week-old unresolved
#          Structural conflict is a signal the draft is stuck.
#    SQL:  SELECT quantile(1) / avg of toInt32(now() - created_at) WHERE
#          resolution_status='Unresolved'. Also a bucketed histogram.
#    Data: notes_conflicts only. Note: created_at DEFAULT now() is in the schema;
#          the agent's persist_from_raw must pass it (verify it does).
#
## 6. Draft Progression Chart (existing query, new visualization)
#    What: line/area chart across draft_version: total_notes, conflict_count, critical_count
#          per draft. Shows whether revisions are reducing the problem.
#    Why:  currently draft_progress returns per-draft rollups but the UI doesn't chart
#          them as a progression. This is the "is the revision working?" view.
#    SQL:  reuses draft_progress + a new conflicts-per-draft query.
#    Data: notes_raw + notes_conflicts, GROUP BY draft_version.
#
## 7. Revision Risk Score (composite metric, new)
#    What: a 0-100 score per project/draft derived ENTIRELY in ClickHouse SQL:
#          risk = clamp(
#            40 * critical_ratio
#            + 30 * conflict_rate            -- conflicts / scenes_with_notes
#            + 20 * notes_per_scene_normalized  -- how crowded is the feedback?
#            + 10 * stakeholder_fragility     -- distinct reviewers with opposing views
#          )
#    Why:  the user asked for "probabilities of possible outcome of the decision."
#          This is a proxy: higher score = higher probability the revision will be
#          painful / stall. It is a transparent, auditable formula, not a black box.
#          Display as a gauge (Chart.js speedometer, or a colored badge: green < 35,
#          amber 35-65, red > 65).
#    SQL:  one aggregate query computing each component, then the arithmetic in the
#          query or in Python post-processing (either is fine; SQL is preferred to show
#          ClickHouse doing the work).
#
## 8. Expected Scenes to Revise (new metric)
#    What: count of scenes that have >= 1 note OR >= 1 conflict. This is the "how many
#          scenes will the writer actually touch?" estimate.
#    Why:  actionable — a writer can budget time by scene count. Currently you see the
#          density per scene but not the aggregate "affected scenes" count in the KPI
#          cards. (The draft_progress query already computes affected_scenes; surface it.)
#    SQL:  count(DISTINCT scene_number) WHERE note_count > 0 OR conflict_count > 0.
#
## 9. Stakeholder Alignment Score (new metric)
#    What: a ratio: (notes that are NOT part of a conflict) / (total notes). Or
#          inversely, conflict_rate = distinct_conflict_scenes / distinct_note_scenes.
#          Low alignment = many scenes have contradictory guidance.
#    Why:  "probability the decision will be contested" — if 40% of scenes have a
#          conflict, the revision decision for any given scene is a coin flip between
#          two stakeholders. This is the user's "outcome probability" ask, phrased as
#          a revision-management metric.
#    SQL:  one query: total distinct scenes with notes vs scenes with conflicts.
#
## 10. Cross-Project Benchmark Dashboard (new tab or section)
#     What: aggregate analytics ACROSS ALL projects currently in ClickHouse:
#       - Average notes per scene (all projects)
#       - Average conflict rate (all projects)
#       - Most common category (across all notes)
#       - Most common conflict type (across all conflicts)
#       - Average revision risk score
#       - Total notes ingested, total conflicts flagged, total projects
#       - Top N "highest risk" projects (by risk score) — a leaderboard
#     Why:  this is the real ClickHouse flex. A single-node analytical DB can scan all
#           projects' notes in milliseconds and produce benchmarks. This is the feature
#           that says "we're not just storing notes, we're analyzing a corpus." It is
#           also the most visually impressive for a demo: "here is what 10 scripts'
#           worth of revision data looks like."
#     SQL:  plain aggregate queries over notes_raw and notes_conflicts with no WHERE
#           clause (or WHERE project_id != ''). Runs against the whole database.
#     Rendering: a new tab "Cross-Project Benchmarks" or a section at the top of the
#           analytics tab. Charts: bar chart of risk scores by project, pie of global
#           category distribution, stat cards for the headline numbers.
#
## 11. Global Category Distribution (cross-project)
#     What: pie/doughnut of category counts across ALL projects — how often does each
#           issue type appear in the wild?
#     Why:  pairs with the cross-project dashboard. Shows the "shape of revision work"
#           across the corpus.
#     SQL:  SELECT category, count(*) FROM notes_raw GROUP BY category.
#
## 12. Global Conflict Type Distribution (cross-project)
#     What: bar of conflict_type counts across all conflicts.
#     Why:  shows what kinds of disagreements are most common across scripts.
#     SQL:  SELECT conflict_type, count(*) FROM notes_conflicts GROUP BY conflict_type.
#
# Phase 2 — schema expansion (future, NOT in this PR)
# =====================================================
# These would require new tables or columns and are out of scope for the immediate
# push. Documented here so we don't forget.
#
## A. revisions_applied table — track what the writer actually changed per draft
#    (scene_number, draft_version, change_description, changed_at). Then you can compute
#    real outcome probability: of the conflicts flagged in Draft 1, what fraction were
#    resolved by Draft 2? This turns the proxy risk score into a real predictive model.
#
## B. script_scene_index table — the full scene list (scene_number, scene_heading,
#    page_count) per script. Then "scenes with no feedback" becomes a real gap analysis
#    instead of "scenes we have notes for." Also enables per-page feedback density.
#
## C. resolution_history table — track conflict resolution_status changes over time
#    (resolved_at, resolved_by, method). Enables the conflict aging chart to show
#    time-to-resolution, not just time-open.
#
# Implementation notes
# =====================
# - All new queries go in src/analytics/queries.py, following the existing pattern:
#   a typed function per query + a bundle function that the web routes call.
# - New charts go in src/web/templates/index.html inside the existing "tab-analytics"
#   tab (add charts 1-7 there) plus a new "tab-benchmarks" tab (cross-project, items
#   10-12). Reuse the existing Chart.js CDN (chart.js 4.x) — do not add a new charting
#   library. For the heatmap (item 1), a hand-built HTML grid with inline bg colors is
#   simpler and more reliable than a matrix plugin; if a matrix plugin is already on the
#   page, use it.
# - The Revision Risk Score formula must be documented in-code (a comment with the
#   weights) so judges can see it is transparent and auditable.
# - Every new chart must have a test that feeds sample rows into chDB and asserts the
#   query returns the expected shape. See tests/test_clickhouse_suite_e.py for the
#   existing pattern.
# - The cross-project dashboard must NOT expose raw note text across projects (privacy).
#   Only aggregates (counts, ratios, category names) leave the project boundary.
# - Performance: cross-project aggregates scan the full notes_raw + notes_conflicts
#   tables. On a real ClickHouse Cloud instance with thousands of notes this is
#   milliseconds. On chDB with a small test dataset it is also fast. No special indexing
#   needed beyond the existing ORDER BY keys.
#
# Acceptance criteria (this PR)
# ==============================
# - [ ] 12 new analytics items implemented (items 1-12 above), all driven by ClickHouse
#       queries in src/analytics/queries.py.
# - [ ] index.html updated: existing tab-analytics tab shows items 1-9; new tab-benchmarks
#       tab shows items 10-12.
# - [ ] Revision Risk Score formula documented in-code and displayed as a colored badge
#       in the KPI card row.
# - [ ] New test file tests/test_analytics_expansion.py (or extend suite E) covering the
#       new queries against chDB with planted sample data.
# - [ ] All existing tests still pass.
# - [ ] README analytics section updated to mention the expanded panel.
