# Longitudinal Study Methodology: Repo Health Pre/Post AI-Agent Introduction

## Goal

Measure how repository structural health changes before vs. after AI coding
agents start contributing, using object-oriented metrics and design/implementation
smells as the outcome variables.

## Tools

**DPy** — [designite-tools.com/products-dpy](https://designite-tools.com/products-dpy).
Python code quality assessment tool. Detects architecture, design, implementation,
and ML-specific smells; computes class- and method-level OO metrics via static
analysis (no build step required).

**Designite (C#)** — same family of tool, same metric/smell taxonomy, for C# repos.

```bibtex
@inproceedings{Sharma2016,
  author = {Sharma, Tushar and Mishra, Pratibha and Tiwari, Rohit},
  title = {Designite: A Software Design Quality Assessment Tool},
  year = {2016},
  isbn = {9781450341530},
  publisher = {Association for Computing Machinery},
  address = {New York, NY, USA},
  url = {https://doi.org/10.1145/2896935.2896938},
  booktitle = {Proceedings of the 1st International Workshop on Bringing Architectural Design Thinking into Developers' Daily Activities},
  pages = {1–4},
  numpages = {4},
  series = {BRIDGE '16}
}
```

We select DPy/Designite because they're widely used in empirical software
engineering research, they perform static analysis directly on source (consistent
extraction across heterogeneous projects, no build configuration needed), and they
report both continuous OO metrics (LOC, cyclomatic complexity, WMC, fan-in/fan-out,
LCOM, DIT) and 27 categorized design/implementation smells (Long Method, Complex
Method, Cyclic Dependency, etc.) — giving multi-perspective coverage of
maintainability, not just a single index.

## Data source correction (2026-07-21)

Checked the actual AIDev dataset before building anything further on top of it,
because the original plan assumed it held full PR history per repo:

- `all_pull_request.parquet` contains **only agent-authored PRs** — the `agent`
  column is non-null on all 932,791 rows, no exceptions. There is no "human PR"
  data in AIDev at all.
- It only spans **2024-12-24 to 2025-07-30** (~7 months). Nothing before or after,
  confirmed both dataset-wide and for just our 235 candidate repos (3,332 rows,
  same window).

Consequence: AIDev cannot supply a pre-agent baseline, and it has zero rows
outside that 7-month band. It's useful only for (a) telling us which PRs in a
given repo are agent-authored and (b) giving us each repo's earliest
agent-authored PR, which we treat as a **candidate intervention point**. Anything
about repo state before or after that narrow window — the actual "before" and
"after" health snapshots — has to come from a fresh GitHub API / git pull per
repo, not from AIDev.

## Methods

### Intervention point: definition and how we obtained it

For each repo, the **intervention point** is its earliest agent-authored PR:

```
intervention_date = min(created_at) over all AIDev rows with that repo_id
```

regardless of which agent authored it (`Claude_Code`, `Copilot`, `Cursor`,
`Devin`, `OpenAI_Codex`). We can use AIDev for this specific purpose — finding
*when* the first agent PR happened — even though AIDev can't supply the
before/after health baseline itself (see the data source correction above).

How this was actually computed
([`repo_pr_selection.py`](../src/phase0/repo_pr_selection.py)):
1. Load the 235 candidate repos and AIDev's `all_pull_request.parquet`; filter
   AIDev to rows whose `repo_id` is in the candidate set (`build_pr_table`).
2. Group the resulting PR rows by `repo_id` and take `idxmin()` of
   `created_at_dt` within each group — the row index of that repo's earliest
   agent PR.
3. Flag that single row per repo as `is_intervention_pr = True`; every other
   agent PR for the repo is `False`.
4. The repo-summary step reads that flagged row's `created_at` back out as
   `intervention_date`, alongside `last_agent_pr_date` (max `created_at`) and
   a per-agent breakdown (dosage) for the repo.

Caveats, not yet implemented:
- **Robustness check**: this only catches agents AIDev attributes at the PR
  level. A repo could have used an agent informally (config files present, no
  PR-level attribution) before its first *AIDev-flagged* PR — not checked yet;
  would need the GitHub API to inspect repo tree history for agent-config
  artifacts (`CLAUDE.md`, `.github/copilot-instructions.md`, etc.).
- **Dosage**: intervention is treated as a single point-in-time event for the
  tracks below, but adoption is gradual. The per-agent breakdown already
  computed in the repo-summary CSV should enter the regression as a
  covariate, not just decide which PR counts as "first."

### Sampling tracks

Four tracks, split along two axes: **what** we're sampling (repo source tree
vs. PR events) and **where** we anchor the sampling grid (a fixed calendar
window shared by every repo, vs. a window centered on each repo's own
intervention point).

| | Fixed calendar window | Centered on intervention point |
|---|---|---|
| **Repo snapshot** | **A1** | **A2** |
| **PR sampling** | **B1** | **B2** |

**A1 — repo snapshot, monthly, fixed window.** One snapshot per repo per
calendar month across the full 2022-01-01 to 2026-03-31 study window (51
months): `git log --until=<1st of month>` on the default branch, checkout,
run DPy/Designite. Same calendar grid for every repo regardless of when its
own intervention point falls. This is the long-run trend line — catches
macro-level drift and any effects contemporaneous across repos (e.g. a
language/tooling shift), and gives the pre-period enough length to fit a
reliable baseline slope. No PR data, no GitHub API/token — just the clone URL
and local disk.

**A2 — repo snapshot, centered on intervention point.** Same mechanism
(`git log --until` + checkout + tool run), but the grid is defined relative to
each repo's own `intervention_date` instead of the calendar — **weekly**
snapshots from `intervention_date` ± 3 months, then **monthly** out to
`intervention_date` ± 12 months (defaults, not yet confirmed with the user).
Purpose: A1's calendar-month grid can land up to ~29 days from the actual
intervention date, which blurs the level-change estimate right at the
discontinuity; A2 exists specifically to resolve that jump precisely, and it
puts every repo on the same *event-time* axis (`months_since_intervention`),
which is what the segmented regression actually runs on.

**B1 — PR sampling, monthly 2-day window, fixed window.** For each of the 51
calendar months, a 2-day window at the start of the month (day 1–2 UTC),
sampling up to 10 PRs (by `created_at`) from the repo's full PR history — not
just AIDev, since AIDev has no data outside Dec 2024–Jul 2025. Cap 510
PRs/repo; under-10 months are flagged, not excluded. This is the process-
metrics backbone (PR size, merge latency, review activity) across the whole
window.

**B2 — PR sampling, centered on intervention point.** Instead of calendar
anchoring, take the **10 PRs immediately preceding** and **10 PRs immediately
following** the intervention PR itself (by `created_at`, ordered), regardless
of what calendar month they land in (default count, not yet confirmed).
Purpose: a clean, tightly-matched before/after comparison right at the event —
this is what feeds the PR-level `delta = after - before` analysis in
[UnitofAnalysis.md](UnitofAnalysis.md), uncontaminated by the months of drift a
calendar-anchored sample would include on either side.

**Staleness (A1/A2 only).** `git log --until=<target_date>` returns the latest
commit at or before that date, which can be arbitrarily old if the repo was
quiet — silently treating a stale commit as if it represented that month would
bias the snapshot toward "nothing changed" specifically in low-activity
periods, which may correlate with the intervention itself. Every A1/A2 row
therefore carries:
- `commit_date` — the actual committer date of the resolved commit.
- `staleness_days` — `target_date - commit_date`, in days.
- `is_stale` — `staleness_days > 45` (default threshold, not yet confirmed).
- `no_prior_commit` — true when no commit exists at or before `target_date`
  at all (grid point predates the repo, or predates the shallow-clone
  boundary), distinct from "stale" (a commit exists, it's just old).

`is_stale` is a flag, not a filter — stale snapshots stay in the manifest and
get excluded or down-weighted at analysis time (segmented regression step),
not silently dropped during extraction.

All four tracks key their output on `(repo_id, track, snapshot_date_or_pr_id,
commit_sha_or_pr_id)` so A1/A2 rows and B1/B2 rows can be told apart and
analyzed separately or pooled.

## Phase 1a: repo & PR picking pipeline (built 2026-07-21)

Before touching the GitHub API at scale, we needed to (a) confirm which of the
235 candidate repos actually have usable agent-PR signal in AIDev, and (b)
produce a first concrete artifact to pick the 5 (then 10) pilot repos from.
This phase needs no GitHub token — it only reads the AIDev parquet and the
existing candidate-repo CSV.

**Script:** [`src/phase0/repo_pr_selection.py`](../src/phase0/repo_pr_selection.py)

Steps (the intervention-point mechanics are detailed in Methods above; this is
the rest of what the script does):
1. Load the 235 candidate repos from
   `results/phase0/repos_07-21-500-pycsharp-1398_235.csv` (156 Python, 79 C#,
   already filtered to 500+ stars — see [Phase0-data.md](Phase0-data.md)).
2. Load `all_pull_request.parquet` and filter to rows whose `repo_id` is in the
   candidate set — every one of the 235 repos already has at least one
   agent-authored PR by construction (that's how the candidate list was built),
   so this filter doesn't drop any repos; it just pulls their agent-PR rows.
3. Flag each repo's intervention PR (see Methods) and build a per-repo summary:
   agent PR count, distinct-agent count, per-agent breakdown (dosage signal),
   intervention date, last agent-PR date.
4. Suggest a pilot set: stratified by language (Python/C#) in proportion to
   their share of the 235, ranked by agent PR count within each language (more
   agent-PR signal = easier to sanity-check the pipeline end-to-end).

**Output (`results/repos/`):**
- `07-21-aidev-agent-prs-3332.csv` — 3,332 PR-level rows (`id, repo_id,
  full_name, language, stars, agent, state, created_at, closed_at, merged_at,
  html_url, is_intervention_pr`) across all 235 repos.
- `07-21-repo-summary-235.csv` — one row per repo (`repo_id, full_name,
  language, stars, agent_pr_count, distinct_agents, agent_breakdown,
  intervention_date, last_agent_pr_date`).

**Suggested 5-repo pilot** (3 Python, 2 C#; ranked by agent PR count within
language):

| repo_id | full_name | language | agent PRs | intervention date |
|---|---|---|---|---|
| 710601088 | crewAIInc/crewAI | Python | 327 | 2024-12-27 |
| 283046497 | airbytehq/airbyte | Python | 218 | 2025-01-21 |
| 136202695 | mlflow/mlflow | Python | 91 | 2025-05-21 |
| 134182879 | wieslawsoltes/Dock | C# | 309 | 2025-06-25 |
| 696529789 | dotnet/aspire | C# | 169 | 2025-05-19 |

**Not yet built (needs a decision or a token first):**
- **Phase 1b** — full PR history pull per repo (Track B, for the 510-PR/repo
  monthly sample and the human-PR baseline). Needs `GITHUB_TOKEN` — unauthenticated
  is 60 req/hr, impractical at this scale. Blocked until the token is set; the
  fetch code should read it from the environment only, never hardcode it.

Phase 1c (Track A) is built — see below.

## Phase 1c: repo-snapshot pipeline (built 2026-07-21)

Resolves Track A1 and A2 (see Methods) into an actual manifest for the 5 pilot
repos: which commit represents each grid point, and how stale that commit is.
No GitHub API, no token — only each repo's clone URL and local disk.

**Script:** [`src/phase0/repo_snapshot_pipeline.py`](../src/phase0/repo_snapshot_pipeline.py)

Steps:
1. Read the pilot list from the repo-summary CSV already produced by
   `repo_pr_selection.py` (Phase 1a) — `results/repos/*-repo-summary-*.csv`,
   most recent by filename — rather than re-deriving the candidate universe
   here. (This is a fix made while building this script: it originally
   re-ran the Phase 1a candidate-loading logic directly, which broke the
   moment the underlying phase0 candidate-repo CSV got moved as part of an
   unrelated, concurrent reorganization of `results/phase0/` vs.
   `results/repos/`. Reading the already-saved summary decouples this
   pipeline from wherever that candidate-list file happens to live.)
2. For each pilot repo, clone once into `data/repo_cache/<owner>__<repo>/`
   (gitignored — see `.gitignore`) if not already cloned: `git clone
   --filter=blob:none --no-tags <url>` — a partial/blobless clone, so the
   full commit graph and trees download (needed for accurate `git log`
   traversal across the whole 2022–2026 window) but file *contents* are
   fetched lazily, only when something actually gets checked out later.
   Idempotent: reruns skip repos that are already cloned.
3. Build both grids for that repo: A1 (`monthly_grid`, the fixed 51-point
   calendar grid) and A2 (`intervention_grid`, centered on that repo's own
   `intervention_date` from the summary CSV: weekly ±3mo, monthly out to
   ±12mo, 45 points).
4. For every grid point in both grids, resolve the nearest commit at or
   before that date (`git log --until=<date> -1`) and record
   `commit_sha`, `commit_date`, `staleness_days`, `is_stale`
   (`staleness_days > 45`), and `no_prior_commit` (no commit exists at all
   before that date — see Methods → Staleness).
5. Concatenate all repos' rows into one manifest CSV.

**Windows-specific issue hit and fixed:** cloning `airbytehq/airbyte` and
`dotnet/aspire` initially failed mid-checkout with `Filename too long` —
both repos have deeply nested test-fixture paths that exceed Windows'
260-character `MAX_PATH`. Fixed by cloning with `-c core.longpaths=true`
(scoped to the single clone command, not a persisted git config change).
This didn't need the machine-wide Windows registry long-paths setting
(`HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled`, which
is off on this machine and would need admin rights to change) — git for
Windows' own long-path handling was sufficient. Now baked into
`clone_repo()` for every future clone.

**Output:** [`results/snapshots/07-21-repo-snapshot-manifest-480.csv`](../results/snapshots/07-21-repo-snapshot-manifest-480.csv)
— 480 rows (5 repos × 96: 51 A1 + 45 A2), columns `repo_id, full_name,
language, track, target_date, commit_sha, commit_date, staleness_days,
is_stale, no_prior_commit`.

| repo | rows | stale (A1/A2) | no prior commit | clone size |
|---|---|---|---|---|
| crewAIInc/crewAI | 96 | 0 | 22 | 668M |
| airbytehq/airbyte | 96 | 0 | 0 | 1.3G |
| mlflow/mlflow | 96 | 0 | 0 | 704M |
| wieslawsoltes/Dock | 96 | 4 | 0 | 18M |
| dotnet/aspire | 96 | 0 | 21 | 172M |

`no_prior_commit` rows are exactly what we'd expect, not a bug: crewAI and
aspire are both relatively young repos, so a chunk of the earliest 2022
calendar grid points (Track A1) predate the repo's own first commit — those
snapshots legitimately don't exist rather than being missing data. Dock's 4
stale points (Track A2, presumably in a quiet stretch near its intervention
date) are the kind of thing the `is_stale` flag exists to catch instead of
silently smoothing over.

**Not yet built:** actually running DPy/Designite against each resolved
commit (Phase 1d). Neither tool is installed in this environment — this
phase only produces the manifest (which commit represents which snapshot),
not the smell/metric output itself.

## Study design: interrupted time series, not a single pre/post snapshot

A single "before" vs. "after" snapshot is weak: repo health metrics drift as
codebases grow regardless of AI involvement, so a two-point comparison conflates
agent effects with ordinary evolution. Instead we treat this as an **interrupted
time series (ITS)**: sample each repo at regular intervals across a window before
and after the intervention point, then test for a change in *level* and *slope* at
the intervention. This distinguishes "smell density was already rising and kept
rising" from "smell density jumped when agents arrived."

<!-- Where possible, add a **matched non-adopting comparison arm** (repos with the same
filters — stars, contributors, language — that never show an `agent`-labeled PR in
the observation window), sampled on the same schedule. That upgrades the design to
**difference-in-differences**, which is a much stronger causal claim than ITS alone.

This repo-level trajectory analysis is complementary to, not a replacement for, the
PR-level delta analysis already sketched in [UnitofAnalysis.md](UnitofAnalysis.md)
(`delta = after - before` per individual refactoring instance, aggregated by
abstraction level and purpose category). The PR-level analysis answers "did this
specific agent PR change quality"; the repo-level ITS answers "did the repo's
overall trajectory bend after agents showed up." Both draw on the same DPy/Designite
metric catalog. -->

## Steps to complete

Intervention-point definition and the A1/A2/B1/B2 sampling tracks are covered
under Methods above. The remaining steps:

### 1. Snapshot extraction and tool pipeline
For each observation point (repo, snapshot_date, commit_sha):
- `git checkout` (or API tree fetch) the snapshot.
- Run DPy on Python files, Designite on C# files, matching the repo's dominant
  language (already filtered to Python/C++/C# — see
  [Phase0-data.md](Phase0-data.md)).
- Export smell + metric output (CSV/JSON) keyed by `(repo_id, snapshot_date, commit_sha)`.
- **Pin the tool version and threshold config for the entire study** and archive it
  — both tools' default thresholds change between releases, which would silently
  contaminate the time series.
- Record LOC coverage of the analyzed language per snapshot, so mixed-language
  snapshots with trivial coverage can be excluded or flagged.

### 2. Metric catalog to extract
**Structural (DPy/Designite output):**
- Smell density, not raw counts, per granularity: design smells / KLOC,
  implementation smells / KLOC, architecture smells / component.
- OO metric distributions per snapshot (median + p90, not mean — these are
  heavy-tailed): LOC/class, LOC/method, cyclomatic complexity, WMC, DIT,
  fan-in/fan-out, LCOM.
- Smell composition: does the mix shift (e.g., fewer implementation smells,
  more design smells) as agents optimize locally rather than architecturally?
- Smell survival: match individual smell instances across snapshots (by entity +
  smell type) to separate introduction rate from removal rate. Net density can
  stay flat while churn doubles.

**Process (GitHub API), per interval:**
- Commit frequency, median PR size (LOC changed), PR merge latency, review comment
  counts, reverted-commit rate, issue open/close ratio, contributor concentration
  (bus factor).

**Normalization covariates:**
- Total LOC, file count, contributor count, repo age at snapshot. These enter the
  regression models, not just the descriptives.

### 3. Analysis plan
- Segmented regression per metric:
  `metric ~ time + intervention + time_since_intervention + covariates`,
  repo random effects when pooling across repos. Report the level-change
  coefficient (on `intervention`) and slope-change coefficient (on
  `time_since_intervention`) separately.
- Pre-register a small primary metric set to avoid multiple-comparison fishing —
  candidates: design smell density, implementation smell density, p90 cyclomatic
  complexity. Treat everything else as exploratory with FDR correction.
- If the matched comparison arm is available, run as difference-in-differences
  instead of plain ITS.

### 4. Threats to validity to design around now
- **Selection**: repos that adopt agents may differ systematically from those that
  don't → mitigated by the matched comparison arm (step 3).
- **Detection confounding**: agents may move code across a smell's threshold
  without changing real quality → mitigated by freezing the threshold config
  (step 1) and reporting effect sizes on raw underlying metrics, not just smell
  counts.

## Decisions log
- **2026-07-21** — Window fixed at 2022-01-01 to 2026-03-31 (51 months), not
  ±12 months centered per-repo. AIDev used only to find each repo's
  intervention point, not for full history. GitHub token required before
  Phase 1b (full PR pull) starts — unauthenticated is not viable at this scale.
  Track B sampling anchors on `created_at`; under-10-PR months are flagged, not
  excluded.
- **2026-07-21** — Split Track A and Track B each into a fixed-calendar variant
  and an intervention-point-centered variant (A1/A2, B1/B2), since a single
  calendar grid per track can't give both a long-run trend line and a precise
  read on the discontinuity itself. See Methods for definitions.
- **2026-07-21** — Pilot repo set confirmed by proceeding with it (crewAI,
  airbyte, mlflow, Dock, aspire): all 5 successfully cloned and snapshotted in
  Phase 1c. `repo.py` and `phase1.py` reconciled to both default to the
  1398-PR list (were pointing at different PR-id lists, 1398 vs. 1434 - both
  happened to cover all 5 pilot repos, but left as-is it would have caused
  confusion later).

## Open decisions
- Whether informal agent use (the robustness check under Methods ›
  Intervention point) is common enough in this dataset to matter, or whether
  the PR-`agent` column is sufficient on its own.
- A2's weekly-±3mo/monthly-±12mo grid and B2's ±10-PR window are defaults, not
  confirmed — may need to change per repo based on how dense each repo's own
  history actually is around its intervention point.
- Minimum snapshot count per repo before it's excluded from the ITS regression
  (relevant now that crewAI/aspire show 21-22 `no_prior_commit` A1 points out
  of 96 each — real absence of history, not a bug, but the regression needs a
  rule for how much of that a repo can have before it's excluded).
- Exact source for GitHub token (env var `GITHUB_TOKEN`, confirmed with user;
  not yet set in this environment) — still blocks Phase 1b.
- Phase 1d (actually running DPy/Designite on each resolved snapshot) needs
  both tools installed; neither is available in this environment yet.

## Artifacts
- `results/repos/07-21-aidev-agent-prs-3332.csv` — AIDev PR rows for the 235
  candidate repos, intervention PR flagged (Phase 1a, done).
- `results/repos/07-21-repo-summary-235.csv` — per-repo agent-PR summary used
  to pick the pilot (Phase 1a, done).
- `results/snapshots/07-21-repo-snapshot-manifest-480.csv` — Track A1/A2
  commit-resolution manifest for the 5 pilot repos, with staleness (Phase 1c,
  done).
- Track A1/A2 metric output: design/implementation smell count and OO metrics
  per snapshot, keyed by `(repo_id, track, target_date, commit_sha)` — needs
  Phase 1d (DPy/Designite installed and run against the Phase 1c manifest),
  not yet built.
- Track B1/B2 output: PR-level process metrics and delta table (see
  [UnitofAnalysis.md](UnitofAnalysis.md)) keyed by `(repo_id, track, pr_id)`
  (Phase 1b, not yet built).
- Segmented regression output per primary metric (level change, slope change).
