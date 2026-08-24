"""
Tier-2 idea #1: does code an agent PR touched get rewritten sooner than
code touched by anything else? LitReview.md's source #15 ("Code Change
Characteristics and Description Alignment") finds agent-introduced symbols
removed sooner than human ones in the aggregate AIDev corpus (median 3 vs.
34 days). This project has its own longitudinal, per-entity touch history
(the RQ3 entity tracker) - a from-scratch, within-repo replication of that
question is buildable from data already collected, not something this
project has to take on faith from AIDev's own numbers.

**The real blocker, found before writing any analysis code**: no file on
disk links an individual entity *touch* (a specific commit) to a specific
PR, let alone that PR's agent flag. `results/analysis/08-19-entity-history-pooled.csv`
carries only first/last touch per lineage - the full per-touch list
(commit_sha, date, change_type) exists only transiently inside
`py_entity_history.py`'s `build_file_lineages()` while it runs, and is
discarded once summarized. `results/repos/08-17-aidev-agent-prs-3332.csv`
(the agent-PR registry) carries no commit SHA at all - only PR number
(parseable from `html_url`), agent name, and timestamps (`merged_at` is
frequently null even for genuinely merged PRs - Kalliamvakou et al. 2014,
cited in `LitReview.md`'s Theme 5, found ~40% of merged PRs don't show as
merged in GitHub's own API - so gating on that field would silently drop
real merges, not just unmerged ones).

**The fix, avoiding new API collection**: local git history already
contains the answer. GitHub's default squash-merge commit message is
`<title> (#NNNN)`; a traditional merge commit's default message is
`Merge pull request #NNNN from ...`. Both patterns are matched against
each repo's own `git log` (already cloned in `data/repo_cache/`, no
network needed) to build a `pr_number -> commit_sha` map per repo -
independent of the AIDev dataset's own `merged_at` field, and more
reliable than it for exactly the reason above. Confirmed directly on
crewAIInc/crewAI before writing this: 10/10 sampled recent commits use
the squash format, `(#NNNN)` at the end of the message.

**Scope, stated honestly rather than assumed complete**: re-extracting
full per-touch data means re-walking git history per file - the same
work `py_entity_history.py`'s original 100-repo run already paid for
once, but not persisted, so it has to be paid again here. This first
pass scopes to Python only (`py_entity_history.py`'s matcher; a C# pass
via `EntityHistory.cs`/`cs_entity_history.py` is a real, separate
follow-up, not attempted here) and REPOS (module-level constant below) -
the highest agent-PR-count Python repos among RQ1's 79 regression-eligible
set, all of which have a local `data/repo_cache/` clone (checked: 51/51
Python regression-eligible repos have one). Coverage is reported as a
real number, not assumed to generalize to the other ~40 Python repos.

**A file-sampling bug found and fixed before trusting any output, not a
theoretical concern**: the first version of this script reused
`py_entity_history.py`'s own random 150-file sample (`sample_files()`),
matching this project's usual convention. Run for real, it produced
0-9 agent-tagged touches per repo out of 1,300-3,500 touches walked -
a random sample of 150 files out of a repo's full file count essentially
never lands on the handful of files a specific agent commit actually
touched. Fixed by resolving each agent commit's own changed `.py` files
(`files_touched_by_commit()`, `git diff --name-only {sha}~1 {sha}`) and
walking exactly that targeted set instead - see `run()`'s own docstring
for the resulting, real trade-off this creates (the "other" touches
compared against are on agent-attracting files, not a repo-wide sample).

Reuses `py_entity_history.py`'s `list_current_py_files`/`build_file_lineages`
unchanged - not a parallel reimplementation of the matcher itself.
"""

import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viz"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "inhouse"))
import figures_common as fc  # noqa: E402
import py_entity_history as peh  # noqa: E402
from entity_matching import _parse_date  # noqa: E402

ROOT = fc.ROOT
REPO_CACHE_DIR = ROOT / "data" / "repo_cache"
AIDEV_AGENT_PRS_PATH = fc.REPO_SUMMARY_DIR / "08-17-aidev-agent-prs-3332.csv"
OUT_DIR = fc.ANALYSIS_DIR

