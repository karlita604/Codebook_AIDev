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

### 1. Define the intervention point per repo
We already have this cheaply from the AIDev dataset used in
[`PRfilter.py`](../src/phase0/PRfilter.py) and [`metrics.py`](../src/phase0/metrics.py):
`all_pull_request` includes an `agent` column (`Claude_Code`, `Copilot`, `Cursor`,
`Devin`, `OpenAI_Codex`, null otherwise). For each `repo_id`:
- **Primary definition**: `created_at` of the first PR with non-null `agent`.
- **Robustness check**: presence of agent-config artifacts in the repo tree
  (`CLAUDE.md`, `.github/copilot-instructions.md`, agent workflow files) via the
  GitHub API, in case agents were used informally before any PR was attributed.
- **Dosage variable**: fraction of PRs/commits per interval that are agent-attributed,
  post-intervention. Adoption isn't binary — record this so the analysis isn't
  forced into an on/off comparison.

### 2. Build the sampling frame
For each repo (identified by `repo_id`, resolved to `repo_url`/`html_url` via
`all_repository`):
- Pull full commit history via the GitHub API.
- Define observation points at fixed calendar intervals (e.g., first commit of each
  month) across a symmetric window around the intervention point — start with ±12
  months, adjust per repo age.
- Use **time-based**, not commit-count-based, sampling: commit velocity itself may
  change post-intervention, so it's an outcome, not a valid sampling frame.

### 3. Snapshot extraction and tool pipeline
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

### 4. Metric catalog to extract
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

### 5. Analysis plan
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

### 6. Threats to validity to design around now
- **Selection**: repos that adopt agents may differ systematically from those that
  don't → mitigated by the matched comparison arm (step 5).
- **Detection confounding**: agents may move code across a smell's threshold
  without changing real quality → mitigated by freezing the threshold config
  (step 3) and reporting effect sizes on raw underlying metrics, not just smell
  counts.

## Open decisions
- Window size (±12 months default) — may need to shrink for younger repos.
- Whether informal agent use (robustness check in step 1) is common enough in this
  dataset to matter, or whether the PR-`agent` column is sufficient on its own.
- Minimum snapshot count per repo before it's excluded from the ITS regression.

## Artifacts
- Design/implementation smell count per snapshot, before and after (repo-level).
- Segmented regression output per primary metric (level change, slope change).
- PR-level delta table (see [UnitofAnalysis.md](UnitofAnalysis.md)) for the
  complementary refactoring-instance analysis.
