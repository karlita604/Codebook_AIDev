# Longitudinal Study Methodology: Repo Health Pre/Post AI-Agent Introduction

## 1. Goal

Measure how repository structural health changes before vs. after AI coding
agents start contributing, using object-oriented metrics and design/implementation
smells as the outcome variables.

## 2. Why this design

**A single before/after snapshot is too weak.** Repo health metrics drift as
codebases grow regardless of AI involvement, so a two-point comparison
conflates an agent effect with ordinary evolution. We need an **interrupted
time series (ITS)**: sample a repo repeatedly across a window before and
after the moment agents arrive, then test for a change in *level* and
*slope* at that moment — the difference between "this was already trending
up and kept trending up" and "this jumped when agents arrived."

**AIDev can only tell us *when*, not *before/after*.** The dataset we're
drawing agent-PR data from (`hao-li/AIDev`) turns out to contain *only*
agent-authored PRs, in a ~7-month window (2024-12-24 to 2025-07-30) — see
§3. It has no pre-agent baseline and nothing outside that window. So AIDev's
one real job in this design is telling us **when** each repo's agents
showed up (its *intervention point*, §4) — the actual before/after health
data has to come from our own git history pull.

**One grid can't do both jobs well.** Once we're pulling our own history, we
still need two different resolutions:
- A **fixed calendar grid**, shared across every repo, is what makes repos
  comparable to each other and gives a stable long-run trend line.
- But a calendar grid's nearest sample point can land up to a month away
  from the actual moment agents arrived — too coarse to see the
  discontinuity itself. That needs a **grid centered on that repo's own
  intervention point**, at finer resolution right around it.

And separately, health metrics (from repo source) and process metrics (from
PR activity) are different kinds of data with different collection costs —
one needs only a git clone, the other needs the GitHub API. So the design
splits along **two independent axes** — *what* is sampled (repo source tree,
vs. PR events) × *where* the grid is anchored (fixed calendar, vs. centered
on the intervention point) — giving **four tracks**, A1/A2/B1/B2, detailed
in §5.

## 3. Data sources

**AIDev** (`hao-li/AIDev` on Hugging Face) — checked before building anything
on top of it, because the original plan assumed it held full PR history per
repo. It doesn't:
- `all_pull_request.parquet` contains **only agent-authored PRs** — the
  `agent` column is non-null on all 932,791 rows, no exceptions.
- It only spans **2024-12-24 to 2025-07-30**. Nothing before or after,
  confirmed both dataset-wide and for our 235 candidate repos (3,332 rows,
  same window).

So AIDev supplies exactly one thing for this study: each repo's earliest
agent-authored PR, i.e. its intervention point (§4). Everything about repo
state before or after that narrow window — the actual health snapshots —
comes from a fresh git pull per repo, not from AIDev.

