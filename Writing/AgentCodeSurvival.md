# Tier-2 idea #1 — does agent-touched code get rewritten sooner? (2026-08-21)

> **Status: first pass, real data, three real bugs found and fixed by
> hand-checking before trusting any output** (see each section below).
> Exploratory, not a pre-registered test. Branch:
> `analysis/agent-code-survival`, off
> `analysis/review-intensity-and-null-check`.

## Why this exists

`LitReview.md`'s source #15 ("Code Change Characteristics and
Description Alignment: Agentic versus Human PRs") finds, across the
aggregate AIDev corpus, that agent-introduced symbols are removed sooner
than human ones (median 3 vs. 34 days) and churn more (7.33% vs. 4.10%).
This project has its own longitudinal, per-entity touch history (the RQ3
entity tracker) — a from-scratch, within-repo replication of that
specific claim is buildable from data already collected, not something
that has to be taken on faith from AIDev's own aggregate numbers.

## The real blocker: no file on disk links a touch to a PR

`results/analysis/08-19-entity-history-pooled.csv` carries only
first/last touch per lineage — the full per-touch list (commit SHA, date,
change type) exists only transiently inside `py_entity_history.py`'s
`build_file_lineages()` while it runs, and is discarded once summarized
into that pooled file. `results/repos/08-17-aidev-agent-prs-3332.csv`
(the agent-PR registry) carries no commit SHA at all — only PR number
(parseable from `html_url`), agent name, and timestamps. `merged_at` is
frequently null even for genuinely merged PRs (Kalliamvakou et al. 2014,
cited in `LitReview.md`'s Theme 5, found ~40% of merged PRs don't show as
merged in GitHub's own API) — gating on that field would silently drop
real merges, not just unmerged ones.

**The fix, avoiding new API collection**: local git history already has
the answer. GitHub's default squash-merge commit message is
`<title> (#NNNN)`; a traditional merge commit's default message is
`Merge pull request #NNNN from ...`. Both patterns are matched against
each repo's own `git log` (already cloned in `data/repo_cache/`, no
network needed) to build a `pr_number -> commit_sha` map per repo,
independent of — and more reliable than — AIDev's own `merged_at` field.
Confirmed directly on `crewAIInc/crewAI` before writing any matching code:
10/10 sampled recent commits use the squash format.

Code: `src/analysis/agent_code_survival.py`.

## Scope

Python only this pass (`py_entity_history.py`'s matcher; a C# pass via
`EntityHistory.cs`/`cs_entity_history.py` is a real, separate follow-up).
Top-10 Python repos by `agent_pr_count` among RQ1's 79 regression-eligible
repos, all confirmed to have a local `data/repo_cache/` clone (51/51
Python regression-eligible repos have one — clone availability wasn't the
constraint). Not claimed to generalize to the other ~41 Python repos.

## Real PR→commit resolution rates vary by repo, and track known agent
identity — not a bug in the method

| Repo | Agent PRs | Resolved to a commit |
|---|---|---|
| `crewAIInc/crewAI` | 327 | 40 (12%) |
| `mlflow/mlflow` | 91 | 74 (81%) |
| `airbytehq/airbyte` | 218 | 86 (39%) |
| `AgentOps-AI/agentops` | 51 | 18 (35%) |

Before trusting this, checked whether the low rates reflect a broken
matcher or a real "most agent PRs here were never merged" story: crewAI's
resolved count (40) sits almost exactly on its `merged_at`-non-null count
(42) — the two independent signals agree closely, and crewAI is a 100%
Devin-authored repo (`agent_breakdown` in the repo-summary registry),
consistent with `LitReview.md` source #1's documented "agents accepted
less often than humans" finding. mlflow (Copilot-heavy) resolves at 81%.
The spread is real repo/agent variation, not evidence the method is
broken.

## Bug 1, found and fixed before trusting any output: random file sampling misses agent-touched files almost entirely

