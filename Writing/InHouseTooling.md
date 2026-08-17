# In-house metrics tooling — brainstorm & comparison plan

**Status: brainstorm / planning, 2026-08-04. Nothing here is built yet.**
Written alongside the Phase 2 kickoff (`ProjectUpdate.md`'s 2026-08-04
entry) — the immediate trigger for writing this now is that Phase 2's ~16
new repos are being collected *without* running them through DPy/Designite,
specifically because this document's premise (that those tools' cost model
doesn't scale) is why that call was made.

## Why consider this at all

DPy and Designite (designite-tools.com) are the two tools this study uses
for structural/OO metrics and code smells — DPy for Python, Designite for
C#. Both worked, and both produced real, usable pilot data (see
`Results.md`, `DESIGNITE_TASK.md`). But three things about them are a real
constraint on scaling past a small pilot:

1. **Trial-license LOC caps force chunking, and chunking is expensive.**
   DPy's Trial cap is <10,000 LOC per invocation (confirmed empirically,
   `ProjectUpdate.md` 2026-07-27); Designite's is <50,000 LOC (stated
   directly by the tool). Every pilot repo is far over that, so
   `long_analysis.py` splits each snapshot into sub-cap chunks and runs the
   tool once per chunk. Measured cost: **one `mlflow` snapshot alone took
   304 chunks × ~3.4s ≈ 29 hours of DPy runtime**, and that's one snapshot
   out of dozens per repo. This is the direct cause of the multi-day
   background jobs and the Windows Smart App Control incident logged in
   `ProjectUpdate.md`.
2. **Closed smell catalogs limit reproducibility.** Neither tool documents
   its exact smell-detection heuristics publicly — `parse_tool_output()`'s
   schema had to be *confirmed empirically* against real output rather than
   read from documentation (see its docstring in `long_analysis.py`). For a
   dataset meant to be published, that's a real limitation: readers can't
   independently verify what "design smell" means without owning a license.