# Top-10 Python repos by agent_pr_count among RQ1's 79 regression-eligible
# repos (all confirmed to have a data/repo_cache/ clone) - see module
# docstring for why this isn't "all 51." Chosen for agent-PR density
# (more agent PRs -> more chance of a resolvable commit -> more chance of
# a usable gap-pair), not cherry-picked on outcome.
REPOS = [
    "crewAIInc/crewAI", "airbytehq/airbyte", "mlflow/mlflow",
    "AgentOps-AI/agentops", "567-labs/instructor", "getsentry/sentry",
    "Significant-Gravitas/AutoGPT", "browser-use/browser-use",
    "crewAIInc/crewAI-tools", "ikamensh/flynt",
]

# Squash-merge: "<title> (#1234)" at the very end of the message.
# Traditional merge commit: "Merge pull request #1234 from ...".
# Deliberately NOT a bare `#\d+` anywhere in the message - that also
# matches informal issue references ("fixes #42" mid-sentence), which
# are not landing commits and would misattribute an unrelated commit's
# date to the PR.
_SQUASH_RE = re.compile(r"\(#(\d+)\)\s*$")
_MERGE_RE = re.compile(r"^Merge pull request #(\d+) from")


def _safe_dirname(full_name):
    return full_name.replace("/", "__")


def resolve_pr_commit_shas(full_name):
    """One `git log` call per repo (not one per PR - much cheaper), regex
    over every commit message for the two landing-commit patterns above.
    Returns {pr_number: commit_sha}. A PR number matched more than once
    (rare - e.g. a revert-and-reland) keeps the first (most recent, since
    git log is newest-first) match and is not otherwise flagged - a
    conscious simplification, not an unnoticed edge case."""
    repo_dir = REPO_CACHE_DIR / _safe_dirname(full_name)
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "log", "--format=%H%x01%s"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120,
    )
    mapping = {}
    for line in result.stdout.split("\n"):
        if "\x01" not in line:
            continue
        sha, msg = line.split("\x01", 1)
        m = _SQUASH_RE.search(msg) or _MERGE_RE.match(msg)
        if m:
            pr_number = int(m.group(1))
            mapping.setdefault(pr_number, sha)
    return mapping


def agent_pr_numbers_for_repo(repo_id):
    """PR numbers AIDev flags as agent-authored for one repo, parsed from
    the registry's html_url (no pr_number column there) - same regex
    review_intensity_explainer.py already validated (3,332/3,332 rows
    parse cleanly)."""
    agent = pd.read_csv(AIDEV_AGENT_PRS_PATH)
    agent = agent[agent["repo_id"] == repo_id].copy()
    agent["pr_number"] = agent["html_url"].str.extract(r"/pull/(\d+)$").astype("Int64")
    return agent.dropna(subset=["pr_number"]).set_index("pr_number")["agent"].to_dict()


def files_touched_by_commit(full_name, sha):
    """.py files a resolved agent commit actually changed, via
    `git diff --name-only {sha}~1 {sha}` - works uniformly for both a
    squash commit (single parent) and a traditional merge commit (`~1`
    follows first-parent by default, i.e. the target branch's state right
    before the merge - exactly the PR's own contributed diff, not the
    merge's trivial no-op diff `git diff-tree` would show without `-m`).
    Root commits (no parent) fail this diff form - not expected among
    resolved agent-PR landing commits, and not specially handled."""
    repo_dir = REPO_CACHE_DIR / _safe_dirname(full_name)
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "diff", "--name-only", f"{sha}~1", sha],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60,
    )
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.splitlines() if f.endswith(".py")]


def walk_repo_touches(full_name, files):
    """Reuses py_entity_history.py's own file-listing/matcher functions
    unchanged, but keeps the raw EntityLineage objects (with their full
    .touches list) instead of calling build_repo_lineages() (which
    converts to first/last-touch summary rows and discards the rest) -
    the one deliberate deviation from that module's own call pattern,
    needed because this script's whole question depends on the touches
    build_repo_lineages() would throw away.

    `files` is passed in explicitly, not resampled here - see run()'s own
    docstring for why a random file sample (this project's usual
    convention, reused verbatim in an earlier version of this script)
    turned out to be the wrong call for this specific question: it
    produced near-zero overlap with the handful of files any given agent
    commit actually touched, out of a repo's full file count."""
    columns = ["relpath", "lineage_id", "kind", "commit_sha", "commit_date", "change_type"]
    if not files:
        # A real, expected case, not defensive paranoia: crewAIInc/crewAI
        # specifically underwent a large lib/ restructuring after most of
        # its own history - files an old agent commit touched routinely no
        # longer exist anywhere at HEAD, so target_files (run()'s
        # touched-union intersected with files still present) can land at
        # 0 for a repo whose resolved-commit count was otherwise healthy.
        # Returns a properly-shaped empty frame rather than pd.DataFrame([])'s
        # columnless one, so tag_and_compute_gaps' column access downstream
        # doesn't KeyError on a repo with real 0-file coverage.
        return pd.DataFrame(columns=columns)
    repo_dir = REPO_CACHE_DIR / _safe_dirname(full_name)
    rows = []
    for path in files:
        try:
            class_lineages, callable_lineages = peh.build_file_lineages(repo_dir, path)
        except RuntimeError:
            continue
        for lineage in class_lineages + callable_lineages:
            for t in lineage.touches:
                rows.append({
                    "relpath": path, "lineage_id": lineage.lineage_id,
                    "kind": lineage.kind, "commit_sha": t.commit_sha,
                    "commit_date": t.commit_date, "change_type": t.change_type,
                })
    return pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)


