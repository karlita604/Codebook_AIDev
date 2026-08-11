# Project Status — 2026-08-11 (updated: in-house Phase A + Phase B both built)

*Companion to `ProjectUpdate.md` (the raw chronological build log — kept
append-only, dated entries). This doc is a clean, current snapshot,
structured for talking through out loud. Full methodology: `Longitudinal.md`.
Full findings with tables and figures: `Results.md`'s "First real analysis"
section and the interactive dashboard linked there — read that section's
banner first, the numbers are an N=4 pilot, not final.*

## The one-paragraph version

We're measuring whether repo structural health (design/implementation
smells, OO metrics) and PR-level process changes when AI coding agents
start contributing — using an interrupted time series, not a naive
before/after, so ordinary codebase drift doesn't get mistaken for an agent
effect. **A first analysis ran on a 4-repo pilot** (3 Python via DPy, 1 C#
via Designite): segmented regression on the pre-registered primary metrics,
composition-shift and process-metric tests. Headline: **no consistent
cross-repo direction** — real, statistically significant changes show up
almost everywhere, but they point different ways in different repos, and
the split doesn't track language. This is N=4 — descriptive of these
repos, not a general claim about "AI agents," and explicitly preliminary.
`dotnet/aspire` is dropped from the pilot entirely (both tracks), leaving
3 Python + 1 C#, not the original 3+2. **The project has since moved into
Phase 2**: expanding to a 20-repo minimum. The Designite branch
(`designite-sln-support`) is now merged into `main` — its output no longer
needs to be read cross-checkout. Phase 2's new repos were collected raw
(snapshots + PR samples) without running them through DPy/Designite,
pending an in-house metrics tool (see `Writing/InHouseTooling.md`) that
won't hit the trial-license LOC caps that made the pilot's tool runtime
expensive. **Update, 2026-08-10: both of those are now further along.**
Phase 2's raw collection is essentially done — repo selection, PR sampling,
and snapshot manifest/materialization all landed at a 21-repo scale (20/21
repos materialized; only `julep-ai/julep` still pending) — leaving
structural metrics (Phase 1d) as the only real remaining gap, which is
exactly what the in-house tool targets. **Update, 2026-08-11: both Phase A
(Python OO-metrics, stdlib `ast`) and Phase B (C# via Roslyn, syntax-only —
no `.sln`/`MSBuildWorkspace` load) are now built and validated against the
real pilot's DPy/Designite output** — see section 6 below. Phase B's
syntax-only approach turned out to unblock both `dotnet/aspire` (excluded
from the pilot entirely — Designite can't load its project graph) and
Dock's post-`.slnx`-migration months (Designite can't read `.slnx`) as a
side effect of not needing a project graph at all. Visualization (Phase C)
and the RQ3 entity tracker (Phase D) are scoped but not yet built (see
`Writing/InHouseTooling.md` and `Writing/RQ3_CodeTracking.md`'s
design-decisions sections).

## Where each piece stands