**DPy** — [designite-tools.com/products-dpy](https://designite-tools.com/products-dpy),
for Python repos. **Designite (C#)** — same family of tool, same
metric/smell taxonomy, for C# repos. Selected because they're widely used in
empirical SE research, perform static analysis directly on source (no build
step, consistent across heterogeneous projects), and report both continuous
OO metrics (LOC, cyclomatic complexity, WMC, fan-in/fan-out, LCOM, DIT) and
27 categorized design/implementation smells — multi-perspective coverage of
maintainability, not a single index.

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

## 4. Intervention point

**Definition.** For each repo, the intervention point is its earliest
agent-authored PR:

```
intervention_date = min(created_at) over all AIDev rows with that repo_id
```

regardless of which agent authored it (`Claude_Code`, `Copilot`, `Cursor`,
`Devin`, `OpenAI_Codex`).

**How it's computed**
([`repo_pr_selection.py`](../src/phase0/repo_pr_selection.py)): load the
candidate repos and AIDev's `all_pull_request.parquet`; filter AIDev to rows
whose `repo_id` is in the candidate set; group by `repo_id` and take the row
with the minimum `created_at` in each group; flag that row
`is_intervention_pr = True`.

**Where it's stored:** `results/repos/*-repo-summary-*.csv`, one row per
repo, column `intervention_date` (alongside `last_agent_pr_date` and a
per-agent PR-count breakdown — the dosage signal, see below). The full
per-PR detail (every agent PR, not just the intervention one) is in
`results/repos/*-aidev-agent-prs-*.csv`.

**Caveats, not yet implemented:**
- **Robustness check**: this only catches agents AIDev attributes at the PR
  level. A repo could have used an agent informally (config files present,
  no PR-level attribution) before its first AIDev-flagged PR — would need
  the GitHub API to check repo tree history for agent-config artifacts
  (`CLAUDE.md`, `.github/copilot-instructions.md`, etc.).
- **Dosage**: intervention is treated as a single point-in-time event for
  the tracks in §5, but adoption is gradual. The per-agent breakdown already
  computed should enter the regression as a covariate, not just decide which
  PR counts as "first."

## 5. The four sampling tracks

|  | Repo source tree | PR events |
|---|---|---|
| **Fixed calendar grid** | **A1** | **B1** |
| **Centered on intervention point** | **A2** | **B2** |

Each track answers a different question and is stored separately, keyed by
`(repo_id, track, ...)` so rows are never ambiguous about which track they
belong to.

### A1 — repo snapshot, monthly, fixed calendar grid

- **Samples:** the repo's source tree.
- **Grid:** one point per calendar month, 2022-01-01 to 2026-03-31 (51
  points), identical across every repo regardless of its own intervention
  date.
- **Why it matters:** the long-run trend line. Catches macro-level drift and
  anything contemporaneous across repos (a language/tooling shift), and
  gives the pre-period enough length to fit a reliable baseline slope.
- **Resolved via:** nearest commit at or before each grid date
  (`git log --until=<date> -1` on the default branch).
- **Stored:** the *manifest* (which commit resolves each point) is in
  `results/snapshots/*-repo-snapshot-manifest-*.csv`, one row per
  `(repo_id, track='A1', target_date)`. The *materialized source* for each
  resolved commit is under `data/snapshots/` — see §7; this is the part
  still being built.

### A2 — repo snapshot, centered on the intervention point

- **Samples:** the repo's source tree (same mechanism as A1).
- **Grid:** relative to that repo's own `intervention_date` — weekly for
  ±3 months, then monthly out to ±12 months (45 points; defaults, not yet
  confirmed).
- **Why it matters:** A1's calendar grid can land up to ~29 days from the
  actual intervention date, which blurs the level-change estimate right at
  the discontinuity. A2 resolves that jump precisely, and puts every repo on
  the same *event-time* axis (`months_since_intervention`) — what the
  segmented regression (§9) actually runs on.
- **Resolved via / stored:** same as A1 — same manifest file, rows with
  `track='A2'`.

### B1 — PR sampling, monthly 2-day window, fixed calendar grid

- **Samples:** PR events (who authored it, when, diff size, review
  activity) — not source code.
- **Grid:** for each of the 51 calendar months, a 2-day window at the start
  of the month (day 1–2 UTC), up to 10 PRs by `created_at`. Cap 510
  PRs/repo. Pulled from the repo's **full** PR history (the GitHub API, not
  AIDev — AIDev has no PR data outside Dec 2024–Jul 2025). Months with fewer
  than 10 PRs in the window keep whatever's available and get flagged as
  under-sampled, rather than being excluded or padded.
- **Why it matters:** the process-metrics backbone (PR size, merge latency,
  review activity) across the whole window — this is what lets us tell
  "development changed" apart from "code got worse."
- **Status:** not yet built (**Phase 1b**) — needs `GITHUB_TOKEN`;
  unauthenticated GitHub API access is 60 req/hr, not viable at this scale.
- **Will be stored:** keyed by `(repo_id, track='B1', pr_id)`, location TBD
  once built.

### B2 — PR sampling, centered on the intervention point

- **Samples:** PR events, same as B1.
- **Grid:** the 10 PRs immediately preceding and the 10 immediately
  following the intervention PR itself (by `created_at`, ordered) — not
  calendar-anchored (default count, not yet confirmed).
- **Why it matters:** a clean, tightly-matched before/after comparison right
  at the event, uncontaminated by the months of drift a calendar-anchored
  sample would include on either side. Feeds the PR-level
  `delta = after - before` analysis sketched in
  [archive/UnitofAnalysis.md](archive/UnitofAnalysis.md) (superseded draft,
  kept for historical reference).
- **Status:** not yet built (**Phase 1b**, same blocker as B1).
- **Will be stored:** keyed by `(repo_id, track='B2', pr_id)`, location TBD.

## 6. Staleness (A1/A2 only)

`git log --until=<target_date>` returns the latest commit at or before that
date — which can be arbitrarily old if the repo was quiet. Silently treating
a stale commit as if it represented that month would bias the snapshot
toward "nothing changed," specifically in low-activity periods that may
correlate with the intervention itself. Every A1/A2 manifest row therefore
carries:

| column | meaning |
|---|---|
| `commit_date` | actual committer date of the resolved commit |
| `staleness_days` | `target_date - commit_date`, in days |
| `is_stale` | `staleness_days > 45` (default threshold, not yet confirmed) |
| `no_prior_commit` | no commit exists at all before `target_date` — the grid point predates the repo, distinct from "stale" (a commit exists, it's just old) |

`is_stale` is a flag, not a filter: stale snapshots stay in the manifest and
get excluded or down-weighted at analysis time (§9), not silently dropped
during extraction.

## 7. Storing the actual snapshot content

The manifest (§5, §6) only records *which commit* represents each grid
point — it doesn't contain source code. Running DPy/Designite needs the
actual source tree at that commit, so this is the next thing to build:
materializing each manifest row's resolved commit into an actual directory
of source files.

**Design:**
- **Dedup by commit, not by manifest row.** Across the 5 pilot repos, 437 of
  480 manifest rows resolve to a commit at all, but only **401 are unique**
  — several grid points (mostly in quiet stretches) resolve to the same
  commit. Materialize each unique `(repo, commit_sha)` once, not once per
  manifest row.
- **Language-filtered, not a full checkout.** DPy/Designite only read one
  language's source (Python or C#, matching the repo) — a full checkout
  would pull in test fixtures, data files, docs, and other repo bulk that
  the tools never touch and that (for repos like `airbyte`) is most of the
  repo's size. Extract with a pathspec limited to the relevant extension:
  `git archive <sha> -- '*.py'` (or `*.cs`).
- **Storage layout:** `data/snapshots/<owner>__<repo>/<commit_sha>/` —
  gitignored alongside `data/repo_cache/` (see `.gitignore`).

**Implementation wrinkles hit while building this:**
- The clones in `data/repo_cache/` are partial (`--filter=blob:none` — see
  Phase 1c, §8): full commit/tree history but no file *contents*, which is
  exactly what made the manifest step in §5/§6 fast. That same choice
  initially worked against this step: `git archive` against a partial clone
  triggers a lazy fetch of every missing blob it touches, one request at a
  time — slow enough to time out even on a single medium-sized repo
  (crewAI). Fix: `git sparse-checkout` set to the language pathspec, then a
  one-time `git backfill --sparse` per repo (bulk-fetches every blob
  matching that pathspec across all history in one pass) before archiving
  anything. After that, individual `git archive` calls are fast (seconds).
- The backfill/archive transfers themselves hit a recurring connection reset
  (`RPC failed; curl 56 schannel: server closed abruptly`) on longer HTTPS
  fetches — an environment-specific TLS transport issue, not a data
  problem. Fixed by forcing `-c http.version=HTTP/1.1` on both the backfill
  and archive commands.
- First materialization pass silently "succeeded" on 14 commits that were
  actually empty — `archive_commit()` created the destination directory
  before knowing whether the archive itself succeeded, so a failed attempt
  still passed the idempotency check on the next run. Fixed by extracting
  into a `.tmp` sibling dir and only renaming it into place once both the
  `git archive` and `tar` processes exit clean and it's non-empty; the
  "already done" check now requires the directory to exist *and* be
  non-empty, not just exist.
- A handful of retried renames hit a transient Windows `PermissionError`
  (`WinError 5: Access is denied`) — a file handle briefly still held by AV
  scanning or search indexing right after `tar` closes it. Fixed with a
  short retry loop around the rename.

**Status:** done — see Phase 1e in §8.

## 8. Build log

### Phase 1a — repo & PR picking (built 2026-07-21)

[`repo_pr_selection.py`](../src/phase0/repo_pr_selection.py): loads the
candidate repo list, pulls AIDev's agent PRs for those repos, flags each
repo's intervention PR (§4), and builds the per-repo summary. No GitHub
token needed — only the AIDev parquet and the candidate-repo CSV.

**Output (`results/repos/`):** `*-aidev-agent-prs-*.csv` (per-PR),
`*-repo-summary-*.csv` (per-repo, this is where `intervention_date` lives).

**5-repo pilot**, stratified by language, proceeded with:

| repo | language | agent PRs | intervention date |
|---|---|---|---|
| crewAIInc/crewAI | Python | 327 | 2024-12-27 |
| airbytehq/airbyte | Python | 218 | 2025-01-21 |
| mlflow/mlflow | Python | 91 | 2025-05-21 |
| wieslawsoltes/Dock | C# | 309 | 2025-06-25 |
| dotnet/aspire | C# | 169 | 2025-05-19 |

### Phase 1c — repo-snapshot manifest (built 2026-07-21)

[`repo_snapshot_pipeline.py`](../src/phase0/repo_snapshot_pipeline.py):
resolves Tracks A1/A2 (§5) into the manifest, for the 5 pilot repos. Clones
each repo once into `data/repo_cache/<owner>__<repo>/` (partial —
`--filter=blob:none --no-tags`, gitignored, idempotent — reruns skip
already-cloned repos), builds both grids, and resolves the nearest commit +
staleness (§6) for every grid point.

**Windows-specific issue hit and fixed:** `airbyte` and `aspire` initially
failed mid-checkout with `Filename too long` (deeply nested test-fixture
paths past Windows' 260-char `MAX_PATH`). Fixed with `-c core.longpaths=true`
scoped to the clone command — didn't need the machine-wide Windows registry
long-paths setting (off on this machine, needs admin rights).

**Output:** [`results/snapshots/07-21-repo-snapshot-manifest-480.csv`](../results/snapshots/07-21-repo-snapshot-manifest-480.csv)
— 480 rows, columns `repo_id, full_name, language, track, target_date,
commit_sha, commit_date, staleness_days, is_stale, no_prior_commit`.

| repo | rows | stale | no prior commit | unique commits | clone size |
|---|---|---|---|---|---|
| crewAIInc/crewAI | 96 | 0 | 22 | 71 | 668M |
| airbytehq/airbyte | 96 | 0 | 0 | 95 | 1.3G |
| mlflow/mlflow | 96 | 0 | 0 | 96 | 704M |
| wieslawsoltes/Dock | 96 | 4 | 0 | 64 | 18M |
| dotnet/aspire | 96 | 0 | 21 | 75 | 172M |

`no_prior_commit` rows are expected, not a bug: crewAI and aspire are young
enough that early-2022 grid points predate their first commit. Dock's 4
stale points (all Track A1, all far from its intervention date) are exactly
what the `is_stale` flag exists to catch.

### Phase 1e — snapshot materialization (built 2026-07-26)

[`materialize_snapshots.py`](../src/phase0/materialize_snapshots.py):
implements §7 — for every unique `(repo, commit_sha)` in the Phase 1c
manifest, backfills that repo's language-matching blobs once
(`git sparse-checkout` + `git backfill --sparse`, HTTP/1.1 forced), then
extracts each commit with a language-filtered `git archive` into
`data/snapshots/<owner>__<repo>/<commit_sha>/`. Resumable by design — rerun
with `--repo <full_name>` (or no argument, for all repos) and it only
processes what's still missing.

**Output:** `data/snapshots/`, 399 of 401 unique commits materialized:

| repo | materialized | disk |
|---|---|---|
| crewAIInc/crewAI | 69 / 71 | 136M |
| airbytehq/airbyte | 95 / 95 | 1.8G |
| mlflow/mlflow | 96 / 96 | 1.5G |
| wieslawsoltes/Dock | 64 / 64 | 139M |
| dotnet/aspire | 75 / 75 | 1.2G |

The 2 crewAI commits that never materialize are a genuine Windows
filesystem incompatibility, not a transient failure: both trees contain
`tests/cassettes/test_agent_tool_role_matching[  "Futel Official Infopoint"  -True].yaml`,
whose `"` character is illegal in an NTFS filename. Re-running consistently
reproduces the exact same `invalid path` / `failed to unpack tree object`
error for just these two, with no other errors alongside — everything else
that failed on earlier passes (connection resets, a transient Windows file
lock) cleared on retry. These two would need a Linux/WSL environment to
materialize; on this machine they're a known, disclosed gap in Track A2 for
crewAI specifically (2 of its 45 A2 points).

One more wrinkle: the `airbyte` clone from Phase 1c (confirmed at 1.3G
earlier in this same work) was gone by the time this step ran — removed by
something outside this pipeline between phases. Re-cloned it (same
`clone_repo()` helper, already has the long-path fix) rather than treating
it as blocking, since `data/repo_cache/` is disposable, gitignored cache
data by design.

### Phase 1d — DPy/Designite orchestration (built 2026-07-27, blocked on tool install)

[`long_analysis.py`](../src/phase0/long_analysis.py): reads the Phase 1c
manifest, drops `no_prior_commit` rows, and for each remaining row looks up
its materialized source tree from Phase 1e
(`data/snapshots/<owner>__<repo>/<commit_sha>/`), routes to DPy (Python) or
Designite (C#) by `language`, and writes a consolidated smell/metric CSV plus
a separate errors CSV (one bad row doesn't abort the run). `run_dpy()` /
`run_designite()` / `parse_tool_output()` are stubs marked `TODO`, gated
behind `DPY_EXECUTABLE`/`DESIGNITE_EXECUTABLE` env vars — neither tool is
installed in this environment (no `dpy`/`designite`/even `java` present),
and both are commercial products whose real CLI/output schema I haven't
verified, so the actual tool invocation isn't implemented yet. `--dry-run`
(snapshot lookup + bookkeeping only) and `--repo`/`--limit` filters let the
orchestration itself be smoke-tested without the tools.

First version checked out each commit directly in the Phase 1c clone cache
instead of reading Phase 1e's output — built before noticing Phase 1e (§7,
§8) already existed and already solved the exact problem that approach then
hit (a slow lazy blob-fetch on `airbyte`'s partial clone timed out mid-run
and left that cache half-updated). Rewritten to consume `data/snapshots/`
directly, matching the design this doc already specified.

**Result:** full `--dry-run` across all 5 repos resolves 435/437 eligible
rows instantly — no network, no checkout, just a directory lookup — with the
2 failures being exactly the 2 known-unmaterialized crewAI commits (§8),
cleanly logged to the errors CSV.

**Update 2026-07-27 — both tools installed, two new concrete blockers.**
`DPy.exe` and `DesigniteConsole.exe` are now installed
(`C:\Users\kvrlv\Downloads\`). `run_dpy()`'s CLI is now confirmed for real
(`DPy.exe analyze -i <dir> -o <dir> -f csv`) and wired in — verified against
both a real `mlflow` snapshot and a tiny synthetic file, which gave the
confirmed CSV schema now documented in `parse_tool_output()`'s docstring
(`_class_module_metrics.csv`, `_function_metrics.csv`,
`_implementation_smells.csv`). But neither tool can produce real pilot-scale
output yet:
- **DPy** — Trial license caps CSV export at <10,000 LOC. Every pilot
  snapshot is far over that (smallest ~60K LOC: a Dock A1 point), so it only
  writes a log file against real data. Needs Professional.
- **Designite** — `-i`/`--input` requires an actual `.sln` (it's Roslyn
  `MSBuildWorkspace`-based, confirmed via its `BuildHost-net472`/`netcore`
  DLLs), not a plain source scanner. Pointing it directly at a materialized
  Dock snapshot fails immediately (`Argument error!! The specified file
  doesn't exists`), since Phase 1e only archives `*.cs` files, no
  `.sln`/`.csproj`. Also no .NET SDK is installed here, only runtimes, which
  `MSBuildWorkspace` may need regardless. `run_designite()` now raises a
  clear `NotImplementedError` explaining this instead of attempting a call
  already known to fail. Needs a design decision: re-materialize C# repos
  with project/solution files included (and get the SDK installed), or find
  a Designite input mode that accepts loose files (undocumented "batch file"
  mode, meaning unconfirmed).

**Update 2026-07-28 — Designite confirmed working for Dock; aspire dropped
from the C# arm.** Done in a separate worktree/branch
(`Codebook_AIDev-designite`) to avoid touching the DPy job running on `main`.
- .NET SDK 8.0.423 installed (was runtimes-only before). `materialize_snapshots.py`'s
  C# pathspec extended from `*.cs`-only to also pull `*.sln`, `*.slnx`,
  `*.csproj`, `*.props`, `*.targets`, `packages.config`.
- Found and fixed a real bug this surfaced: `git archive` (unlike
  `ls-tree`/checkout) hard-fails (exit 128) if *any* given pathspec pattern
  matches zero files in that commit's tree - no `--ignore-unmatch` exists for
  `archive`. A fixed multi-extension pathspec was guaranteed to hit this
  per-commit (e.g. Dock has no `.sln` at all after its 2025-12-25 migration to
  `.slnx`, commit `b8fb130d`). Fixed via `_present_patterns()`, which filters
  the pathspec down to patterns that actually match something in that
  specific commit before archiving - matching against full relative paths,
  not basenames, since git's own literal (non-wildcard) pathspec matching
  (e.g. `packages.config`) is a top-level-path match, not a basename match at
  any depth (caught on aspire's `eng/common/sdl/packages.config`, which a
  basename-based filter would have wrongly kept, only for `git archive`
  itself to then reject it).
- **Dock**: `DesigniteConsole.exe` opens and analyzes a real historical
  `.sln` cleanly (confirmed on both a 2022 and a 2026 commit) - the original
  blocker is resolved. Two caveats found:
  - Trial license caps CSV export at **<50,000 LOC per invocation** (a
    different, higher threshold than DPy's 10K) - a 58K-LOC Dock commit ran
    the full analysis and printed a summary to stdout but wrote zero CSVs; a
    13K-LOC commit exported fully. Same shape of problem as DPy's cap, likely
    needs an analogous workaround eventually.
  - This DesigniteConsole build (5.3.0.0) does not support `.slnx` at all
    ("could not find any project to analyze") - so Dock commits after its
    2025-12-25 `.sln` → `.slnx` migration are currently unanalyzable too,
    until either a newer Designite build is installed or `.slnx` is
    converted back to `.sln` before analysis.
  - Output shape confirmed: one set of 8 CSVs *per project in the solution*
    (`ClassMetrics`, `MethodMetrics`, `NamespaceMetrics`, `DesignSmells`,
    `ImpSmells`, `ArchSmells`, `TestabilitySmells`, `TestSmells`) plus one
    `Designite_AnalysisSummary.csv` - a different shape than DPy's
    single-set-per-run output. Some projects appear multiple times under
    different config/TFM-suffixed names (multi-targeting) - pooling logic
    will need to de-dup/handle this deliberately, not just concatenate.
- **aspire: dropped from the C# arm for now** (decision made 2026-07-28).
  Investigated both ends of its history and found two *different* blockers,
  not one:
  - Early commit (2023-10, pre-1.0): `.sln` opens without crashing, but every
    project reports "no source files found" (0 LOC). Confirmed via `dotnet
    restore`: `NuGet.targets error: Invalid framework identifier ''` - aspire
    bootstraps via Arcade (`global.json` pins a prerelease SDK version +
    `Microsoft.DotNet.Arcade.Sdk`), needing its own `restore.cmd`/private
    feed setup, not a plain `dotnet restore`/MSBuildWorkspace open.
  - Recent commit (2026-05): uses `.slnx` (same unsupported-format problem as
    Dock's recent history) **and** pins .NET SDK 10.0.201 (preview, not
    installed, fetched by the repo's own local-install script).
  - No confirmed "clean middle band" of aspire history was found (not
    exhaustively searched - just the two ends). Full support would mean
    replicating aspire's own CI bootstrap per historical commit (multiple
    pinned prerelease SDKs, private feeds) - out of scope for the current
    pilot phase. `EXCLUDED_REPOS` in `materialize_snapshots.py` (imported by
    `long_analysis.py`) is the actual exclusion mechanism, applied generically
    (not aspire-specific) so any future repo needing similar exclusion has
    somewhere to go, and so this is trivially reversible once revisited.
    Aspire's exploration artifacts (materialized snapshots, test Designite
    output) were moved to `data/archive/dotnet__aspire_2026-07-28/` rather
    than deleted.
  - C# arm is Dock-only until this is revisited.
- `run_designite()`/`parse_tool_output()` are still stubs - next step is
  wiring them up for real against Dock (schema above), including a design
  for the Trial LOC cap (Designite operates at the *solution* level, not a
  raw source directory, so a naive port of DPy's directory-chunking approach
  won't work as-is).

### Not yet built

- **Phase 1b** — Tracks B1/B2 (§5). Blocked on `GITHUB_TOKEN`.
- **Phase 1d tool execution** — orchestration is built (above) and DPy's CLI
  is wired in, but a Trial license blocks real DPy output and Designite
  needs a `.sln` Phase 1e doesn't currently produce - see Update above
  yet.

## 9. Metric catalog & analysis plan

**Structural (DPy/Designite output):**
- Smell density, not raw counts, per granularity: design smells / KLOC,
  implementation smells / KLOC, architecture smells / component.
- OO metric distributions per snapshot (median + p90, not mean — heavy-tailed):
  LOC/class, LOC/method, cyclomatic complexity, WMC, DIT, fan-in/fan-out, LCOM.
- Smell composition: does the mix shift (fewer implementation smells, more
  design smells) as agents optimize locally rather than architecturally?
- Smell survival: match individual smell instances across snapshots (entity +
  smell type) to separate introduction rate from removal rate — net density
  can stay flat while churn doubles.

**Process (from B1/B2, once built), per interval:** commit frequency, median
PR size, PR merge latency, review comment counts, reverted-commit rate, issue
open/close ratio, contributor concentration (bus factor).

**Normalization covariates:** total LOC, file count, contributor count, repo
age at snapshot — enter the regression models, not just the descriptives.

**Analysis plan:**
- Segmented regression per metric:
  `metric ~ time + intervention + time_since_intervention + covariates`,
  repo random effects when pooling. Report the level-change coefficient (on
  `intervention`) and slope-change coefficient (on `time_since_intervention`)
  separately.
- Pre-register a small primary metric set to avoid multiple-comparison
  fishing — candidates: design smell density, implementation smell density,
  p90 cyclomatic complexity. Everything else exploratory, FDR-corrected.
- Matched non-adopting comparison arm (repos with the same filters that never
  show an agent PR, sampled on the same schedule), if available, upgrades
  this from ITS to difference-in-differences — a stronger causal claim.

**Threats to validity:**
- **Selection** (repos that adopt agents may differ systematically) →
  mitigated by the matched comparison arm above.
- **Detection confounding** (agents may move code across a smell's threshold
  without changing real quality) → mitigated by freezing the tool's
  threshold config for the whole study and reporting effect sizes on raw
  underlying metrics, not just smell counts.
- **Pin the tool version and threshold config for the entire study.** Both
  tools' defaults change between releases — archive the config used.
- Record LOC coverage of the analyzed language per snapshot so mixed-language
  snapshots with trivial coverage can be flagged/excluded.

## 10. Decisions log

- **2026-07-21** — Window fixed at 2022-01-01 to 2026-03-31 (51 months), not
  ±12 months centered per-repo. AIDev used only to find each repo's
  intervention point, not for full history.
- **2026-07-21** — Split each of Track A and Track B into a fixed-calendar
  variant and an intervention-centered variant (A1/A2, B1/B2) — a single
  grid per track can't give both a long-run trend and a precise read on the
  discontinuity.
- **2026-07-21** — Pilot set confirmed by proceeding with it (crewAI,
  airbyte, mlflow, Dock, aspire); all 5 cloned and snapshotted in Phase 1c.
- **2026-07-22** — Snapshot storage: dedup by unique commit (401 across the 5
  repos, not 480), extract with a language-filtered `git archive` pathspec
  rather than a full checkout, store under `data/snapshots/`.
- **2026-07-26** — Snapshot materialization (Phase 1e) complete: 399/401
  unique commits, across all 5 pilot repos. The partial-clone lazy-fetch
  problem from §7 was solved with `git sparse-checkout` + `git backfill
  --sparse` (one bulk fetch per repo) plus forcing HTTP/1.1, not by
  switching to full clones as originally planned when §7 was first
  written — see §7 and Phase 1e (§8) for what actually worked. The 2 unmaterialized
  crewAI commits are a permanent Windows filename incompatibility, not
  something a retry fixes.
- **2026-07-27** — Phase 1d orchestration (`long_analysis.py`) built to read
  per-row source from Phase 1e's `data/snapshots/`, not to check out commits
  itself — its first draft did the latter, built without noticing Phase 1e
  already existed and already solved the exact slow-checkout problem that
  approach then hit on `airbyte`. Rewritten before it saw real use; no output
  was ever produced under the old approach.
- **2026-07-27** — DPy/Designite installed (Trial licenses), surfacing two
  concrete blockers before real output is possible: DPy's Trial license caps
  CSV export at <10K LOC (every pilot snapshot exceeds this), and Designite
  needs a `.sln` that Phase 1e's `*.cs`-only snapshots don't include. See
  Phase 1d (§8) "Update 2026-07-27" for detail. Not resolved yet — both need
  a decision (buy DPy Professional; decide how to get Designite a usable
  project file) before Phase 1d can produce real data.
- **2026-07-28** — Designite's `.sln` blocker resolved for Dock (SDK
  installed, pathspec extended, real `git archive` pathspec-matching bugs
  found and fixed along the way). aspire investigated and dropped from the
  C# analysis arm instead of forced to work — its build depends on Arcade's
  own CI bootstrap (pinned prerelease SDKs, private feeds) in its early
  history and an uninstalled preview SDK + unsupported `.slnx` format in its
  recent history, neither of which is a `materialize_snapshots.py`/Designite
  problem to solve generically. C# arm is Dock-only for this pilot phase; see
  Phase 1d (§8) "Update 2026-07-28" for detail and `EXCLUDED_REPOS`.

## Open decisions

- **Designite input for Dock**: resolved 2026-07-28 (SDK installed, pathspec
  extended to include `.sln`/`.csproj`/etc). Two remaining Dock-specific
  gaps: this Designite build (5.3.0.0) doesn't support `.slnx` (blocks Dock
  commits after 2025-12-25), and Trial license caps CSV export at <50K LOC
  (blocks Dock commits over that size) — same shape of problem as DPy's cap,
  not yet solved.
- **aspire scope**: dropped from the C# arm for this pilot phase rather than
  replicating its Arcade-based CI bootstrap per historical commit. Revisit
  only if the study later needs a second C# repo — options considered were:
  fully replicate aspire's own restore process (high effort, may not reach
  100% history coverage even then), look for a clean middle band of aspire
  history that needs neither Arcade nor `.slnx` (unconfirmed whether one
  exists), or swap in a different C# pilot repo (methodologically risky this
  late). See Phase 1d (§8) "Update 2026-07-28".
- **Designite generalization**: the current exclusion mechanism
  (`EXCLUDED_REPOS`) and pathspec-presence filtering are written to be
  repo-agnostic already, but `run_designite()`/`parse_tool_output()` and the
  Trial LOC-cap workaround are still being built against Dock specifically.
  Revisiting "run Designite against any specified C# repo" for real (per-repo
  SDK version detection, handling repos that need their own restore step,
  etc.) is explicitly deferred until after this small pilot set is done.
- **DPy licensing**: Trial caps CSV export at <10K LOC, which every pilot
  snapshot exceeds — needs a Professional license before Phase 1d produces
  real DPy output.

- A2's weekly-±3mo/monthly-±12mo grid and B2's ±10-PR window are defaults,
  not confirmed — may need to change per repo based on how dense each repo's
  own history actually is around its intervention point.
- Minimum snapshot count per repo before it's excluded from the ITS
  regression (relevant now that crewAI/aspire show 21–22 `no_prior_commit`
  A1 points out of 96 each).
- Whether informal (pre-AIDev) agent use is common enough to need the
  robustness check in §4, or whether the PR-`agent` column is enough alone.
- `GITHUB_TOKEN` source — confirmed the approach (env var, never hardcoded)
  but not yet set in this environment; still blocks Phase 1b.
- Phase 0 filtering is still moving in parallel (a dead-link PR filter was
  just added) — worth re-running Phase 1a once it settles, to confirm the
  pilot repos are still representative of the final candidate set.
- crewAI's 2 unmaterialized A2 commits (§7/§8) — accept the gap, or find an
  environment without the Windows filename restriction to fill it in.

## Artifacts

- `results/repos/*-aidev-agent-prs-*.csv`, `*-repo-summary-*.csv` — Phase 1a,
  done.
- `results/snapshots/07-21-repo-snapshot-manifest-480.csv` — Phase 1c, done.
- `data/snapshots/<owner>__<repo>/<commit_sha>/` — materialized source per
  unique resolved commit — Phase 1e, done (399/401).
- Track A1/A2 metric output (smell counts, OO metrics per snapshot) —
  orchestration built (`long_analysis.py`, Phase 1d), still needs DPy/Designite
  actually installed before it produces real output.
- Track B1/B2 output (PR-level process metrics, delta table per
  [archive/UnitofAnalysis.md](archive/UnitofAnalysis.md), superseded draft) —
  needs Phase 1b.
- Segmented regression output per primary metric (level change, slope
  change) — needs the above.