def tag_and_compute_gaps(touches, agent_shas):
    """One row per touch that has a *following* touch on the same lineage
    (the lineage's final touch is right-censored - "no touch yet" isn't
    "no touch ever" - so it's dropped here, not treated as an infinite or
    zero gap). gap_days = time to that next touch. is_agent_touch: whether
    *this* touch (the one starting the gap being measured) landed via a
    commit this repo's agent-PR registry flags.

    **Duplicate-touch dedup, found by hand-checking a suspicious
    gap_days=0 row, not assumed clean**: entity_matching.py's matcher can
    record the *same commit* twice for the same lineage (confirmed
    directly: mlflow/mlflow's `dev/check_function_signatures.py` lineage
    1 lists commit `4d99802...` twice, both `change_type="created"`) -
    a real characteristic of the shared, already-validated matcher, not
    something to alter there. For this script's purposes specifically, two
    touch rows from the literal same commit aren't a real "gap" (zero
    elapsed time between two *different* events) - they're one event
    double-counted. Deduplicated by commit_sha within each lineage before
    computing gaps, keeping the first occurrence order-wise."""
    gap_columns = ["relpath", "lineage_id", "kind", "touch_index", "commit_sha",
                   "commit_date", "is_agent_touch", "gap_days"]
    if touches.empty:
        return pd.DataFrame(columns=gap_columns)
    touches = touches.copy()
    touches["commit_date"] = touches["commit_date"].apply(_parse_date)
    touches["is_agent_touch"] = touches["commit_sha"].isin(agent_shas)
    rows = []
    for (relpath, lineage_id), g in touches.groupby(["relpath", "lineage_id"]):
        g = g.sort_values("commit_date").drop_duplicates("commit_sha").reset_index(drop=True)
        for i in range(len(g) - 1):
            gap_days = (g.loc[i + 1, "commit_date"] - g.loc[i, "commit_date"]).total_seconds() / 86400
            rows.append({
                "relpath": relpath, "lineage_id": lineage_id, "kind": g.loc[i, "kind"],
                "touch_index": i, "commit_sha": g.loc[i, "commit_sha"],
                "commit_date": g.loc[i, "commit_date"], "is_agent_touch": g.loc[i, "is_agent_touch"],
                "gap_days": gap_days,
            })
    return pd.DataFrame(rows, columns=gap_columns) if rows else pd.DataFrame(columns=gap_columns)