| Piece | Status |
|---|---|
| Phase 0 — candidate repo filtering | Done, iterating in background |
| Phase 1a — pilot selection & intervention dates | Done |
| Phase 1c — snapshot manifest (which commit per grid point) | Done — 480 rows |
| Phase 1e — snapshot materialization (source on disk) | Done — 399/401 unique commits |
| Phase 1d — structural metrics (DPy + Designite) | **Done for the 4-repo pilot** — 351 pooled rows. Deferred for Phase 2's new repos (see in-house tool row below) |
| Phase 1b — PR-level process metrics | **Done for the pilot, with one exclusion. Done for Phase 2's new repos too** — 4990-row PR sample landed 2026-08-04 |
| First analysis (segmented regression, composition, process) | **Done for the pilot — see `Results.md`.** Preliminary, N=4, not re-run since |
| Designite branch → `main` merge | **Done 2026-08-04** — Dock's Designite output now lives in this checkout, no cross-checkout reads needed |
| Phase 2 — expand to 20-repo minimum | **Raw collection essentially done** (2026-08-10) — 21-repo manifest, 20/21 repos materialized (`julep-ai/julep` pending); structural-metric analysis is the one remaining piece |
| In-house tool, Phase A (Python) + Phase B (C#/Roslyn) | **Both built and validated 2026-08-11** — see section 6 below. Phase C (viz)/D (RQ3 entity tracker) not started |

## 1. The pilot (now 4 repos, not 5)

| repo | language | agent PRs | intervention date | structural data | process (Track B) data |
|---|---|---|---|---|---|
| crewAIInc/crewAI | Python | 327 | 2024-12-27 | 72/74 rows | full |
| airbytehq/airbyte | Python | 218 | 2025-01-21 | 96/96 rows | full |
| mlflow/mlflow | Python | 91 | 2025-05-21 | 96/96 rows | full |
| wieslawsoltes/Dock | C# | 309 | 2025-06-25 | 87/96 rows (post-period thin, below) | full |
| ~~dotnet/aspire~~ | ~~C#~~ | — | — | **dropped** | **dropped** |

`dotnet/aspire` is out of the pilot entirely now, not just Track B as of
07-28. Track A (structural) hit its own, separate blocker: Designite can't
open any of aspire's history cleanly — early commits fail via its Arcade
bootstrap (every project reports 0 source files without a private-feed
restore), recent commits need a preview .NET SDK not installed. No clean
middle band was found. See `DESIGNITE_TASK.md` (on the
`designite-sln-support` branch) for the full investigation. **This pilot is
3 Python + 1 C#, not the original 3+2** — an open methodology question, not
resolved (§ Open decisions).

## 2. Structural metrics — done

| repo | tool | rows ok | notes |
|---|---|---|---|
| crewAIInc/crewAI | DPy | 72/74 | 2 permanent gaps — NTFS-illegal filename in a test fixture, Windows-only limitation |
| airbytehq/airbyte | DPy | 96/96 | complete |
| mlflow/mlflow | DPy | 96/96 | complete |
| wieslawsoltes/Dock | Designite | 87/96 | 9 fail — Dock migrated `Dock.sln`→`Dock.slnx` on 2025-12-25, unsupported by the installed Designite build |

**351 pooled rows** across both tracks (A1 fixed-calendar, A2 event-window),
consolidated in `results/analysis/07-29-pooled-structural-metrics.csv`. DPy
ran in the main checkout; Designite was built and run on a separate branch
(`designite-sln-support`, worktree `Codebook_AIDev-designite`) to avoid
touching the multi-day DPy background job — **merged into `main` on
2026-08-04**, so Dock's data now lives alongside the Python output in one
checkout (no more cross-checkout reads).

**Dock's post-intervention data is thin** — only 6 of a possible ~19 A1
points, because the `.slnx` gap above starts just 6 months after Dock's own
intervention date (2025-06-25). Its slope estimates use those 6 points same
as everything else; its level-change comparisons rest on less data than the
three Python repos. Recovering the rest needs a newer Designite build with
`.slnx` support, or a `.slnx`→`.sln` conversion step — neither started.

**Schema note that changed the plan**: Designite's output was written to
pool onto the *same* canonical column names DPy already uses. The
cross-language adapter step earlier planning assumed would be needed
(`Results.md`'s 07-28 "Assumption 1") **wasn't** — the two CSVs concatenate
directly.

## 3. PR-level process metrics — done, one exclusion

212/265 query units ok (all 53 failures on `dotnet/aspire` — Microsoft's
`dotnet` org blocks fine-grained PATs at the org-policy level, confirmed
directly, unrelated to any code issue). `wieslawsoltes/Dock` is the sole C#
repo for Track B, same imbalance as Track A now. Captured: PR identity,
timestamps, comment counts. **Still not captured**: diff size, deeper
review stats — needs a per-PR follow-up call, not yet built.

## 4. First analysis — done (2026-07-29)

Ran the pre-registered tests from `Longitudinal.md` §9 for the first time.
Full tables and an interactive dashboard (hover for exact values, every
chart has a data table) are in `Results.md`'s "First real analysis" section:
https://claude.ai/code/artifact/5ae706c9-eb9a-458a-9880-76be980d9164

**What it found, in brief:**
- **Segmented regression (RQ1)**: design-smell density shows a
  statistically significant *slope* change post-intervention in all 4
  repos — but 2 trend worse (airbyte, crewAI) and 2 trend better (mlflow,
  Dock). That split is *within* the Python repos, not a Python-vs-C#
  divide. No repo shows a significant *level* jump on this metric.
- **Implementation-smell density**: airbyte and mlflow both show a real
  drop right at the intervention; Dock shows the opposite — the sharpest
  upward slope in the whole table.
- **Composition (RQ2)**: design smells' share of all smells shifts
  significantly in all 4 repos (p<.01) — shrinking in 3 (airbyte, mlflow,
  Dock), growing in crewAI.
- **Process (RQ3)**: crewAI is the only repo with a significant
  merge-latency change (a large drop); airbyte and crewAI both show
  significantly more review comments per PR post-intervention; mlflow shows
  no process change on either metric.
- **Cross-language (RQ4)**: Dock (the one C# repo) doesn't stand apart from
  the Python repos on any metric — but n=1 C# repo barely tests this.
- **Dosage (RQ5)**: agent-PR count doesn't predict effect direction or size
  across the 4 repos — if anything runs backwards. Inconclusive at N=4, kept
  as a covariate for when there's enough repos to regress properly.

**The honest read**: real, non-random signal is showing up almost
everywhere, but it's repo-specific, not a uniform "agents help" or "agents
hurt" story, and doesn't cleanly split by language either. That's a
legitimate finding on its own, not a failure to find one — but it's N=4,
unadjusted for the 12 significance tests RQ1 alone ran, with no matched
non-adopting comparison arm yet. Not paper-ready; a real first look.

## 5. Phase 2 — expanding to 20 repos (raw collection essentially done, 2026-08-10)

The pilot's 4 usable repos were well short of the thesis's 20-repo minimum.
Rather than re-running the pilot's DPy/Designite pipeline at ~4-5x the
scale (the pilot's trial-license LOC caps already made mlflow alone cost
~29 hours of chunked tool runtime — see `ProjectUpdate.md`'s 2026-07-27 and
2026-08-04 entries), Phase 2 collected raw data for the new repos using the
same already-parameterized (`--pilot-size`) Phase 1a/1b/1c/1e pipeline —
repo/PR selection, PR sampling, snapshot manifest, materialized source
trees — but **deferred Phase 1d (DPy/Designite execution) entirely**.

**Status as of 2026-08-10, checked directly against what's on disk (not
just the plan above):**

| Piece | Real numbers |
|---|---|
| Repo selection | `results/repos/08-04-repo-summary-235.csv` — 235 candidate repos considered |
| Snapshot manifest (Phase 1c) | `results/snapshots/08-04-repo-snapshot-manifest-2016.csv` — 2016 grid rows, 1673 resolved to a real `commit_sha`, **21 unique repos** (up from the pilot's 5/480) |
| Snapshot materialization (Phase 1e) | **20 of 21 manifest repos have real source trees in `data/snapshots/`** — only `julep-ai/julep` doesn't yet |
| PR sampling (Phase 1b) | `results/pr_samples/08-04-pr-sample-4990.csv` — 4990 PR rows (up from the pilot's 265) |
| Structural metrics (Phase 1d) | **Still the one deferred piece** — no DPy/Designite output exists for any of the ~16 new repos beyond the original 4-repo pilot. This is exactly what the in-house tool (section 6) targets, and it's now the *only* remaining piece of Phase 2, not one of several. |

The new repos' raw materialized snapshots sit ready for the in-house
metrics tool instead of being forced through the same LOC-cap chunking that
made the pilot expensive. Full repo list and any remaining collection
gaps (starting with `julep-ai/julep`'s materialization): `ProjectUpdate.md`'s
2026-08-04 and 2026-08-10 entries.

## 6. In-house metrics tool — Phase A and Phase B built and validated (2026-08-11)

`Writing/InHouseTooling.md` and `Writing/RQ3_CodeTracking.md` moved from
brainstorm to a real build this session. Design decisions (scope, language
sequencing, correlation/visualization conventions, RQ3 approach) are logged
in both docs' "Design decisions (2026-08-05)" sections — not repeated here.
Full build plan: `C:\Users\kvrlv\.claude\plans\woolly-jumping-acorn.md`.

**What's built** (`src/inhouse/`): a from-scratch Python AST engine
(`ast_common.py`, `py_metrics.py`) computing the same OO-metric family DPy
reports — LOC, WMC, NOM/NOPM/NOF/NOPF, LCOM, DIT, Fan-In/Fan-Out, per-method
cyclomatic complexity and param count — with **no LOC cap**, since it's our
own code, not a licensed trial tool. `pool_inhouse_metrics.py` is the CLI
orchestrator (same resumable/error-logged shape as `long_analysis.py`);
`validate_against_pilot.py` joins its output against the real pilot's DPy
ground truth (`07-29-pooled-structural-metrics.csv`) and reports per-metric
agreement.

**Validated two ways:**
1. **Hand-checked synthetic fixture** — a small `.py` file with
   pre-computed expected CC/WMC/LOC/LCOM/DIT/Fan-In/Fan-Out values. Caught
   and fixed a real bug in the process: `self.method()` calls were
   initially being counted as field accesses (identical `ast.Attribute`
   shape to `self.field`), inflating NOF and polluting LCOM. Fixed by
   excluding a class's own method names from its field-access scan
   (`ast_common.self_attribute_names`'s `exclude` parameter) — a documented
   remaining blind spot for *inherited* method calls (a subclass calling a
   base-class method still isn't recognized as a call, since there's no
   cross-class method-name resolution) is called out directly in that
   function's docstring, not silently left as a gap.
2. **Real run against the pilot's materialized snapshots**, joined against
   DPy's actual output on `(repo_id, track, target_date, commit_sha)`.
   Speed: ~1 second per snapshot (crewAI's first 5 snapshots: 4.0s total),
   vs. DPy's chunked multi-second-to-minutes-per-chunk runtime at LOC-cap
   scale. Full validation numbers (all 3 pilot Python repos, not just the
   5-row smoke test): see `Results.md`'s in-house-tool section.

**A finding worth flagging beyond "the tool works": DPy's own pilot output
for airbyte may itself be undercounted, not just differently-conventioned.**
Validated against all 264 pilot Python rows (100% join rate — airbyte and
mlflow runs finished at 96/96 real rows each, no errors, after this was
first drafted). Airbyte's in-house/DPy LOC ratio (2.41x) is far larger than
crewAI's (1.54x) or mlflow's (1.71x). A direct `wc -l` cross-check on one
airbyte
commit confirms the in-house figure (352,778 lines) matches the snapshot's
real physical line count almost exactly, while DPy's own reported figure
for that identical commit (125,111) does not — that snapshot needed 411
separate DPy chunks under the Trial LOC cap (airbyte's repo-wide average:
~374 chunks/snapshot, vs. crewAI's ~30), consistent with chunked DPy runs
silently losing coverage as chunk count grows. **Practical implication**:
airbyte's absolute LOC/class-count figures in this pilot's existing DPy
output (sections 1-4 above, and the pilot's first analysis) may be
undercounts specifically for that reason — worth keeping in mind when
citing them, though the *within-repo before/after* comparisons those
sections actually run are less affected (both pre- and post-intervention
snapshots would be similarly chunked). Full analysis: `Results.md`'s
in-house-tool validation section.

### Phase B — C# via Roslyn, built and validated same day

Followed the same shape as Phase A, translated to C#: `src/inhouse/roslyn_tool/`
is a small .NET console app (`Microsoft.CodeAnalysis.CSharp`,
`CSharpSyntaxTree.ParseText` — **no `.sln`/`MSBuildWorkspace` load, ever**),
invoked via subprocess from `src/inhouse/csharp_metrics.py` the same way
`run_designite()` already shells out to `DesigniteConsole` in
`long_analysis.py`. `pool_inhouse_metrics.py` now routes each manifest row
to the right analyzer by `language` instead of filtering to Python only.

**Validated the same two ways as Phase A:**
1. **Hand-checked synthetic fixture** (same `Animal`/`Dog` shape as
   Phase A's, for a direct side-by-side). Caught a real gap before it
   became a silent undercount: C# constructors are a *different* Roslyn
   node type (`ConstructorDeclarationSyntax`), not a subtype of
   `MethodDeclarationSyntax` — missing this would have dropped every
   constructor from NOM/WMC and, worse, from LCOM's field-access scan
   (constructors are often the one place that touches every field, exactly
   the case that most affects LCOM). Fixed by extracting
   `BaseMethodDeclarationSyntax` (covers methods, constructors,
   destructors, operators) throughout. Every hand-computed value matched
   after the fix — including confirmation that C#'s real field-declaration
   syntax sidesteps Phase A's Python-specific blind spot entirely: the
   same fixture's `Dog` class gets `NOF=0` in C# (correct), not the `NOF=1`
   the Python engine produces from mis-reading `self.speak()` as a field
   access, because the C# side reads real declared fields instead of
   inferring them from usage.
2. **Real run against Dock's and `dotnet/aspire`'s materialized
   snapshots**, joined against Designite's actual output. **87/87
   Designite-successful Dock rows joined, and agreement is strong**:
   `total_loc` r=0.999, `n_classes` r=0.998, `n_methods` r=0.997,
   `cyclomatic_complexity_p90` r=0.546 (weaker, same category of
   cross-implementation CC-counting divergence Phase A's validation
   already showed on the Python side). Class/method counts run a
   *negative* 11-15% vs. Designite — the opposite direction from Phase A's
   Python offset — consistent with a documented Designite quirk
   (`DESIGNITE_TASK.md`'s "known gaps"): multi-targeted projects (built for
   more than one target framework) get a full duplicate class/method set
   per framework, undeduplicated, so Designite's own counts run inflated,
   not ours short.

**Two real, unplanned wins fell out of being syntax-only:**
- **`dotnet/aspire` analyzed successfully — 75/75 rows, `ok`.** This is the
  repo excluded from the pilot entirely because `MSBuildWorkspace` can't
  evaluate its project graph without replicating Arcade's bootstrap
  (`DESIGNITE_TASK.md` §5). Phase B never loads a project graph at all, so
  that blocker doesn't apply — this is the first real structural data this
  project has ever had for `dotnet/aspire`.
- **Dock's post-`.slnx`-migration period is no longer censored.** Designite
  fails on 9/96 Dock rows because it can't read `.slnx` (Dock migrated
  2025-12-25, six months after its own intervention date) — flagged
  repeatedly as a real limitation on Dock's post-intervention data
  (`Results.md`'s caveats). Phase B doesn't touch `.sln`/`.slnx` either, so
  **all 96/96 Dock rows succeeded**, including the previously-unreadable
  post-migration months.

**A real bug this surfaced, unrelated to Phase B's own code**: joining
against Designite's ground truth using the *latest* snapshot manifest
(`08-04-repo-snapshot-manifest-2016.csv`) initially returned only 2/87
matches for Dock — not a validation failure, a **manifest regression**.
That manifest resolves 94 of Dock's 96 grid points to just 2 distinct
commits (mostly one from January 2022), while the older manifest
(`07-21-repo-snapshot-manifest-480.csv`) correctly resolves 64 distinct
commits, all genuinely materialized on disk. `data/repo_cache/wieslawsoltes__Dock`
is currently stale, capped at that same January 2022 commit — the newer
manifest's "closest commit at or before this date" resolution has nothing
newer to find, so it keeps returning the same one. **Every other repo in
both manifest versions kept its full commit diversity** (airbyte 95→95,
crewAI 71→71, mlflow 96→96, `dotnet/aspire` 75→75) — this is Dock-specific,
not systemic. Worked around for this validation run by pointing
`pool_inhouse_metrics.py --manifest` at the older manifest explicitly; the
underlying clone staleness is unresolved and needs its own fix (a
`git fetch`/backfill re-run for Dock specifically) before the *latest*
manifest can be trusted for Dock again — see "What's still open" below.

**Not yet built** (scoped, not started): Phase C (time-series + pre/post
correlation-matrix visualization), Phase D (RQ3 entity/snippet lifetime
tracker — "how many times was this method edited," "did it get renamed,"
etc.). "How many rounds of *review*" specifically (as opposed to edit
count) stays blocked on Track B's still-missing deeper PR-diff stats
regardless of Phase D's own progress — see item 4 below, unchanged since
2026-07-21.

## 7. What's still open

Ranked by what would change the analysis most:

1. **`dotnet/aspire`'s exclusion / the language imbalance — resolved for
   the in-house tool, still open for the pilot's published Designite
   numbers.** Phase B gives real structural data for `dotnet/aspire`
   (75/75 rows) and doesn't need the language-imbalance workaround the
   original Designite-based pilot needed. The *pilot's first analysis*
   (section 4 above) still only has Designite/DPy data and still excludes
   aspire — re-running that analysis on in-house data, or deciding whether
   to formally supersede the Designite numbers, is a methodology call, not
   done automatically by Phase B existing.
2. **Dock's `.slnx` gap — resolved for the in-house tool, still open for
   Designite's own numbers.** Phase B reads all 96/96 Dock rows including
   the post-migration months; Designite's real output (used in the pilot's
   published first analysis) still only has 87/96. Same "which numbers are
   now authoritative" methodology call as item 1.
3. **The Dock manifest commit-resolution bug** (found validating Phase B,
   section 6) — `data/repo_cache/wieslawsoltes__Dock` is stale, capped at
   a January 2022 commit, so the *latest* snapshot manifest
   (`08-04-repo-snapshot-manifest-2016.csv`) resolves 94/96 of Dock's grid
   points to just 2 distinct commits instead of 64. Needs a fresh
   `git fetch`/backfill for Dock's clone specifically (confirmed
   repo-specific, not systemic) before the latest manifest can be trusted
   for Dock again.
4. **The in-house metrics tool, Python + C# are done; viz/RQ3 aren't.**
   Phase A and Phase B (section 6) are both built and validated. Still
   needed before Phase 2's raw-collected repos are *fully* analyzable:
   Phase C (the actual time-series/correlation figures) and Phase D (RQ3
   entity tracking). Also: `julep-ai/julep` still needs Phase 1e
   materialization before either analyzer can run against it.
5. **Track B's deeper PR stats** (diff size, review detail) — needed to
   extend RQ3 beyond timestamps/comments, and specifically blocks any
   "how many rounds of review" question the RQ3 entity tracker (Phase D)
   will eventually want to answer — "how many times edited" doesn't need
   this (commit history alone answers it), but "how many review rounds"
   does. Unchanged since 2026-07-21 — still not built.
6. **Multiple-comparison correction + a matched non-adopting comparison
   arm** — needed before any of this is a defensible general claim, not
   just a per-repo descriptive result.

## Where things live

- Methodology & full rationale: `writing/Longitudinal.md`
- **Findings, tables, and the dashboard link: `writing/Results.md`**
  ("First real analysis — pilot results" section — preliminary, read its
  banner first)
- Raw chronological build log: `writing/ProjectUpdate.md`
- Designite decision log: `DESIGNITE_TASK.md` (now on `main`)
- In-house tooling plan/decisions: `Writing/InHouseTooling.md`
- RQ3 code-tracking plan/decisions: `Writing/RQ3_CodeTracking.md`
- In-house tool build plan: `C:\Users\kvrlv\.claude\plans\woolly-jumping-acorn.md`
- In-house tool code: `src/inhouse/` — Python (Phase A): `ast_common.py`,
  `py_metrics.py`; C# (Phase B): `roslyn_tool/` (.NET console project),
  `csharp_metrics.py` (subprocess glue); shared: `pool_inhouse_metrics.py`
  (orchestrator), `validate_against_pilot.py`
- In-house tool output: `results/analysis/08-10-inhouse-metrics-python-*.csv`
  (Phase A, pilot validation runs), `results/analysis/08-11-inhouse-metrics-{Dock,aspire}-*.csv`
  (Phase B)
- In-house vs. DPy/Designite agreement report: `results/analysis/08-11-inhouse-validation-report.csv`
- Pooled structural data (pilot only): `results/analysis/07-29-pooled-structural-metrics.csv`
- Regression / composition / process output: `results/analysis/07-29-{segmented-regression-A1,rq2-composition,rq3-process}.csv`
- PR samples (pilot): `results/pr_samples/07-28-pr-sample-265.csv`; **Phase 2 (21-repo)**: `results/pr_samples/08-04-pr-sample-4990.csv`
- Snapshot manifest / materialized source: pilot `results/snapshots/07-21-repo-snapshot-manifest-480.csv`; **Phase 2 (21-repo)**: `results/snapshots/08-04-repo-snapshot-manifest-2016.csv`, `data/snapshots/`