The first version of this script reused `py_entity_history.py`'s own
random 150-file sample, matching this project's usual convention for
scoping an entity-history walk. Run for real, it produced 0-9
agent-tagged touches per repo out of 1,300-3,500 touches walked — a
random sample of 150 files out of a repo's full file count essentially
never lands on the handful of files a specific agent commit actually
touched. Fixed by resolving each agent commit's own changed `.py` files
(`git diff --name-only {sha}~1 {sha}`, works uniformly for both a squash
commit and a merge commit since `~1` follows first-parent by default —
exactly the PR's own contributed diff) and walking exactly that targeted
set instead.

**A real, named trade-off this creates**: the "other" (non-agent) touches
compared against are still real human/other touches, but on files that
happen to attract agent attention specifically — not a repo-wide random
sample. The comparison this analysis actually runs is "what happens on a
file after an agent touches it, within that file's own history," not
"agent-touched files vs. typical files repo-wide."

## Bug 2, found by hand-checking a suspicious `gap_days=0` row: duplicate touches from a single commit

`entity_matching.py`'s matcher can record the same commit twice for the
same lineage — confirmed directly: `mlflow/mlflow`'s
`dev/check_function_signatures.py` lineage 1 lists commit `4d99802...`
twice, both `change_type="created"`. A real characteristic of the shared,
already-validated matcher, not something to alter there. For this
script's own purposes, two touch rows from the literal same commit aren't
a real "gap" — one event double-counted, not two events zero days apart.
5.4% of raw gap-pairs (666/12,391) were affected before this fix.
Deduplicated by `commit_sha` within each lineage before computing gaps.

**This fix mattered substantively, not just cosmetically**: before it,
mlflow alone showed a dramatic, seemingly clean result (p=5.7×10⁻⁹,
agent-touched code surviving *shorter*) that vanished entirely after
dedup (p=0.28) — the duplicate-touch artifact was inflating mlflow's
"after an agent touch" sample with spurious zero-day gaps. Reported here
as the reason this fix isn't optional, not as a curiosity.

## Coverage, after both fixes

| Repo | Agent-tagged touches | Gap-pairs after an agent touch |
|---|---|---|
| `mlflow/mlflow` | 277 | 119 |
| `Significant-Gravitas/AutoGPT` | 120 | 69 |
| `567-labs/instructor` | 30 | 14 |
| `getsentry/sentry` | 29 | 19 |
| `airbytehq/airbyte` | 71 | 0 |
| `AgentOps-AI/agentops` | 28 | 1 |
| `ikamensh/flynt` | 11 | 0 |
| `crewAIInc/crewAI` | 0 | 0 |
| `browser-use/browser-use`, `crewAIInc/crewAI-tools` | 0 | 0 |

Only 4 repos clear `n>=2` in both groups for a per-repo test at all
(mlflow, AutoGPT, instructor, getsentry). `crewAIInc/crewAI` contributes
nothing — every one of its 72 agent-touched files has since been moved or
deleted as part of the `lib/` restructuring `Results.md` already
documented (0/72 still present at HEAD), independently reconfirming that
finding through a completely different code path. `browser-use` and
`crewAI-tools` resolved real commits but none of their touched files
matched any lineage the AST matcher tracks in this walk (not further
diagnosed this session).

## Result: no generalizable signal, and the one seemingly strong pooled result doesn't survive a repo-composition check

| Repo | n (agent / other) | Median gap after agent (days) | Median gap after other | Mann-Whitney p | Cliff's δ |
|---|---|---|---|---|---|
| `567-labs/instructor` | 14 / 151 | 33.4 | 31.4 | 0.745 | -0.05 |
| `Significant-Gravitas/AutoGPT` | 69 / 613 | 68.7 | 48.2 | 0.515 | +0.05 |
| `getsentry/sentry` | 19 / 1,918 | 15.3 | 0.9 | **0.0025** | **+0.40** |
| `mlflow/mlflow` | 119 / 5,628 | 42.0 | 50.0 | 0.285 | -0.06 |
| **pooled (naive)** | 222 / 11,513 | 42.0 | 9.9 | **4.5×10⁻¹³** | **+0.28** |

Read naively, the pooled row says agent-touched entities take
*longer* to be touched again than other-touched entities — the opposite
direction from `LitReview.md`'s aggregate finding, and dramatically
significant. **This doesn't survive a repo-stratified permutation
check, built specifically because the pooled p-value was far more
extreme than any individual repo's own result (getsentry, the one real
per-repo signal, alone reaches only p=0.0025 on n=19)** — exactly the
mismatch shape a repo-composition confound produces: mlflow alone
supplies 54% of all agent-tagged gap-pairs, repos differ hugely in their
own baseline touch-gap distribution, and the "agent" group's repo mix
differs from the "other" group's by construction. Shuffling the
`is_agent_touch` label *within each repo separately* (preserving each
repo's own agent/other count and gap_days values, 300 draws) places the
real pooled Cliff's δ (0.283) at the **77th percentile** of that null
(mean 0.262, std 0.030), **p=0.465** — unremarkable. The naive pooled
significance is a repo-composition artifact, not evidence of a real
cross-repo effect.

**The one real, surviving result is getsentry alone** (p=0.0025, n=19,
δ=+0.40 — agent-touched entities take longer to be re-touched there) —
a single-repo lead on a small sample, 1 of 4 per-repo tests run in this
pass, unadjusted for multiple comparisons. Not a confirmed finding, and
not consistent with `LitReview.md`'s aggregate direction either.

**Bottom line: this analysis does not replicate `LitReview.md` source
#15's aggregate "agent code removed sooner" finding within this
project's own repos** — at least not from this 10-repo, Python-only,
exploratory pass. This is a genuine non-replication worth stating
plainly, not a failure to find something that's really there; it also
adds a third instance of this project's now-recurring lesson (after the
Findings-1/2 sampling-bias fix and the pre-slope/slope-change placebo
check) that a naive pooled or single-shot result needs a real
composition/randomization check before it goes in a headline.

## Caveats

- **N=4 repos with a usable per-repo test, not independent draws** — the
  pooled row (now shown to be a composition artifact, not a real
  aggregate) was the whole reason a stratified check was built, not an
  afterthought.
- **The "other" comparison group is files agents happen to touch, not a
  repo-wide random sample** (see Bug 1's trade-off above) — this
  analysis answers "what happens after an agent touches a file it
  touches," not "agent-touched files vs. typical files."
- **Coverage is real but partial and repo-dependent** — 3 of 10 repos
  contribute 0 usable gap-pairs for reasons ranging from a documented
  repo restructuring (crewAI) to unexplained zero AST-matcher overlap
  (browser-use, crewAI-tools) - not investigated further this pass.
- **Python only** — the C# side (`EntityHistory.cs`) would need its own
  merge-commit resolution and touch-walk; not attempted here.
- **PR→commit resolution via commit-message pattern matching, not
  GitHub's own PR-commit API** — a rebase-merge workflow (no PR-number-
  bearing commit message at all) would silently under-resolve; not
  distinguished from "PR never merged" in the resolved-rate numbers
  above.

Outputs: `results/analysis/08-21-agent-code-survival-coverage.csv`,
`-gaps.csv` (12,391 rows, one per gap-pair), `-test.csv`,
`-stratified-permutation.csv`.
