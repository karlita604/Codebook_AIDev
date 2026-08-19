# File reference

A file-by-file map of what's in `src/` — functionality, design rationale, and
known caveats for each module. Companion to the top-level [README.md](README.md)
(which covers *running* the pipeline end to end); this file is about what each
piece of code actually does and where its sharp edges are.

---

## Table of contents

**Pipeline orchestration**
- [`src/pipeline/run_pipeline.py`](#srcpipelinerun_pipelinepy)

**Phase 0 — corpus selection & data collection**
- [`src/phase0/PRfilter.py`](#srcphase0prfilterpy)
- [`src/phase0/phase1.py`](#srcphase0phase1py)
- [`src/phase0/repo_pr_selection.py`](#srcphase0repo_pr_selectionpy)
- [`src/phase0/repo_snapshot_pipeline.py`](#srcphase0repo_snapshot_pipelinepy)
- [`src/phase0/materialize_snapshots.py`](#srcphase0materialize_snapshotspy)
- [`src/phase0/pr_sampling_pipeline.py`](#srcphase0pr_sampling_pipelinepy)
- [`src/phase0/long_analysis.py`](#srcphase0long_analysispy)
- [`src/phase0/progress_dpy.py`](#srcphase0progress_dpypy)
- [`src/phase0/analyze_dock_designite.py`](#srcphase0analyze_dock_designitepy)
- [`src/phase0/generate_phase0_figures.py`](#srcphase0generate_phase0_figurespy)
- [`src/phase0/metrics.py`](#srcphase0metricspy)
- [`src/repos/repo.py`](#srcreposrepopy)

**In-house structural-metrics engines**
- [`src/inhouse/ast_common.py`](#srcinhouseast_commonpy)
- [`src/inhouse/py_metrics.py`](#srcinhousepy_metricspy)
- [`src/inhouse/csharp_metrics.py`](#srcinhousecsharp_metricspy)
- [`src/inhouse/cs_smells.py`](#srcinhousecs_smellspy)
- [`src/inhouse/py_smells.py`](#srcinhousepy_smellspy)
- [`src/inhouse/pool_inhouse_metrics.py`](#srcinhousepool_inhouse_metricspy)
- [`src/inhouse/pool_inhouse_smells.py`](#srcinhousepool_inhouse_smellspy)
- [`src/inhouse/consolidate_inhouse_metrics.py`](#srcinhouseconsolidate_inhouse_metricspy)
- [`src/inhouse/consolidate_inhouse_smells.py`](#srcinhouseconsolidate_inhouse_smellspy)
- [`src/inhouse/validate_against_pilot.py`](#srcinhousevalidate_against_pilotpy)
- [`src/inhouse/validate_smells_against_pilot.py`](#srcinhousevalidate_smells_against_pilotpy)

**RQ3 entity-lineage tracker**
- [`src/inhouse/entity_matching.py`](#srcinhouseentity_matchingpy)
- [`src/inhouse/py_entity_history.py`](#srcinhousepy_entity_historypy)
- [`src/inhouse/cs_entity_history.py`](#srcinhousecs_entity_historypy)
- [`src/inhouse/pool_entity_history.py`](#srcinhousepool_entity_historypy)
- [`src/inhouse/entity_history_windowed_cut.py`](#srcinhouseentity_history_windowed_cutpy)
- [`src/inhouse/validate_entity_matching.py`](#srcinhousevalidate_entity_matchingpy)

**Roslyn console app (`src/inhouse/roslyn_tool/`)**
- [`Program.cs`](#programcs)
- [`Entities.cs`](#entitiescs)
- [`CcWalker.cs`](#ccwalkercs)
- [`SnapshotAnalyzer.cs`](#snapshotanalyzercs)
- [`SmellDetector.cs`](#smelldetectorcs)
- [`EntityHistory.cs`](#entityhistorycs)

**Statistical analysis & visualization**
- [`src/analysis/segmented_regression.py`](#srcanalysissegmented_regressionpy)
- [`src/viz/figures_common.py`](#srcvizfigures_commonpy)
- [`src/viz/generate_track_a_figures.py`](#srcvizgenerate_track_a_figurespy)
- [`src/viz/generate_churn_figures.py`](#srcvizgenerate_churn_figurespy)

**Shared infrastructure (`src/common/`)**
- [`resumable_run.py`](#resumable_runpy)
- [`parallel_repo.py`](#parallel_repopy)
- [`exclusions.py`](#exclusionspy)
- [`storage_lifecycle.py`](#storage_lifecyclepy)

**Misc**
- [`src/rejection_analysis.py`](#srcrejection_analysispy)

---

## Pipeline orchestration

### `src/pipeline/run_pipeline.py`

Thin subprocess sequencer for the 13-stage pipeline (`select → snapshot-manifest
→ materialize → metrics/smells/entity-history → consolidate-metrics/consolidate-smells
→ regression → viz-track-a/viz-churn → validate-metrics/validate-smells`) — doesn't
reimplement any stage, just runs each script's own file with the shared flags it
declares support for (`--dry-run`/`--limit`/`--repo`/`--target-total`/`--stale-check`/
`--workers`), stops on the first non-zero exit, and writes a rolled-up
`results/pipeline-run-<timestamp>.json`. `legacy-dpy-designite` (`long_analysis.py`)
is deliberately excluded from the default stage list and only runs if named
explicitly via `--stages` — it's gated by its own pilot-size ceiling and must never
fire by accident at scale. `status` subcommand reads back the latest run log.

---

## Phase 0 — corpus selection & data collection

### `src/phase0/PRfilter.py`

Filters the `hao-li/AIDev` PR dataset (read live from Hugging Face, nothing
cached) by rejection status, star count, language, agent, follower/fork/age
thresholds, English-title detection, non-empty body, and live-URL checking
(concurrent HTTP HEAD, treating timeouts/non-404s as "keep" so transient
failures never wrongly drop a PR). English-title detection is a non-Latin-
letter-ratio heuristic (>30% non-Latin letters = rejected), chosen over a
statistical language-ID model after spot checks showed the model
misclassifying ~20% of genuinely English titles. `require_live_url` is
applied last since it's the most expensive check. Writes a descriptor-tagged
CSV; can also be imported as `filter_prs()`.

### `src/phase0/phase1.py`

Joins a CSV of PR ids against `all_pull_request.parquet` to attach metadata
columns (title, body, agent, timestamps, repo info) — a left join, so an id
with no match keeps its row with NaN metadata rather than being silently
dropped. No caching; re-reads the full parquet from Hugging Face every run.

### `src/phase0/repo_pr_selection.py`

Phase 1a: derives each candidate repo's *intervention date* (its earliest
agent-authored PR) from AIDev, since that dataset only covers
2024-12-24–2025-07-30 and has no pre-agent baseline. `suggest_pilot(n)`
stratifies a pick across `["Python", "C#"]`, preferring higher agent-PR-count
repos — its growth property (a larger `n`'s pick is a superset of a smaller
`n`'s) is verified empirically via `check_monotonic_growth()` against the
current 235-row candidate pool, not proven in general; re-run that check
before trusting the property against a widened or re-shaped candidate pool
(e.g. before a 1000-repo run, or after adding a third language).
`--target-total`/`--pilot-size` (deprecated alias, kept working) caps out at
whatever the fixed candidate-pool CSV contains.

### `src/phase0/repo_snapshot_pipeline.py`

Phase 1c: clones each pilot repo (partial clone, full history, lazy blobs)
and resolves two independent snapshot grids against it — A1 (fixed monthly
calendar, 2022-01-01–2026-03-31) and A2 (weekly ±3 months / monthly out to
±12 months around the repo's own intervention date) — recording the nearest
commit at-or-before each grid point and how stale that resolution is
(`STALENESS_THRESHOLD_DAYS=45`). Produces a *manifest* (which commit
represents which repo×track×date), not metrics themselves — that's Phase
1d/in-house's job. No GitHub API/token needed, just git.

### `src/phase0/materialize_snapshots.py`

Phase 1e: extracts language-filtered source trees (`git archive` with a
`*.py` or `*.cs`/`.sln`/`.slnx`/etc. pathspec, not a full checkout) for every
unique `(repo, commit_sha)` in the manifest into `data/snapshots/`. One-time
per-repo blob backfill (`git backfill --sparse`) before archiving, since
archiving directly against a `--filter=blob:none` clone triggers slow
one-object-at-a-time fetches; both backfill and archive force HTTP/1.1 since
this environment's HTTPS transport was observed resetting mid-transfer under
HTTP/2. `_present_patterns()` filters the pathspec down to patterns that
actually match something at that commit first, since `git archive` (unlike
checkout) hard-fails if any given pathspec matches zero files — needed
because Dock's C# pathspec includes both `.sln` and `.slnx`, and no single
commit has both. Idempotent/resumable per commit; `--workers N` dispatches
one process per repo (safe — no shared output file to race on, unlike the
pool scripts). `EXCLUDED_REPOS` is loaded from the permanent-scope rows of
`results/repos/excluded_repos.csv`, not hardcoded.

### `src/phase0/pr_sampling_pipeline.py`

Phase 1b: samples PR *identity* (number, timestamps, comment count — not yet
diff/review depth) via the GitHub Search API on two tracks: B1 (monthly 2-day
window, up to 10 PRs/month, flagged `is_undersampled` if fewer exist rather
than padded) and B2 (10 PRs immediately before/after each repo's intervention
PR). Needs `GITHUB_TOKEN`; `GITHUB_TOKENS_FILE` (one token per line)
round-robins additional tokens through a `TokenPool`, dividing the pacing
delay by token count so aggregate throughput scales roughly linearly.
Resumable at the query-unit level via a *query ledger* CSV (not just the PR
rows) — necessary because a legitimately-empty window can't otherwise be
told apart from "not yet queried."

### `src/phase0/long_analysis.py`

Phase 1d, legacy: the licensed DPy (Python)/Designite (C#) driver — chunks
oversized snapshots under each tool's Trial-license LOC cap (DPy: 8,000
LOC/chunk via directory-boundary splitting + bin-packing loose files;
Designite: 45,000 LOC/chunk via whole-project bin-packing, since it can't
split a single project's files) and consolidates chunk output via
`parse_tool_output()`. Explicitly documents that chunk-scoped architecture
smells and Fan-In/Fan-Out are *not* repo-wide when chunked — collected for
traceability but never pooled as if they were. Hard-gated: refuses to run
(outside `--dry-run`) against more than `PILOT_SIZE_CEILING=25` eligible rows
without `--force`, since one large snapshot alone took ~29 hours under this
chunking. `.slnx`-only snapshots raise `NotImplementedError` (the installed
DesigniteConsole 5.3.0.0 can't open them) rather than being silently
skipped.

### `src/phase0/progress_dpy.py`

Live progress reporter for `long_analysis.py`'s background runs — queries the
OS process list (not a possibly-stale PID file) for running `long_analysis.py`
invocations, deduplicates real progress across every `*-smell-metrics-*.csv`,
and splits errors into "expected" (known causes like `DESIGNITE_EXECUTABLE
not set` or the resolved 2026-07-28 Smart App Control incident) vs.
"unexpected" (surfaced in full, since a growing pile is worth noticing).

### `src/phase0/analyze_dock_designite.py`

Exploratory analysis script backing `Writing/DockDesigniteReport.md`
(hand-written, not auto-generated — edit both if underlying numbers change).
Produces 11 time-series/comparison PNGs plus Mann-Whitney U + Cliff's delta
pre/post statistics from Dock's real Designite pilot output. Requires
`scipy` (not otherwise a phase0 dependency).

### `src/phase0/generate_phase0_figures.py`

Generates 6 figures + a `findings.md` descriptive summary from
`data/04_pr250 - 04_pr250.csv` (a 250-PR rejection-reason-coding sample) —
agent mix, monthly volume, rejection-label frequency, top repos, close-time
distribution, description length. Standalone, hand-rolled CSV parsing (no
pandas) with its own palette constants duplicated from the dataviz-skill
reference rather than importing `figures_common.py` (predates it).

### `src/phase0/metrics.py`

A scaffold/stub, not a working script — defines `calculate_rejected()` (the
one implemented metric) plus ~20 empty section headers (`num_diffhunks`,
`duplicate_code`, `god_object`, `cyclomatic_complexity`,
`author_experience`, etc.) with no bodies, evidently a planning placeholder
for PR-level metrics that was never built out. Importing it executes three
unconditional Hugging Face parquet reads at module load time.

### `src/repos/repo.py`

Given a CSV of PR ids, finds the unique repos they belong to and writes one
summary row per repo (id, full_name, language, stars, forks, url, license) —
also logs the exact `hao-li/AIDev` dataset version (commit sha +
last-modified) used, to a dated log file, since the dataset is read live and
can change between runs.

---

## In-house structural-metrics engines

### `src/inhouse/ast_common.py`

Shared, from-scratch AST primitives for Python — entity extraction
(module/class/method/function inventories via stdlib `ast`, not `radon`, so
every counting rule is explicit) and cyclomatic complexity (`_CCVisitor`:
base 1, +1 per `if`/`for`/`while`/`except`/boolean-operand/ternary/
comprehension-`if`/`match`-case; stops at nested def/class boundaries;
lambdas are not a boundary). `self_attribute_names()` deliberately can't
distinguish a field read from a method call at the AST level — callers must
pass the class's own method names as `exclude`, or a call like
`self.speak()` gets misread as a field access (a bug this fix was created
for). `sample_field_sets()` caps the O(n²) cohesion pairwise scan at 300
methods via a seeded random subsample (deterministic per class, via its
qualified name) — the fix for a confirmed ~20-minute stall on
`azure-sdk-for-python`'s largest generated-file classes. Also provides
`max_nesting_level`, `accessed_variable_names`, `foreign_attribute_accesses`,
and `is_accessor_method` — all primitives `py_smells.py`'s Lanza & Marinescu
strategies need, plus the RQ3 entity tracker.

### `src/inhouse/py_metrics.py`

The Python OO-metrics engine — LOC, NOM/NOPM/NOF/NOPF, WMC, LCOM (Chidamber
& Kemerer's original LCOM1, `max(0, P−Q)`), DIT, Fan-In/Fan-Out, per-method
CC/PC — output shaped to match DPy's confirmed schema so both pool with no
adapter step. Fan-In/Fan-Out and DIT are documented, whole-snapshot
*heuristics* (textual identifier/attribute matching against a same-name
class index, no import-alias resolution or type inference) — the accepted
cost of not doing a real project-wide semantic resolution. `_lcom()`
explicitly does **not** rescale a sampled subclass's `P−Q` by the pair-count
ratio (a rejected fix, verified on a synthetic 600-method case to produce
~98% relative error via catastrophic cancellation) — it reports the raw
sampled `p−q` instead, flagged via `lcom_sampled`.

### `src/inhouse/csharp_metrics.py`

Python-side glue that shells out to the compiled Roslyn console tool
(`roslyn_tool.dll`) the same way `long_analysis.py` shells out to
`DesigniteConsole` — `ensure_built()` auto-builds via `dotnet build -c
Release` if the DLL is missing. Returns the identical schema `py_metrics.py`
does, so both languages pool with no adapter step. Raises (rather than
swallowing) on a non-zero exit or non-JSON stdout.

### `src/inhouse/cs_smells.py`

The C# smell-detector's Python glue, mirroring `csharp_metrics.py` but
invoking the tool's `--smells` mode instead of its default OO-metrics mode —
same subprocess/JSON/error-handling convention, ~30 lines.

### `src/inhouse/py_smells.py`

Python smell detector implementing four of Lanza & Marinescu's Detection
Strategies from the published formulas (not reverse-engineered from
DPy/Designite's closed catalogs): **God Class/Blob** (`WMC≥p90 AND TCC≤p10
AND ATFD>1`), **Data Class** (`WOC<1/3` plus a NOPA+NOAM/WMC condition),
**Feature Envy** (`ATFD>5 AND LAA<1/3 AND FDP≤5`), **Brain Method**
(`LOC>p75(class LOC)/2 AND CYCLO≥p75 AND MAXNESTING≥3 AND NOAV>7`).
Thresholds are computed as *percentiles over this run's own population*, not
the literature's absolute Java-corpus constants. God Class's percentile pair
was tightened from Marinescu's own 25%/25% worked example to 10%/10% after
the first full batch run measured an 11.7% flag rate — traced to WMC/TCC
being strongly anti-correlated in real code (Spearman r −0.53 to −0.82), so
two correlated 25% filters intersect far above the naive 6.25% independence
estimate. `_tcc()` uses the same 300-method sampling cap as `py_metrics.py`'s
LCOM, but needs no rescaling correction since TCC is already a ratio.

### `src/inhouse/pool_inhouse_metrics.py`

Batch CLI orchestrator running `py_metrics.py`/`csharp_metrics.py` against
every materialized snapshot in the manifest, resumable via
`src/common/resumable_run.py`. Deliberately does **not** inherit
`materialize_snapshots.py`'s permanent `EXCLUDED_REPOS` (e.g.
`dotnet/aspire`) — that exclusion is Designite/`MSBuildWorkspace`-specific
and doesn't apply to this syntax-only tool — but does auto-apply the
registry's `scope=per-run` rows (e.g. `azure-sdk-for-python`'s
cohesion-computation stall). `--workers N>1` writes one fragment file per
repo via `ProcessPoolExecutor`, structurally indistinguishable on disk from
several manual `--repo`-scoped invocations. `SCHEMA_VERSION=1` gates
done-key trust via the runinfo sidecar.

### `src/inhouse/pool_inhouse_smells.py`

The smell-detector counterpart to `pool_inhouse_metrics.py` — identical CLI
shape, resumability, per-run/permanent exclusion handling, and `--workers`
fragment-file convention, just calling `py_smells.py`/`cs_smells.py`
instead.

### `src/inhouse/consolidate_inhouse_metrics.py`

Concatenates every fragmented `*-inhouse-metrics-*.csv` into one canonical
pooled table (dedup on the 4-column key, last-seen wins). One deliberate
exception to "last-seen wins": any *unscoped* (bare-number-suffixed, i.e.
default-manifest) run's Dock rows are dropped unconditionally, not
deduplicated — Dock's `repo_cache` clone is stale (frozen years in the
past), so the default manifest collapses ~94 of its 96 grid points onto one
commit; the correct, `--manifest`-overridden Dock data is kept instead. This
row-level patch is deliberately *not* in `results/repos/excluded_repos.csv`
— it fixes already-stale data from a bug, not a repo-selection decision.
Has a stable `run()` alias for the orchestrator (script has no argparse).

### `src/inhouse/consolidate_inhouse_smells.py`

The smell-pool counterpart to `consolidate_inhouse_metrics.py` — same
dedup/Dock-drop logic, glob-includes the older pre-C#
`*-inhouse-smells-python-*.csv` files (still valid rows, just from before
the tag dropped "-python").

### `src/inhouse/validate_against_pilot.py`

Joins the in-house OO-metrics output against the pilot's real
DPy/Designite ground truth (`07-29-pooled-structural-metrics.csv`) on the
shared 4-column key and reports mean diff / mean %-diff / Spearman r per
shared metric, split by language (a blended Python+C# average would be
misleading). Not a pass/fail gate — a quantified report, written to
`08-11-inhouse-validation-report.csv`.

### `src/inhouse/validate_smells_against_pilot.py`

The smell-validation counterpart — explicitly does **not** run the same
exact-count correlation check, since the smell catalogs are independently
sourced (Lanza & Marinescu vs. DPy's closed rules), so row-for-row agreement
isn't the right question. Reports both a Spearman correlation (informative,
not a match requirement) and, more importantly, pre/post-intervention
*direction* agreement per repo and pooled — the actual validation target
per `PySmellDetection.md`'s plan.

---

## RQ3 entity-lineage tracker

### `src/inhouse/entity_matching.py`

Language-agnostic lineage matcher — given a chronological per-commit entity
inventory for one file, reconstructs which entity at commit N+1 is "the
same" as which at commit N, even across renames. Two-tier match: exact
`qualified_name` first, then greedy Jaccard token-overlap fuzzy matching
(threshold 0.75, CodeShovel's published starting point) for whatever's left.
`sample_files()` fixes a real diagnosed bias — plain sorted-order file
truncation correlated alphabetical position with a repo's own
directory-creation history (confirmed on crewAI: its sorted-first 150 files
landed almost entirely in a subtree added 18 months *after* its intervention
date) — with a seeded uniform random sample instead. `EntityLineage`
exposes `relative_churn` (Nagappan & Ball), `change_entropy` (a stated
*simplified proxy* for Hassan's entropy-of-changes, not a faithful
reimplementation), and `review_count` (always `None` — an explicit
placeholder, not a fabricated stand-in, since Track B's deeper per-PR review
data doesn't exist).

### `src/inhouse/py_entity_history.py`

Python entity-lineage extraction — walks every currently-tracked `.py`
file's `git log --follow` history, extracts a class/method inventory at each
touching commit via `ast_common`, feeds sequences through
`entity_matching.py`. Only files present at current HEAD are walked (a file
deleted and never restored is invisible); cross-file moves aren't tracked as
continuous (each file is followed independently). `batch_show()` fetches
every blob a file's history needs in **one** `git cat-file --batch`
subprocess instead of one `git show` per commit — the fix for a confirmed
68-minute stall on one 445-touch entity in `browser-use/browser-use`,
measured at a 38.7x speedup on an 80-commit sample.

### `src/inhouse/cs_entity_history.py`

The C# counterpart — reuses `py_entity_history.py`'s git plumbing
(`follow_history`, `_run_git`, `batch_show`) directly since it's
language-agnostic, but extracts entities via the Roslyn tool's `--batch`
stdin mode (one subprocess call per file's whole history, not per commit —
.NET process-startup cost made per-commit invocation impractical, confirmed
empirically).

### `src/inhouse/pool_entity_history.py`

Stage 5 orchestrator: runs entity-lineage extraction across every repo in
the manifest, resumable per `(repo_id, full_name)` rather than per snapshot
row — RQ3's unit of work is "one repo's full git history." Reads directly
from `data/repo_cache/` (not `data/snapshots/`), so repos never materialized
for the OO-metrics tools are still includable. `--max-files-per-repo`
(default 150) is a stated, deliberate scope decision — some repos are far
too large for an exhaustive walk (`azure-sdk-for-python` alone has 44,112
Python files at HEAD) — trading per-repo completeness for cross-repo
breadth; files are sampled via `entity_matching.sample_files()`, not the
biased sorted-order truncation.

### `src/inhouse/entity_history_windowed_cut.py`

Stage 6: a filter/join over Stage 5's already-collected pooled output (not a
new collection pass) — classifies every lineage into `pre_only`,
`post_created`, or `spans` against each repo's `intervention_date`. States
its own real limitation directly: classification is per-*lineage* (using
pooled first/last touch date), not per-*touch* — a `spans` entity's
`modification_count` can't be split into "N before, M after" from this
file's inputs alone, since Stage 5's pooled CSV doesn't carry per-touch
dates.

### `src/inhouse/validate_entity_matching.py`

Stage 3 validation gate: measures the matcher's real accuracy before
trusting any age/churn/entropy number from it, via two checks — an
automated baseline (cross-checking never-renamed lineages' touch-commit
sets against `git log -L`'s independently-computed, differently-implemented
line history — a genuine two-independent-methods agreement check) and a
manual-review candidate export (every detected rename/move across a
threshold sweep, with real diffs printable via `--print-diffs` for human
judgment, since a real rename can't be automatically told apart from a
coincidental token-overlap false match).

---

## Roslyn console app (`src/inhouse/roslyn_tool/`)

A .NET 8 console app (`Microsoft.CodeAnalysis.CSharp`) invoked as a
subprocess from Python. All three of its modes use `CSharpSyntaxTree.ParseText`
only — no `.sln`/`.csproj` load, ever.

### `Program.cs`

Entry point, three modes — default (`RoslynMetrics <snapshot-dir>`, OO
metrics), `--smells <snapshot-dir>` (smell detection), `--batch` (reads a
JSON array of `{relpath, text}` blobs from stdin for the entity-history
tool). Errors are written as a structured JSON object on stdout, not just
stderr, so the Python caller can always parse *something* and keep going
rather than crashing a batch run on one bad snapshot.

### `Entities.cs`

Shared `MethodInfo`/`ClassInfo`/`ModuleInfo` record types — deliberately
mirrors `ast_common.py`'s `MethodEntity`/`ClassEntity` shape field-for-field.
`ClassInfo.FieldNameSet` comes from real `FieldDeclarationSyntax` (plus
auto-properties), sidestepping the Python side's usage-inferred-field
problem entirely — the exact bug `ast_common.py`'s `exclude` parameter
exists to guard against doesn't exist on the C# side.

### `CcWalker.cs`

McCabe cyclomatic complexity from scratch, mirroring `ast_common.py`'s
`_CCVisitor` node-for-node (`if`/`for`/`foreach`/`while`/`do`/`catch`/
switch-label/switch-arm/ternary/`&&`/`||`), so the two languages' CC
definitions are directly comparable rather than borrowed from two different
third-party analyzers. Stops at nested method/local-function/type
boundaries; lambdas are not a boundary.

### `SnapshotAnalyzer.cs`

The C# OO-metrics engine — same aggregation, output keys, and percentile
method (linear interpolation, matching pandas' default) as `py_metrics.py`,
so rows pool with no adapter step. `BuildClassInfo` extracts methods as
`BaseMethodDeclarationSyntax` (not `MethodDeclarationSyntax`) specifically
because C# constructors/destructors/operators are sibling node types, not
subtypes — missing this was a real caught bug that would have silently
dropped every constructor from NOM/WMC/LCOM. `ComputeLcom` carries the full
derivation for why a sampled subclass's `P−Q` is reported raw, not rescaled
(same catastrophic-cancellation reasoning as the Python side, independently
re-derived here). `StableSeed()` uses a hand-rolled FNV-1a hash rather than
`string.GetHashCode()`, since .NET randomizes the built-in hash per process
(hash-flooding hardening) — which would silently break run-to-run sampling
reproducibility.

### `SmellDetector.cs`

C# port of `py_smells.py` — same four Detection Strategies, same literature
constants, same corpus-relative percentile thresholds (including the
empirically-justified 10%/10% God Class revision, independently re-verified
on real C# data: WMC/TCC r=−0.743, same range as Python's). One real caught
bug during hand-validation: `MaxNestingLevel` initially never descended past
the method boundary (silently zeroing Brain Method's nesting condition)
until fixed to start walking from the method body directly, mirroring
`CcWalker.Compute`'s pattern. WOC/NOAM are explicitly adapted, not blindly
ported — idiomatic C# expresses most getters/setters as properties, not
explicit methods, so the "public methods" population includes public
properties.

### `EntityHistory.cs`

The RQ3 batch-mode extractor — given arbitrary `(relpath, text)` blobs from
git history (not a materialized snapshot), extracts each blob's class/method
inventory *including source text per entity* (no metrics computation at
all) so Python's `entity_matching.py` can tokenize it. Deliberately a
separate, self-contained pass rather than a refactor of
`SnapshotAnalyzer.cs`'s helpers — its qualified-name/method-name logic
intentionally duplicates `SnapshotAnalyzer`'s (same node types, same
Parent-chain walk) as a stated simplicity-over-DRY tradeoff, since
`SnapshotAnalyzer` is already validated and this needs a different output
shape entirely.

---

## Statistical analysis & visualization

### `src/analysis/segmented_regression.py`

Interrupted-time-series regression (`metric ~ intercept + slope_pre·T +
level_change·post + slope_change·(T·post)`), reconstructed from
`Results.md`'s own methodology prose since the original script that
produced the pilot's regression CSV was never committed. Closed-form OLS via
normal equations (no `statsmodels` dependency), 95% CI via the normal
approximation (`Z_975=1.96`, the textbook-rounded constant, confirmed by
reproduction rather than the precise value) while p-values use the
t-distribution. `validate_against_pilot()` is a **mandatory, blocking**
check — it must exactly reproduce the pilot's original 4-repo
coefficients/p-values/CIs (within float tolerance, with an explicit
documented exception for one genuinely zero-variance row) before
`run_full_corpus()` is trusted on new data.

### `src/viz/figures_common.py`

Shared palette (reused verbatim from `analyze_dock_designite.py`'s
established house style), rcParams, and every data loader this figure set
uses. Documents two real, load-bearing data-scope splits directly in its own
docstring: smell density has two differently-sourced/differently-validated
tiers (4-repo DPy/Designite pilot vs. the in-house Lanza & Marinescu
detector), and OO metrics have two *scope* tiers that are nonetheless the
*same*, validated-1:1 metric (r=0.997–0.999) — `attach_smell_source()` never
blends the two smell sources into one series without an explicit `source`
column.

### `src/viz/generate_track_a_figures.py`

Figs 1–6 and Tables 1–2 (structural-health small multiples, event-window
views, forest plots, composition stacked-area, LOC/CC before-after,
cross-language boxplots), each explicitly captioned by which data tier it
draws from. `make_fig1b_inhouse_small_multiples()`'s title is built
dynamically from the real repo/language counts specifically so it can't
silently go stale the way an earlier hardcoded "11 Python repos" caption
once did after `cs_smells.py` landed. Has a `run = main` alias for the
orchestrator.

### `src/viz/generate_churn_figures.py`

Figs 7–9 and Table 3 (paired churn-rate distribution, per-repo bars, pooled
before/after histogram) over `spans` entities only (existed before
intervention *and* touched again after) — every figure's caption restates
this selection-bias scope directly, since a `pre_only`/`post_created`
entity has nothing to compare. Fig 8 uses a symlog x-axis specifically
because a linear scale made 15+ of 18 repos' bars visually vanish next to
one confirmed outlier (`browser-use`'s mean pre-rate ~7.7). Requires
`--entity-history <path>` naming Part A's churn-column-enhanced CSV
explicitly — no auto-discovery, unlike every other stage.

---

## Shared infrastructure (`src/common/`)

### `resumable_run.py`

The done-keys/progress/error-file convention extracted out of three scripts
that had each independently reimplemented it byte-for-byte. `load_done_keys()`
treats *any* prior output file matching a tag glob as already-done
(deliberate — it's what lets parallel `--repo`-scoped runs share progress),
gated by an optional `schema_version` check against a `<stem>.runinfo.json`
sidecar so a fix that changes what "done" should mean can invalidate stale
rows by bumping a version constant rather than relying on someone manually
archiving old files. Files predating this tracking (no sidecar) are still
trusted, by design — additive protection, not retroactive invalidation.

### `parallel_repo.py`

Generic repo-level dispatch (`run_by_repo()`) shared by the three pool
scripts — `workers<=1` runs every group inline, sequentially, byte-identical
to pre-concurrency behavior; `workers>1` dispatches one `ProcessPoolExecutor`
worker per repo (processes, not threads, since the analyzers are CPU-bound
and threads wouldn't actually run concurrently under the GIL). `worker_fn`
must be a module-level function — a closure/lambda can't survive being
pickled to a child process.

### `exclusions.py`

Single registry (`results/repos/excluded_repos.csv`) replacing three
previously uncoordinated exclusion mechanisms — `scope=permanent` (a tool
can *never* handle this repo, e.g. `dotnet/aspire`'s `MSBuildWorkspace`
blocker) vs. `scope=per-run` (a scale workaround expected to be retired by a
real fix). `record_exclusion()` is idempotent — a `full_name` already
present keeps its first-recorded reason.

### `storage_lifecycle.py`

Identifies which `data/repo_cache/` clones (~430MB/repo average, confirmed
9.9GB across ~23 repos) are safe to reclaim — entity-history done for that
repo, not on `keep_cache.csv`'s opt-out list — and reports or deletes them.
Deletion is never automatic and never the default (`--confirm`-gated);
deliberately not wired into the pipeline's main flow at all, since a repo's
clone might be needed again after entity-history is "done" today (a wider
date grid, a raised `--max-files-per-repo`) — framed explicitly as a manual,
deliberate researcher action, not a pipeline side effect.

---

## Misc

### `src/rejection_analysis.py`

A 4-line docstring stub ("Ask a judge why a PR was rejected... The judge
will receive") — no implementation, evidently an unstarted placeholder for
an LLM-judge rejection-reason classifier.