3. **Cost, at real Phase-2/Phase-3 scale.** Trial licenses are free but
   capped; removing the cap needs a paid license (DPy Professional,
   Designite's paid tier) per seat/machine, which doesn't obviously get
   cheaper as the repo count grows into the dozens.

None of this means DPy/Designite were a bad choice for the pilot — they
gave real, validated numbers fast, which is exactly what a pilot needs. The
question is what's worth building in-house *now that the pilot has proven
the study design works*, ahead of a much larger Phase 2/3 sample.

## What's actually being measured today (ground truth for comparison)

Pulled directly from `parse_tool_output()`'s confirmed schema in
`long_analysis.py` (both tools' output was verified against real runs, not
guessed):

| Category | DPy (Python) | Designite (C#) | Replicable in-house? |
|---|---|---|---|
| Size | `LOC` (class/module) | `LOC` (class) | **Easy** — line counting, same caveats either tool already has (both undercount vs. their own top-line totals by not attributing boilerplate lines to a class) |
| Class-level OO metrics | `WMC`, `NOM`, `NOPM`, `NOF`, `NOPF`, `LCOM`, `Fan-In`, `Fan-Out`, `DIT` | same set, plus `NC`, `NOP` | **Easy–Medium** — all are standard, well-published metrics (Chidamber & Kemerer's suite, mostly) computable from an AST/symbol table. Fan-In/Fan-Out and DIT need whole-project type resolution, not just per-file parsing — the harder end of "easy." |
| Method-level | `CC` (cyclomatic complexity), `PC` (param count), `LOC` | same | **Easy** — CC is a well-defined graph metric over a control-flow graph; both `radon`/`lizard` (Python) and Roslyn (C#) compute it already. |
| Design/Implementation/Architecture smells | `_design_smells.csv`, `_implementation_smells.csv`, `_arch_smells.csv` | `DesignSmells.csv`, `ImpSmells.csv`, `ArchSmells.csv` | **Hard** — these are the vendor's own heuristic rule catalogs, not published in a way that lets us reproduce the *exact same* smell for the *exact same* code. See below. |
| Testability / test-code smells | — (no DPy equivalent) | `TestabilitySmells.csv`, `TestSmells.csv` | **Hard**, same reason, and Designite-only to begin with (no DPy baseline to even compare against). |

## What's easy: OO metrics

Everything in the "size"/"class-level"/"method-level" rows above traces to
metrics with public, decades-old definitions (Chidamber & Kemerer 1994 for
WMC/DIT/LCOM/NOC; McCabe 1976 for cyclomatic complexity). Off-the-shelf
building blocks that already compute most of these:

- **Python**: `ast` (stdlib) for a from-scratch implementation with full
  control over exactly what's counted (useful for 1:1 comparison, see
  below); `radon` (CC, LOC, maintainability index) and `lizard`
  (cross-language CC/LOC/param-count) as existing libraries that already
  do most of the method-level work.
- **C#**: `Microsoft.CodeAnalysis` (Roslyn) — notably, **this is the same
  underlying engine Designite itself uses** (`DESIGNITE_TASK.md` confirms
  Designite is an `MSBuildWorkspace`-based Roslyn tool), so an in-house
  Roslyn-based analyzer is working from the same AST/symbol-resolution
  primitives Designite is, not a weaker substitute. `lizard` also has C#
  support for the simpler per-method metrics without needing a full
  Roslyn/MSBuild project load (which is what currently requires a real
  `.sln` and blocks repos like `dotnet/aspire` — see `DESIGNITE_TASK.md`
  §5 — a from-scratch tokenizer/lizard-style approach could sidestep that
  requirement entirely for whole-file metrics, at the cost of losing
  whole-project metrics like Fan-In/Fan-Out).

**No LOC cap** on any of these — they're just libraries we run ourselves,
which is the entire point.

## What's hard: smell detection

**Update 2026-08-11: this is no longer just future work — v1 is built and
partially validated for Python.** See "Smell detection: built and partially
validated (2026-08-11)" below and `PySmellDetection.md` for the full
build/validation log. The reasoning in this section is still why it was
scoped out of the first build pass, and still governs the approach taken.

Design/implementation/architecture smells are the harder half, and worth
being honest about *why* before committing to reproducing them:

- The exact rule for e.g. "Unnecessary Abstraction" or "God Component" is a
  specific threshold/heuristic choice by the tool vendor, not a single
  agreed-upon algorithm. Multiple published catalogs exist (Fowler's
  refactoring catalog, Lanza & Marinescu's *Object-Oriented Metrics in
  Practice*, Tufano et al.'s empirical smell studies) and they don't all
  define the same smell identically.
- Reproducing DPy/Designite's *specific* smell counts would require
  reverse-engineering their exact thresholds — not generally reproducible
  from a paper, and arguably not the right goal anyway (their thresholds
  aren't validated as "correct," just as what those specific tools do).
- The more defensible path for a published dataset is probably: **pick one
  or two well-documented smell definitions from the literature, implement
  those transparently and reproducibly ourselves, and report them as their
  own (differently-sourced) metric** — not attempt to match DPy/Designite's
  smell counts number-for-number. That changes the comparison framing (see
  below) from "does our tool agree with theirs" to "does our tool's smell
  signal move the same *direction* as theirs, on the same repos."

## Validation plan: use the pilot as ground truth

The pilot already produced real DPy/Designite output for known snapshots —
this is a genuine opportunity to validate against real data before trusting
an in-house tool on repos with no reference answer:

1. Build the OO-metrics half of the in-house tool first (the "easy" row
   above) — it has a clean 1:1 target to check against.
2. Run it against the **same already-materialized snapshots** the pilot
   used (`data/snapshots/<owner>__<repo>/<commit_sha>/`) — no need to
   re-clone or re-materialize anything.
3. Compare metric-by-metric against the real pilot output already on disk
   (`results/analysis/07-28-smell-metrics-96.csv` for Dock/Designite,
   `results/analysis/07-27-smell-metrics-437.csv` +
   `07-28-smell-metrics-{airbyteDock-192,crewAI-74,mlflowaspire-171}.csv`
   for DPy) — same `(repo_id, track, target_date, commit_sha)` keys already
   used to join everything else, so this is a straightforward join +
   correlation, not new data engineering.
4. For smells specifically: don't aim for exact-count agreement (see above)
   — instead check whether an in-house smell signal (once one is
   implemented) shows the same *before/after* pattern the pilot already
   found (e.g. Dock's implementation-smell density rising ~90%
   post-intervention, per `DockDesigniteReport.md`) — a direction/magnitude
   check, not a row-for-row match.
5. Once validated on the pilot, apply to Phase 2's already-collected raw
   snapshots (which exist specifically because Phase 1d was skipped for
   them, see `ProjectUpdate.md`'s 2026-08-04 entry) — this closes the loop
   the Phase 2 scope decision opened.

## Open questions / what would make this harder than expected

- **Whole-project resolution for C#.** Fan-In/Fan-Out/DIT need real
  cross-file type resolution, which either means a full Roslyn/MSBuild
  project load (same `.sln` requirement Designite already has, including
  its `dotnet/aspire`/`.slnx` blockers) or accepting a weaker
  file-local-only approximation for those specific metrics.
- **Multi-language growth.** If Phase 2/3 adds languages beyond Python/C#,
  an in-house tool needs per-language AST support each time — DPy/Designite
  don't cover other languages either, so this isn't a regression, but it's
  a real scope question for how far "in-house" needs to reach.
- **Time budget vs. the thesis timeline.** This is real engineering work on
  top of an already-busy pipeline — worth scoping the *first* version
  narrowly (OO metrics only, Python first since `ast`/`radon` need no
  project-file setup at all) rather than trying to match Designite's full
  8-CSV-per-project output on day one.

## Design decisions (2026-08-05, build kickoff)

Status upgrade: this section documents the decisions made when moving from
brainstorm to implementation. Answers to the open questions above, plus the
concrete architecture the code will follow.

**Scope: OO metrics only, both languages built in parallel** — smells were
out of scope for this pass (see "What's hard: smell detection" above), but
have since had their own build pass for Python; see "Smell detection: built
and partially validated (2026-08-11)" below. Python and C# analyzers are both in scope for this
build, not sequenced as two separate phases — but Python ships first in
practice (no toolchain/project-load setup needed, and the pilot's DPy output
is the fastest ground truth to validate against per the "Validation plan"
above), with the C# analyzer following the same schema once Python is
validated.

**C# approach: syntax-only Roslyn, not `MSBuildWorkspace`.** This is the
single biggest architectural fork and worth being explicit about *why*:
Designite's `dotnet/aspire` blocker (`DESIGNITE_TASK.md` §5,
`materialize_snapshots.py`'s `EXCLUDED_REPOS`) is entirely a consequence of
`MSBuildWorkspace` needing a real, restorable `.sln`/`.csproj` graph —
Arcade bootstrap, pinned preview SDKs, private feeds. `Microsoft.CodeAnalysis`
also exposes `CSharpSyntaxTree.ParseText`, which parses a single `.cs` file
into a full AST with **no project load at all**. Using that instead means:
- File/class/method-local metrics (LOC, WMC, NOM, NOPM, NOF, NOPF, CC, PC,
  LCOM) are all computable per-file, no `.sln` required — this is the
  `lizard`-style tradeoff the original doc flagged above, chosen deliberately.
- **Fan-In/Fan-Out/DIT need real cross-file type resolution**, which
  `ParseText` alone doesn't give (that's exactly what `MSBuildWorkspace`
  buys Designite). Building these ourselves means a lightweight, in-house
  symbol table: walk every parsed file's class/interface declarations once
  to build a name → declaring-file index, then resolve base-class/interface
  names and field/parameter/return types against that index. This is
  necessarily an approximation (no generic instantiation, no NuGet-package
  type resolution, no partial-class merging across files unless we handle
  `partial` explicitly) — good enough for DIT and same-repo Fan-In/Fan-Out,
  not a full semantic compile.
- **This is expected to unblock `dotnet/aspire`** for the in-house tool even
  though it stays excluded from Designite's own output — worth flagging
  explicitly when Phase 2 analysis runs, since it changes the "3 Python + 1
  C#" language imbalance noted in `ProjectStatus.md` §6 item 1.
- Output schema mirrors DPy/Designite's confirmed columns (see
  `long_analysis.py`'s `parse_tool_output()` docstring) so pooling continues
  to work the way `07-29-pooled-structural-metrics.csv` already does —
  no adapter step, same as the DPy/Designite pooling turned out not to need
  one.

**Correlation matrix: pre vs. post, using the existing `post`/
`intervention_date` convention.** Reuses the same pre/post split
`07-29-pooled-structural-metrics.csv` and `07-29-rq3-process.csv` already
encode (rows before vs. at-or-after each repo's intervention date) rather
than inventing a new split. Two metric-by-metric matrices per unit of
analysis (pre and post), **Spearman** not Pearson — consistent with the
existing process-metrics test choice (`07-29-rq3-process.csv` uses
Mann-Whitney/Cliff's delta, nonparametric throughout) and because smell
counts/LOC aren't expected to be normally distributed. Computed **both**
per-repo (small-N, descriptive) and pooled across the full sample (once
Phase 2 gives enough rows for pooled correlation to mean something) — matches
the existing per-repo-table + pooled-CSV pattern already used elsewhere in
`results/analysis/`.

**Time-series graphs**: one figure per metric, `target_date` on the x-axis,
one line per repo (or faceted small-multiples once the repo count grows past
what's readable on one plot) — built with the `dataviz` skill, reading
directly from the same pooled CSV shape the correlation matrices use, no
separate data prep.

**Entity/snippet tracking (RQ3)**: superseded by decisions logged in
`RQ3_CodeTracking.md`'s own "Design decisions" section, not duplicated here.

## Smell detection: built and partially validated (2026-08-11)

Status upgrade from "hard, separate phase" above: a Python v1 is built,
run against the full available sample, and checked against the pilot's
DPy output. Full design rationale, batch-run log, and validation numbers
live in `PySmellDetection.md`; this is the summary.

**Method**: Lanza & Marinescu's "Detection Strategies" (Marinescu, ICSM
2004; Lanza & Marinescu, 2006) — the well-documented-literature-definition
path this doc's "What's hard" section above called the defensible option,
not an attempt to reverse-engineer DPy/Designite's closed rule catalogs.

**Implemented (`src/inhouse/py_smells.py`), four strategies**:
- **God Class/Blob** and **Data Class** (class-level) → pooled as
  `design_smell_count` / `design_smell_density_per_kloc`
- **Feature Envy** and **Brain Method** (method-level) → pooled as
  `implementation_smell_count` / `implementation_smell_density_per_kloc`
- **Not attempted**: Shotgun Surgery (needs multi-commit history, out of
  scope for v1)

**What was found**: first full run (926 rows, `azure-sdk-for-python`
excluded — its `_tcc` cohesion computation is O(n²) and stalled on its
23,744-file / 40k+-line-file monorepo shape) over-flagged God Class at
~11.7% of classes, 5–25x the other three strategies' rate. Root cause,
confirmed empirically: WMC and TCC are strongly anti-correlated in real
code (Spearman r between −0.53 and −0.82 across sample repos), so ANDing
two independent 25th-percentile filters lands far above the naive 6.25%
independence estimate. Fixed by tightening both thresholds to 10%/10%,
which brought God Class down to 2.46% — in line with the other three
strategies. Re-run on the full corrected corpus: 799/926 ok.

**Validation against the pilot's DPy ground truth** (264 joined rows,
`airbyte`/`crewAI`/`mlflow` only): row-level Spearman correlation is weak
and slightly negative — expected, since this measures a different,
narrower smell definition than DPy's, not the same thing done wrong (see
"What's hard" above on why exact-count agreement was never the goal).
Pre/post-intervention *direction* agreement — the metric the validation
plan above actually cares about — is mixed-but-leaning-positive: 2/2 on
the pooled cross-repo signal, 4/6 per-repo-per-metric.
`implementation_smell_density_per_kloc` (Feature Envy + Brain Method) is
on firmer footing than `design_smell_density_per_kloc` (God Class + Data
Class) — God Class's double-percentile-filter structure is the piece
still flagged as needing more work.

~~**Open**: `_tcc`'s O(n²) cost is unfixed~~ — **fixed 2026-08-17** (the
method-count guard proposed here is built: `ast_common.sample_field_sets()`,
300-method threshold, same fix applied to `_lcom`/C#'s `ComputeLcom` too —
see the "Pipeline scaling, Phase B" section below for the full account,
including a real extrapolation bug caught and fixed along the way). The
`azure-sdk-for-python` per-run exclusion this note originally described as
the workaround can be retired now that the guard exists. A God Class v2
(absolute WMC floor, or corpus-pooled rather than per-snapshot
percentiles) is still suggested but not started - unrelated to the O(n²)
fix, a separate methodology question. **Update 2026-08-13: a C# equivalent
now exists** (`SmellDetector.cs`, a direct port reusing the same
field-access machinery `ComputeLcom` already had — see
`PySmellDetection.md`'s "C# port" section for the build/validation log and
a real bug caught before trusting it on real data). OO metrics' own
coverage also expanded this entry from the 3-repo Python pilot to every
repo with a materialized snapshot (18 repos, both languages, consolidated
into `results/analysis/08-13-inhouse-metrics-pooled.csv`) — see
`ProjectUpdate.md`'s 2026-08-13 entry for the full account, including a
real Dock stale-clone data-hygiene bug caught and fixed in the
consolidation step.

Built on the (now-merged) `python-smell-detection` branch, commits
`6084ef9f6`..`ace21ab6f`.

## Pipeline orchestration & scaling, Phase A (2026-08-17)

Status upgrade: with the corpus about to grow from ~18-21 repos toward
100 then 1000, three cross-cutting gaps got fixed before touching repo
count at all — see the session's scaling plan for the full phased design
(Phase A here; Phase B covers repo-level concurrency, the `_tcc`/`_lcom`
O(n²) cohesion bottleneck above, and entity-history git-subprocess
batching — none of that is built yet).

**`src/common/resumable_run.py`** extracts the done-keys/progress/error-
file convention that `pool_inhouse_metrics.py`, `pool_inhouse_smells.py`,
and `pool_entity_history.py` had each independently reimplemented
(`long_analysis.py` keeps its own copy — see below for why it wasn't
migrated). Same behavior as before (a fragment file counts as done if it
matches `*-<tag>-*.csv`, globally across every prior run with that tag,
which is what lets parallel `--repo`-scoped invocations share progress),
plus a `schema_version` sidecar (`<stem>.runinfo.json`) that lets a fix
which changes what "done" should mean for existing rows invalidate the
old ones by bumping a `SCHEMA_VERSION` constant, rather than relying on
someone remembering to move stale files into an `archive_*/` folder by
hand — the exact footgun that bit the 2026-08-12/13 entity-history
sampling-bias re-run (`RQ3_CodeTracking.md`) and an earlier
`PySmellDetection.md` full re-run. Files predating this tracking (no
`.runinfo.json`) are still trusted, so nothing already in
`results/analysis/` needed re-validating. All three pool scripts also get
a `--stale-check` flag: reports done-key count/file count/oldest-newest
without running anything, so drift is visible before a real run starts
instead of only discoverable after the fact via a suspiciously-instant
resume.

**`results/repos/excluded_repos.csv` + `src/common/exclusions.py`**
replace three previously uncoordinated exclusion mechanisms: a hardcoded
`EXCLUDED_REPOS` set (`materialize_snapshots.py`), ad hoc `--exclude-repo`
CLI flags per invocation, and no single place recording *why*.
`full_name, excluded_at, reason, scope` — `scope=permanent` (the tool can
never handle this repo, e.g. `dotnet/aspire`'s MSBuildWorkspace/PAT
issues) or `scope=per-run` (a scale workaround expected to be retired by
a real fix, e.g. `azure-sdk-for-python`'s O(n²) cohesion stall, still
open above). `materialize_snapshots.py` now loads `EXCLUDED_REPOS` from
the registry's permanent rows; `pool_inhouse_metrics.py`/
`pool_inhouse_smells.py` auto-apply the per-run rows (deliberately *not*
the permanent ones — dotnet/aspire's exclusion is Designite-project-graph-
specific and doesn't apply to the syntax-only in-house tools, per the
"C# approach" design decision above) and print a reminder to register a
`--exclude-repo` filter persistently if it's meant to outlive one
invocation. `consolidate_inhouse_metrics.py`'s Dock stale-clone row-drop
rule is deliberately *not* in this registry — it's a row-level patch for
already-produced bad data, not a repo-selection decision.

**`src/pipeline/run_pipeline.py`** is a thin subprocess sequencer for the
now-13-stage pipeline (`select → snapshot-manifest → materialize →
metrics/smells/entity-history → consolidate-metrics/consolidate-smells →
regression → viz-track-a/viz-churn → validate-metrics/validate-smells`),
previously run stage-by-stage by hand in the order documented only in
prose in `ProjectStatus.md`/this file. `python -m
src.pipeline.run_pipeline run --stages metrics,smells --dry-run --limit 3`
or no `--stages` for the full default sequence; writes a rolled-up
`results/pipeline-run-<timestamp>.json` per invocation and stops (non-zero
exit) on the first stage failure rather than continuing past it. It
doesn't reimplement any stage - each one keeps its own argparse flags,
resumability, and output conventions; the orchestrator only knows which
of its own shared flags (`--dry-run`/`--limit`/`--repo`/`--target-total`/
`--stale-check`) each stage's argparse actually accepts, and forwards
accordingly. `consolidate_inhouse_metrics.py`, `consolidate_inhouse_smells.py`,
and `generate_track_a_figures.py` (none of which had a CLI before this)
each got a stable `run()` alias to their existing `consolidate()`/`main()`
body so they're callable consistently, though the orchestrator still
shells out to all stages uniformly rather than importing some directly.

**`legacy-dpy-designite` (`long_analysis.py`) is deliberately excluded
from the orchestrator's default stage list**, and now hard-gated inside
`long_analysis.py` itself: refuses to run (non-`--dry-run`) against more
than `PILOT_SIZE_CEILING=25` eligible rows without an explicit `--force`.
This tool remains the pilot-recalibration path against the licensed
DPy/Designite baseline — not retired, since that comparison still
matters — but must never run by accident at 100/1000-repo scale, given
one `mlflow` snapshot alone took ~29 hours under its LOC-cap chunking
(see "What's hard: smell detection" above). This is also why
`long_analysis.py` wasn't migrated to `resumable_run.py`: low value
relative to the risk of touching a path being deliberately scoped down,
not scaled up.

**Side effect worth flagging**: testing the `viz-churn` stage end-to-end
against real data surfaced that `Writing/figures/method_churn/`'s
`fig7`/`fig8`/`fig9`/`table3` were stale — last generated before the
2026-08-13 entity-history sampling-bias fix (`RQ3_CodeTracking.md`)
landed on `main`. Regenerating them (now part of this same commit)
changed real numbers, e.g. `wieslawsoltes/Dock` now shows real churn
stats instead of being silently absent - not a pipeline-scaling change
itself, just something the orchestrator's first real end-to-end run
happened to catch.

## Pipeline scaling, Phase B (2026-08-17, same day as Phase A)

Status upgrade: the actual wall-clock levers for 100/1000-repo scale -
concurrency, the two confirmed O(n) blowups - all landed the same day as
Phase A, verified against real data before committing.

**Repo-level concurrency**: new `src/common/parallel_repo.py`
(`run_by_repo()`), a thin dispatcher shared by `pool_inhouse_metrics.py`,
`pool_inhouse_smells.py`, `pool_entity_history.py`, and
`materialize_snapshots.py` rather than each reimplementing it - the exact
triplication `resumable_run.py` (Phase A) already fixed once for the
resumability logic. `--workers N` (default 1, sequential, byte-identical
to pre-concurrency behavior including the single unscoped output file) -
above 1, dispatches one `ProcessPoolExecutor` worker per repo (each
repo's analysis is independent, so this is embarrassingly parallel; not
threads, since the per-row analyzers are CPU-bound AST/Roslyn work).
Workers write their own repo-scoped fragment file, the same shape a
manual `--repo <name>` invocation already produces, so parallel and
sequential runs are structurally indistinguishable on disk. Verified:
real multi-repo dispatch across all four scripts, correct row/repo
counts (no duplication or loss), cross-mode resumability (a parallel
run's fragments are correctly picked up by a subsequent sequential
`--repo`-scoped run and vice versa), and a synthetic failing-worker case
confirming `ProcessPoolExecutor` exceptions propagate correctly rather
than silently vanishing.

**The `_tcc`/`_lcom` O(n²) cohesion bottleneck** (the "Open" note above,
now resolved): `ast_common.sample_field_sets()`, modeled directly on
`entity_matching.py`'s `sample_files()` (same fix for the same class of
problem - an O(n²)/O(n) computation exploding on an outlier-sized
population, methods-within-a-class here instead of files-within-a-repo).
Above 300 methods, both `_tcc` (`py_smells.py`) and `_lcom`
(`py_metrics.py`) sample instead of computing the full pairwise scan;
the C# mirrors (`SmellDetector.cs`'s TCC computation, `SnapshotAnalyzer.cs`'s
`ComputeLcom`) get the identical fix, seeded via a hand-rolled FNV-1a hash
since `string.GetHashCode()` is randomized per-process in modern .NET
(would break run-to-run reproducibility). New `tcc_sampled`/`lcom_sampled`
(class-level) and `n_tcc_sampled`/`n_lcom_sampled` (snapshot-level
summary) columns flag when this fired - expected to be near-always 0
outside pathological repos.

**A real statistical bug caught during testing, not shipped**: the first
LCOM implementation scaled the sampled P/Q counts by (true pair count /
sampled pair count) before subtracting, mirroring how TCC's ratio-based
estimate works. Verified directly with a controlled synthetic case (a
600-method class split evenly across 2 fields, no field overlap): true
P-Q=300, naively rescaled sample estimate=593 - **~98% relative error**.
Root cause: unlike TCC (a ratio, so a subsample's own ratio is already an
unbiased density estimate), LCOM is P-Q, a *difference* of two
typically-large, nearly-equal counts for a reasonably cohesive class -
the true magnitude is governed by a second-order imbalance term
(algebraically, P-Q = N/2 - (k_a-k_b)²/2 for a 2-group split), not a
simple density, so the quadratic pair-count ratio over/under-corrects it
badly, and subtracting two large, sampling-noisy, highly-correlated
estimates amplifies relative error catastrophically (classic
catastrophic cancellation). Fixed by reporting the raw p-q computed
directly on the sampled subset instead - smaller in absolute terms than
an unsampled class's LCOM (expected, flagged via `lcom_sampled`, not
silently wrong), but internally consistent across every sampled class.
Both `py_metrics.py`'s `_lcom` and `SnapshotAnalyzer.cs`'s `ComputeLcom`
carry the full derivation in their docstrings/comments, not just the
conclusion.

**Entity-history's per-touch `git show` cost** (confirmed 68 minutes on
`browser-use/browser-use`, one 445-touch entity): `py_entity_history.py`'s
new `batch_show()` replaces one `git show` subprocess per commit-touch
with one `git cat-file --batch` process per file - reads a stream of
`<sha>:<path>` specs from stdin, writes each blob back with a
length-prefixed framing, all within one process instead of N. **Measured
38.7x speedup** (4.339s → 0.112s) on an 80-commit real sample from
`crewAIInc/crewAI`, with byte-identical content confirmed against the old
per-commit approach. Applied to both `py_entity_history.py`'s own
`collect_file_sequences()` and `cs_entity_history.py`'s (which shares
`py_entity_history.py`'s git plumbing directly) - both languages hit the
identical bottleneck, since the C# `--batch` mode built earlier
(`EntityHistory.cs`) only ever batched the .NET side, not the git-fetch
side; that script's own docstring said as much ("`git show` is still one
subprocess call per commit... that part is unavoidable") until today.