def run(repos=REPOS):
    """Walks only the .py files a repo's resolved agent commits actually
    touched (files_touched_by_commit's union), intersected with files
    still present at HEAD (py_entity_history.py's own documented
    limitation - a file an agent PR touched and which was later deleted
    or renamed away isn't `git log --follow`-able from its current
    location, so it can't be walked at all here; reported per repo, not
    silently dropped). An earlier version of this script reused the main
    pipeline's random 150-file sample instead - across all 10 repos it
    produced 0-9 agent-tagged touches out of thousands walked, because a
    handful of PR-touched files essentially never lands inside a random
    sample drawn from a repo's full file count. Targeting the actually-
    relevant files fixes that at the cost of a real, named trade-off: the
    "other" (non-agent) touches being compared against are still real
    human/other touches, but on files that happen to attract agent
    attention specifically, not a repo-wide random sample - the
    comparison is "what happens on a file after an agent touches it,
    within that file's own history," not "agent-touched files vs.
    typical files repo-wide.\""""
    all_gaps = []
    coverage_rows = []
    rs = pd.read_csv(fc.REPO_SUMMARY_DIR / "08-17-repo-summary-235.csv")
    for full_name in repos:
        repo_id = rs.loc[rs["full_name"] == full_name, "repo_id"].iloc[0]
        repo_dir = REPO_CACHE_DIR / _safe_dirname(full_name)

        pr_commits = resolve_pr_commit_shas(full_name)
        agent_prs = agent_pr_numbers_for_repo(repo_id)
        agent_shas = {pr_commits[pr] for pr in agent_prs if pr in pr_commits}
        resolved_rate = len(agent_shas) / len(agent_prs) if agent_prs else float("nan")

        touched_union = set()
        for sha in agent_shas:
            touched_union.update(files_touched_by_commit(full_name, sha))
        current_files = set(peh.list_current_py_files(repo_dir))
        target_files = sorted(touched_union & current_files)
        n_touched_gone = len(touched_union - current_files)

        touches = walk_repo_touches(full_name, target_files)
        gaps = tag_and_compute_gaps(touches, agent_shas)
        gaps["full_name"] = full_name
        gaps["repo_id"] = repo_id
        all_gaps.append(gaps)

        coverage_rows.append({
            "full_name": full_name, "agent_prs_in_registry": len(agent_prs),
            "agent_prs_resolved_to_a_commit": len(agent_shas),
            "resolved_rate": resolved_rate,
            "agent_touched_files": len(touched_union),
            "agent_touched_files_still_at_head": len(target_files),
            "agent_touched_files_gone": n_touched_gone,
            "total_touches_walked": len(touches),
            "agent_tagged_touches": int(touches["commit_sha"].isin(agent_shas).sum()) if len(touches) else 0,
            "gap_pairs_total": len(gaps),
            "gap_pairs_after_agent_touch": int(gaps["is_agent_touch"].sum()) if len(gaps) else 0,
        })
        print(f"{full_name}: {len(agent_prs)} agent PRs, "
              f"{len(agent_shas)} resolved to a commit ({resolved_rate:.0%}), "
              f"{len(touches)} touches walked, "
              f"{int(touches['commit_sha'].isin(agent_shas).sum()) if len(touches) else 0} agent-tagged, "
              f"{len(gaps)} gap-pairs ({int(gaps['is_agent_touch'].sum()) if len(gaps) else 0} after an agent touch)")

    coverage = pd.DataFrame(coverage_rows)
    gaps_all = pd.concat(all_gaps, ignore_index=True) if all_gaps else pd.DataFrame()

    today = date.today()
    prefix = f"{today.month:02d}-{today.day:02d}"
    coverage_path = OUT_DIR / f"{prefix}-agent-code-survival-coverage.csv"
    gaps_path = OUT_DIR / f"{prefix}-agent-code-survival-gaps.csv"
    coverage.to_csv(coverage_path, index=False)
    gaps_all.to_csv(gaps_path, index=False)

    print(f"\n=== coverage -> {coverage_path} ===")
    print(coverage.to_string(index=False))

    test = gap_test(gaps_all)
    test_path = OUT_DIR / f"{prefix}-agent-code-survival-test.csv"
    test.to_csv(test_path, index=False)
    print(f"\n=== gap_days: after an agent touch vs. after any other touch -> {test_path} ===")
    print(test.to_string(index=False) if not test.empty else "(no repo/pooled cell had n>=2 in both groups)")

    strat = stratified_permutation_test(gaps_all) if not gaps_all.empty else pd.DataFrame()
    strat_path = OUT_DIR / f"{prefix}-agent-code-survival-stratified-permutation.csv"
    strat.to_csv(strat_path, index=False)
    print(f"\n=== repo-stratified permutation check on the pooled Cliff's delta -> {strat_path} ===")
    print(strat.to_string(index=False) if not strat.empty else "(no data)")

    return coverage, gaps_all, test, strat


