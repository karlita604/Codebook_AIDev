# Timeline

Dated milestones only — headline outcomes, not the debugging narrative. Full
detail (bugs, blockers, dead ends, exact numbers) lives in
`ProjectUpdate.md`'s matching dated entry; this doc just makes "what
happened, in order" a 30-second read. Phase/tool names follow `PHASES.md`'s
current terms even where `ProjectUpdate.md`'s own entries use the older
"Phase A/B" labels (that file is a verbatim historical record, not rewritten).

| Date | Milestone |
|---|---|
| 2026-07-21 | Methodology designed (`Longitudinal.md`, interrupted time series, A1/A2/B1/B2 tracks). Phase 1a done: 5-repo pilot selected (crewAI, airbyte, mlflow, Dock, aspire). Phase 1c done: 480-row snapshot manifest, 5 repos cloned. Phase 1e done: 399/401 unique commits materialized. Phase 1d built but blocked — DPy/Designite not yet installed. |
| 2026-07-27 | DPy + Designite installed. Two new blockers found: DPy's Trial license caps CSV export at <10,000 LOC/invocation; Designite requires a real `.sln`, which materialized snapshots didn't have yet. Chunking wrapper built for DPy; cost measured at ~29 hours of DPy runtime for `mlflow` alone. Decision: run the full manifest as a multi-day background job anyway; pipeline made crash-resilient (incremental writes, resumable, chunk cleanup). |
| 2026-07-28 | DPy background run hit and recovered from: a silent-death/resume bug, then a Windows Smart App Control incident that blocked `DPy.exe` outright (user disabled SAC directly). Parallelized to 3 workers. Separately: Track B1/B2 PR sampling completed, 212/265 query units ok — every failure was `dotnet/aspire` (Microsoft's org blocks fine-grained PATs). Decision: Dock becomes the sole C# repo for Track B. |
| 2026-07-29 | DPy run finished: 264 unique ok rows (crewAI 72/74, airbyte 96/96, mlflow 96/96). In parallel, on the `designite-sln-support` branch: Designite unblocked, Dock gets real structural data (87/96 rows); `dotnet/aspire` dropped from the C# arm entirely (no clean commit range works). **First real analysis run** — segmented regression (RQ1), composition shift (RQ2), process metrics (RQ3) — see `Results.md`, dashboard linked there. N=4 pilot, explicitly preliminary. |
| 2026-08-04 | `designite-sln-support` merged into `main` — Dock's data and the pilot's Python data now live in one checkout. **Phase 2 kickoff**: decision to collect raw snapshots/PR samples for a 20-repo minimum using the existing pipeline, but *defer* Phase 1d (DPy/Designite) for the new repos — the trial-license LOC caps don't scale. `InHouseTooling.md` and `RQ3_CodeTracking.md` added as brainstorm docs, the trigger for building an in-house replacement. |
| 2026-08-10 | **Phase 2 raw collection essentially done**: 21-repo manifest (1673/2016 grid points resolved), 4990-row PR sample, 20/21 repos materialized (`julep-ai/julep` pending). **Tool-Py built and validated** (Python OO metrics, stdlib `ast`, no LOC cap) — validated against the pilot's real DPy output; surfaced a finding that DPy's own airbyte numbers look undercounted (chunking artifact, not a convention difference). |
| 2026-08-11 | **Tool-CS built and validated** (C# via Roslyn, syntax-only — no `.sln`/`MSBuildWorkspace` load). Two unplanned wins: `dotnet/aspire` gets real structural data for the first time ever (75/75 rows), and Dock's post-`.slnx`-migration months are no longer censored (96/96 vs. Designite's 87/96). Also found: Dock's local `repo_cache` clone is stale, so the *latest* snapshot manifest under-resolves Dock's commit diversity — worked around for this validation, not yet fixed. |

## What's next (not yet on this timeline)

Per `ProjectStatus.md` §7: Tool-Viz (time-series/correlation figures) and
Tool-RQ3 (entity lifetime tracker) aren't built; the pilot's first analysis
hasn't been re-run against the now-available in-house Dock/aspire data;
Dock's stale clone isn't fixed; Track B's deeper PR-diff stats aren't built;
no multiple-comparison correction or matched non-adopting comparison arm
exists yet. This is the honest "still open" list, not a promise of order.