**Storage lifecycle, deliberately incomplete**: new
`src/common/storage_lifecycle.py` identifies which repos'
`data/repo_cache/` clones are safe to reclaim (entity-history done for
that repo, not on a `results/repos/keep_cache.csv` opt-out list) and
reports or deletes them - dry-run by default, `--confirm`-gated for real
deletion, real numbers confirmed against this repo's own disk (9.37GB
across 21 repos). Deliberately **not** wired into
`materialize_snapshots.py`'s main flow or `run_pipeline.py`'s stage list,
a real deviation from the scaling plan's original "prune automatically
right after entity-history finishes" framing: a repo's clone may be
needed again even after entity-history is "done" for it today (the
manifest could later be regenerated with a wider date grid, or
`--max-files-per-repo` raised for a fuller pass) - deleting the only
full-history clone on the assumption that today's "done" is final would
turn either of those into a full re-clone instead of a quick re-run. So:
framed as a manual, deliberate action a researcher runs when *they*
decide a repo is truly done, not something the pipeline does on its own.
The lighter secondary policy (pruning individual
`data/snapshots/<repo>/<sha>/` directories) from the original plan is
documented as a real follow-up, not built - `data/snapshots/` is the
much smaller half of the disk cost, and correctly identifying "this
commit's snapshot is no longer needed by anything" requires checking
every relevant consolidated output, not just one.

**Not done this entry**: actually growing the corpus (`--target-total`
is parameterized - see `ProjectUpdate.md`'s 2026-08-17 write-up - but no
real 100-repo run has been kicked off yet); re-running the Phase 0
candidate search with a wider pool (235 candidates is enough for 100,
not 1000 - still an open precondition); retiring the
`azure-sdk-for-python` per-run exclusion in `results/repos/excluded_repos.csv`
now that the cohesion-sampling fix makes it unnecessary (safe to remove,
just not done here).