def gap_test(gaps_all):
    """Mann-Whitney U + Cliff's delta (this project's established
    small-n two-group convention), pooled and per-repo: gap_days after an
    agent-authored touch vs. gap_days after any other touch on the same
    lineage. Pooled row is the headline for the same non-independence
    reason every other RQ in this project's heterogeneity-explainer work
    already states - individual touches within a repo aren't independent
    draws."""
    if gaps_all.empty:
        return pd.DataFrame()
    # Concatenating a real repo's typed columns with a 0-row-but-still-
    # object-dtype empty frame (crewAIInc/crewAI - see walk_repo_touches'
    # own empty-input branch, an empty pd.DataFrame(columns=[...]) has no
    # way to know its columns' real dtypes) upcasts the whole pooled
    # column to object dtype - caught by two real crashes here (`~` on an
    # object-dtype bool column does Python's bitwise-NOT on the underlying
    # ints, giving -2/-1 not False/True; scipy's isnan then rejects an
    # object-dtype gap_days column outright), not assumed safe. Cast both
    # back to their real dtypes before use.
    gaps_all = gaps_all.astype({"is_agent_touch": bool, "gap_days": float})
    rows = []
    groups = list(gaps_all.groupby("full_name")) + [("pooled (non-independent, see caveat)", gaps_all)]
    for full_name, g in groups:
        agent = g.loc[g["is_agent_touch"], "gap_days"].dropna()
        other = g.loc[~g["is_agent_touch"], "gap_days"].dropna()
        if len(agent) < 2 or len(other) < 2:
            continue
        u, p = stats.mannwhitneyu(agent, other, alternative="two-sided")
        diffs = agent.to_numpy()[:, None] - other.to_numpy()[None, :]
        delta = (np.sum(diffs > 0) - np.sum(diffs < 0)) / diffs.size
        rows.append({
            "full_name": full_name, "n_after_agent": len(agent), "n_after_other": len(other),
            "median_gap_after_agent": agent.median(), "median_gap_after_other": other.median(),
            "mannwhitney_p": p, "cliffs_delta": delta,
        })
    return pd.DataFrame(rows)


def _pooled_cliffs_delta(is_agent, gap_days):
    agent = gap_days[is_agent]
    other = gap_days[~is_agent]
    diffs = agent[:, None] - other[None, :]
    return (np.sum(diffs > 0) - np.sum(diffs < 0)) / diffs.size


def stratified_permutation_test(gaps_all, n_perms=300, seed=20260821):
    """Tests whether the naive pooled Mann-Whitney above (p=4.5e-13 on the
    real run) is bigger than repo composition alone would produce -
    caught as suspicious by hand, not run reflexively: every *individual*
    repo's own test in `test` was weak or null (one exception,
    getsentry, p=0.002 on n=19) - a mismatch that large between "every
    repo alone: nothing much" and "pooled: extremely significant" is
    exactly the shape a repo-composition confound produces, not a
    repo-general effect, and exactly the same "hand-check anything
    surprisingly clean before reporting it" instinct
    `HeterogeneityExplainersPart2.md`'s placebo-permutation work already
    established as this project's own convention for this failure mode.

    Real mechanism the naive pooled test can't see: repos differ hugely
    in their own baseline touch-gap distribution, and the "agent" group's
    repo composition differs from the "other" group's by construction
    (agent touches are a small, repo-uneven subset - see the coverage
    table: mlflow alone supplies 54% of all agent-tagged gap-pairs). A
    pooled two-group test can find "significance" that's actually "which
    repo's baseline dominates which bucket," not a real cross-repo effect.

    Null: shuffle the is_agent_touch label *within each repo separately*
    (preserving each repo's own agent/other count and its own gap_days
    values exactly - only which specific rows get the "agent" label
    changes), recompute the pooled Cliff's delta, 300 times. If the real
    pooled delta sits inside this null, the naive test's apparent
    significance is explained by repo composition."""
    gaps_all = gaps_all.astype({"is_agent_touch": bool, "gap_days": float})
    is_agent = gaps_all["is_agent_touch"].to_numpy()
    gap_days = gaps_all["gap_days"].to_numpy()
    full_name = gaps_all["full_name"].to_numpy()
    real_delta = _pooled_cliffs_delta(is_agent, gap_days)

    rng = np.random.default_rng(seed)
    repo_masks = [full_name == name for name in np.unique(full_name)]
    null_deltas = np.empty(n_perms)
    for i in range(n_perms):
        shuffled = is_agent.copy()
        for mask in repo_masks:
            shuffled[mask] = rng.permutation(shuffled[mask])
        null_deltas[i] = _pooled_cliffs_delta(shuffled, gap_days)

    frac_le = (null_deltas <= real_delta).mean()
    p_two_sided = min(1.0, 2 * min(
        (np.sum(null_deltas <= real_delta) + 1) / (n_perms + 1),
        (np.sum(null_deltas >= real_delta) + 1) / (n_perms + 1),
    ))
    return pd.DataFrame([{
        "n_perms": n_perms, "real_pooled_delta": real_delta,
        "null_mean_delta": float(null_deltas.mean()), "null_std_delta": float(null_deltas.std(ddof=1)),
        "null_percentile_of_real": frac_le * 100, "p_empirical_two_sided": p_two_sided,
    }])


if __name__ == "__main__":
    run()
