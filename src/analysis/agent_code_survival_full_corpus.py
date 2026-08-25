"""
Tier-2 idea #1, full-corpus pass: does agent-created code get touched more
often, and survive less often, than human-created code? Follow-up to
`agent_code_survival.py`'s 10-repo, Python-only, gap-after-any-touch pilot
(see `Writing/AgentCodeSurvival.md`) - two real changes from that pass:

**Scope: full corpus, both languages, not a 10-repo Python subset.**
`results/analysis/08-19-entity-history-pooled.csv` already carries a
first/last-touch summary row per lineage for all 100 scaled-corpus repos
(65 Python + 34 C# with a local `data/repo_cache/` clone; C#'s own
`EntityHistory.cs`/`cs_entity_history.py` walk already ran for the RQ3
tracker - it was only the *agent-PR linking* step, not the underlying
entity-history walk, that was Python-only before). Reusing that pooled
file means this pass needs only a per-repo PR->commit resolution (one
`git log`, seconds) rather than re-walking git history per file - the
expensive part `agent_code_survival.py`'s docstring already paid for once.

**Question reframed as a birth cohort, not a post-touch gap.** The
original pass asked "what happens after an agent touches a file it
touches." This asks the more direct question stated in the request that
motivated this file: was an entity *created* by an agent-authored commit
touched more often than one created by a human commit, and did it
*survive* (see `survived_no_deletion` below - deletion is the cheap half
of "survived"; the "modified >50%" half needs an additional per-lineage
similarity computation against each entity's birth state - see
`compute_modification_similarity`, extended to BOTH languages 2026-08-24
via cs_entity_history.py's Roslyn-batch path, Python-only on first
landing).

Reuses `agent_code_survival.py`'s PR->commit and agent-PR-registry
resolution unchanged - not a parallel reimplementation.
"""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viz"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "inhouse"))
import figures_common as fc  # noqa: E402
from agent_code_survival import (  # noqa: E402
    agent_pr_numbers_for_repo,
    resolve_pr_commit_shas,
)
from entity_matching import jaccard  # noqa: E402
from py_entity_history import _entities_from_text, batch_show, _safe_dirname  # noqa: E402
from cs_entity_history import _run_roslyn_batch, _to_snapshot  # noqa: E402

ROOT = fc.ROOT
REPO_CACHE_DIR = ROOT / "data" / "repo_cache"
ENTITY_HISTORY_POOLED_PATH = fc.ANALYSIS_DIR / "08-19-entity-history-pooled.csv"
REPO_SUMMARY_PATH = fc.REPO_SUMMARY_DIR / "08-17-repo-summary-235.csv"
OUT_DIR = fc.ANALYSIS_DIR


def scoped_repos():
    """Every repo with a local clone AND at least one registered agent PR
    (both languages) - 99/100 on the real corpus (99 of the 100
    `data/repo_cache/` dirs have a nonzero `agent_pr_count`; the 100th has
    a clone but 0 agent PRs, contributing nothing to either cohort)."""
    rs = pd.read_csv(REPO_SUMMARY_PATH)
    cache = {p.name for p in REPO_CACHE_DIR.iterdir() if p.is_dir()}
    rs["dirname"] = rs["full_name"].str.replace("/", "__", regex=False)
    rs["has_clone"] = rs["dirname"].isin(cache)
    scope = rs[rs["has_clone"] & (rs["agent_pr_count"] > 0)]
    return scope[["repo_id", "full_name", "language", "agent_pr_count"]].reset_index(drop=True)


def resolve_agent_shas_all_repos(repos):
    """One `git log` per repo (same cheap, already-validated regex
    resolution as `agent_code_survival.py`) - the only new git operation
    this pass needs, since the entity-history walk itself is reused from
    the pooled file rather than redone."""
    rows = []
    for _, row in repos.iterrows():
        full_name, repo_id = row["full_name"], row["repo_id"]
        pr_commits = resolve_pr_commit_shas(full_name)
        agent_prs = agent_pr_numbers_for_repo(repo_id)
        agent_shas = {pr_commits[pr] for pr in agent_prs if pr in pr_commits}
        rows.append({
            "full_name": full_name, "repo_id": repo_id,
            "language": row["language"],
            "agent_prs_in_registry": len(agent_prs),
            "agent_prs_resolved_to_a_commit": len(agent_shas),
            "resolved_rate": len(agent_shas) / len(agent_prs) if agent_prs else float("nan"),
            "agent_shas": agent_shas,
        })
        print(f"{full_name}: {len(agent_prs)} agent PRs, "
              f"{len(agent_shas)} resolved to a commit "
              f"({len(agent_shas) / len(agent_prs):.0%})" if agent_prs else
              f"{full_name}: 0 agent PRs")
    return pd.DataFrame(rows)


def label_pooled_lineages(resolved):
    """Joins the pooled entity-history file to each repo's resolved
    agent-commit set on `full_name`, labeling every lineage
    `is_born_agent` = whether its OWN first touch (`first_commit`) landed
    via a commit this repo's registry flags as agent-authored. Lineages in
    repos outside `scoped_repos()` (no clone, or 0 registered agent PRs)
    are dropped - they can supply neither cohort."""
    pooled = pd.read_csv(ENTITY_HISTORY_POOLED_PATH)
    shas_by_repo = dict(zip(resolved["full_name"], resolved["agent_shas"]))
    pooled = pooled[pooled["full_name"].isin(shas_by_repo)].copy()
    pooled["is_born_agent"] = pooled.apply(
        lambda r: r["first_commit"] in shas_by_repo[r["full_name"]], axis=1
    )
    # age_days=0 (created and last-touched same day, or a single-commit
    # lineage) makes a touches-per-day rate divide-by-zero; +1 is this
    # project's usual small-denominator guard elsewhere (see e.g.
    # relative_churn's own None-on-zero handling in entity_matching.py) -
    # here a rate rather than a None, since 0 age doesn't make the rate
    # undefined, just large, and undefined would silently drop same-day
    # lineages from every rate-based comparison below.
    pooled["touches_after_birth"] = pooled["modification_count"] - 1
    pooled["touches_per_day"] = pooled["touches_after_birth"] / (pooled["age_days"] + 1)
    pooled["survived_no_deletion"] = ~pooled["ended"]
    return pooled


def cliffs_delta(a, b):
    diffs = a.to_numpy()[:, None] - b.to_numpy()[None, :]
    return (np.sum(diffs > 0) - np.sum(diffs < 0)) / diffs.size


def frequency_test(labeled, value_col):
    """Mann-Whitney U + Cliff's delta on `value_col`, agent-born vs.
    human-born, per repo (n>=2 both groups) and pooled - same convention
    `agent_code_survival.py`'s `gap_test` already established."""
    rows = []
    groups = list(labeled.groupby("full_name")) + [("pooled (non-independent, see caveat)", labeled)]
    for full_name, g in groups:
        agent = g.loc[g["is_born_agent"], value_col].dropna()
        other = g.loc[~g["is_born_agent"], value_col].dropna()
        if len(agent) < 2 or len(other) < 2:
            continue
        u, p = stats.mannwhitneyu(agent, other, alternative="two-sided")
        rows.append({
            "full_name": full_name, "n_agent": len(agent), "n_other": len(other),
            "median_agent": agent.median(), "median_other": other.median(),
            "mannwhitney_p": p, "cliffs_delta": cliffs_delta(agent, other),
        })
    return pd.DataFrame(rows)


def stratified_permutation_test(labeled, value_col, n_perms=300, seed=20260824):
    """Repo-stratified label-shuffle check on the pooled Cliff's delta -
    same mechanism and same reason as `agent_code_survival.py`'s own
    (there: a naive pooled p=4.5e-13 that a single repo's 54% share of the
    agent-tagged sample turned out to fully explain). Run reflexively
    here, not only when a pooled result looks suspicious - full-corpus
    scope makes repo-composition confounding the default risk, not an
    exception to check for after the fact."""
    is_agent = labeled["is_born_agent"].to_numpy()
    values = labeled[value_col].to_numpy(dtype=float)
    full_name = labeled["full_name"].to_numpy()
    valid = ~np.isnan(values)
    is_agent, values, full_name = is_agent[valid], values[valid], full_name[valid]
    real_delta = cliffs_delta(pd.Series(values[is_agent]), pd.Series(values[~is_agent]))

    rng = np.random.default_rng(seed)
    repo_masks = [full_name == name for name in np.unique(full_name)]
    null_deltas = np.empty(n_perms)
    for i in range(n_perms):
        shuffled = is_agent.copy()
        for mask in repo_masks:
            shuffled[mask] = rng.permutation(shuffled[mask])
        null_deltas[i] = cliffs_delta(pd.Series(values[shuffled]), pd.Series(values[~shuffled]))

    frac_le = (null_deltas <= real_delta).mean()
    p_two_sided = min(1.0, 2 * min(
        (np.sum(null_deltas <= real_delta) + 1) / (n_perms + 1),
        (np.sum(null_deltas >= real_delta) + 1) / (n_perms + 1),
    ))
    return pd.DataFrame([{
        "value_col": value_col, "n_perms": n_perms, "real_pooled_delta": real_delta,
        "null_mean_delta": float(null_deltas.mean()), "null_std_delta": float(null_deltas.std(ddof=1)),
        "null_percentile_of_real": frac_le * 100, "p_empirical_two_sided": p_two_sided,
    }])


def survival_deletion_test(labeled):
    """Deletion half of "survived" only (the modified->50% half isn't
    computed in this pass - see module docstring). Per repo (n>=5 both
    cohorts, a real-not-arbitrary floor: a 2x2 table with a near-empty
    cell reports a meaningless proportion) and pooled: proportion of
    lineages later deleted (`ended`), agent-born vs. human-born, Fisher
    exact test (a proportions test, not Mann-Whitney - the outcome here is
    binary, not a distribution to rank-compare)."""
    rows = []
    groups = list(labeled.groupby("full_name")) + [("pooled (non-independent, see caveat)", labeled)]
    for full_name, g in groups:
        agent = g.loc[g["is_born_agent"], "ended"]
        other = g.loc[~g["is_born_agent"], "ended"]
        if len(agent) < 5 or len(other) < 5:
            continue
        table = [[agent.sum(), len(agent) - agent.sum()],
                  [other.sum(), len(other) - other.sum()]]
        odds_ratio, p = stats.fisher_exact(table)
        rows.append({
            "full_name": full_name, "n_agent": len(agent), "n_other": len(other),
            "pct_deleted_agent": 100 * agent.mean(), "pct_deleted_other": 100 * other.mean(),
            "fisher_p": p, "odds_ratio": odds_ratio,
        })
    return pd.DataFrame(rows)


def stratified_permutation_test_proportion(labeled, value_col, n_perms=300, seed=20260824):
    """Same repo-stratified label-shuffle mechanism as
    `stratified_permutation_test`, but for a binary outcome (`ended`) using
    difference-in-proportions (agent mean - other mean) as the statistic
    instead of Cliff's delta - added specifically because
    `microsoft/testfx` posts a wildly outlying per-repo deletion result
    (36.5% agent-born deleted vs. 0.6% other, odds_ratio=99, on the real
    run) in the OPPOSITE direction from the pooled proportion (agent-born
    deleted LESS often overall) - exactly the shape that should be
    stratification-checked before either number goes in a headline,
    matching this project's now-standard response to that pattern."""
    is_agent = labeled["is_born_agent"].to_numpy()
    ended = labeled[value_col].to_numpy(dtype=bool)
    full_name = labeled["full_name"].to_numpy()
    real_diff = ended[is_agent].mean() - ended[~is_agent].mean()

    rng = np.random.default_rng(seed)
    repo_masks = [full_name == name for name in np.unique(full_name)]
    null_diffs = np.empty(n_perms)
    for i in range(n_perms):
        shuffled = is_agent.copy()
        for mask in repo_masks:
            shuffled[mask] = rng.permutation(shuffled[mask])
        null_diffs[i] = ended[shuffled].mean() - ended[~shuffled].mean()

    frac_le = (null_diffs <= real_diff).mean()
    p_two_sided = min(1.0, 2 * min(
        (np.sum(null_diffs <= real_diff) + 1) / (n_perms + 1),
        (np.sum(null_diffs >= real_diff) + 1) / (n_perms + 1),
    ))
    return pd.DataFrame([{
        "value_col": value_col, "n_perms": n_perms,
        "real_pooled_pct_diff": real_diff * 100,
        "null_mean_pct_diff": float(null_diffs.mean()) * 100,
        "null_std_pct_diff": float(null_diffs.std(ddof=1)) * 100,
        "null_percentile_of_real": frac_le * 100, "p_empirical_two_sided": p_two_sided,
    }])


def sample_modification_candidates(labeled, human_multiplier=3, seed=20260824):
    """Both languages (2026-08-24: extended from the first pass's
    Python-only scope - see git history for why that was deferred rather
    than skipped). The "modified >50%" half of survival needs each
    candidate lineage's own token content at birth and at its last known
    state - re-parsed from git blobs, not something the pooled file
    carries. All agent-born, still-alive lineages are candidates (937 on
    the full-corpus run, both languages - a real number, not too large to
    do in full). Human-born candidates are a per-repo random sample
    (`human_multiplier`x the repo's own agent-alive count, capped by
    availability) rather than all ~150K alive human-born lineages -
    matching this analysis's now-established repo-stratified design
    without paying to re-parse a six-figure blob count."""
    agent_alive = labeled[labeled["is_born_agent"] & ~labeled["ended"]].copy()
    human_alive = labeled[~labeled["is_born_agent"] & ~labeled["ended"]]

    rng = np.random.default_rng(seed)
    samples = []
    for full_name, n_agent in agent_alive.groupby("full_name").size().items():
        pool = human_alive[human_alive["full_name"] == full_name]
        n_sample = min(len(pool), n_agent * human_multiplier)
        if n_sample > 0:
            samples.append(pool.sample(n=n_sample, random_state=rng.integers(2**32 - 1)))
    human_sample = pd.concat(samples, ignore_index=True) if samples else human_alive.iloc[0:0]

    return pd.concat([agent_alive, human_sample], ignore_index=True)


def _build_inventory_python(repo_dir, pairs, blobs):
    """AST-based, in-process - no subprocess beyond the blob fetch
    itself."""
    inventory = {}
    for sha, path in pairs:
        text = blobs.get((sha, path))
        if text is None:
            inventory[(sha, path)] = {}
            continue
        class_inv, callable_inv = _entities_from_text(text, path)
        inventory[(sha, path)] = {**class_inv, **callable_inv}
    return inventory


def _build_inventory_csharp(repo_dir, pairs, blobs):
    """Roslyn-based: one `_run_roslyn_batch` call for ALL of a repo's
    needed blobs at once (not one dotnet subprocess per pair - the same
    per-file batching cs_entity_history.py's own collect_file_sequences
    already established, applied here across a whole repo's birth/last
    pairs instead of one file's touch history). Blobs missing from git
    (deleted/renamed-away path at that commit) are skipped before the
    Roslyn call, not sent as empty input - `_run_roslyn_batch` returns one
    result per INPUT blob, positionally aligned, so a pair with no text
    needs no matching output slot rather than a placeholder one."""
    ordered_pairs = [(sha, path) for sha, path in pairs if blobs.get((sha, path)) is not None]
    payload = [{"relpath": path, "text": blobs[(sha, path)]} for sha, path in ordered_pairs]
    results = _run_roslyn_batch(payload)
    if len(results) != len(ordered_pairs):
        raise RuntimeError(
            f"roslyn_tool --batch returned {len(results)} result(s) for "
            f"{len(ordered_pairs)} input blob(s) in {repo_dir} - can't align by position"
        )
    inventory = {pair: {} for pair in pairs}
    for (sha, path), result in zip(ordered_pairs, results):
        if result.get("status") != "ok":
            continue
        class_inv = {c["qualified_name"]: _to_snapshot(c) for c in result["classes"]}
        callable_inv = {c["qualified_name"]: _to_snapshot(c) for c in result["callables"]}
        inventory[(sha, path)] = {**class_inv, **callable_inv}
    return inventory


def compute_modification_similarity(candidates):
    """Birth-to-current Jaccard token-similarity per candidate lineage,
    one batched `git cat-file --batch` call per repo (reusing
    py_entity_history.py's batch_show - the same fix that took a
    documented 68-minute single-git-show-per-touch stall on
    browser-use/browser-use down to seconds, applied here to a birth/last
    pair per lineage instead of a full touch history) plus, per repo,
    ONE entity-extraction call - AST-in-process for Python
    (`_entities_from_text`), one batched Roslyn subprocess call for C#
    (`_run_roslyn_batch`, reusing cs_entity_history.py's own per-file
    batching pattern at repo scope instead). A lookup miss (entity not
    found in its own recorded commit's inventory - can happen on a real
    parse failure, or a qualified-name change a rename/move touch didn't
    fully track) is left NaN, not assumed 0 or 1, and reported as a real
    coverage number, not silently dropped."""
    build_inventory = {"Python": _build_inventory_python, "C#": _build_inventory_csharp}
    results = []
    for full_name, g in candidates.groupby("full_name"):
        repo_dir = REPO_CACHE_DIR / _safe_dirname(full_name)
        language = g["language"].iloc[0]
        pairs = set(zip(g["first_commit"], g["relpath"])) | set(zip(g["last_commit"], g["relpath"]))
        blobs = batch_show(repo_dir, sorted(pairs))
        inventory = build_inventory[language](repo_dir, pairs, blobs)

        for row in g.itertuples():
            first_inv = inventory.get((row.first_commit, row.relpath), {})
            last_inv = inventory.get((row.last_commit, row.relpath), {})
            first_snap = first_inv.get(row.first_qualified_name)
            last_snap = last_inv.get(row.last_qualified_name)
            similarity = (
                jaccard(first_snap.tokens, last_snap.tokens)
                if first_snap is not None and last_snap is not None else None
            )
            results.append({
                "full_name": full_name, "relpath": row.relpath, "lineage_id": row.lineage_id,
                "is_born_agent": row.is_born_agent, "similarity_birth_to_last": similarity,
                "survived_modification": similarity >= 0.5 if similarity is not None else None,
            })
        print(f"{full_name}: {len(g)} candidates, "
              f"{sum(1 for r in results[-len(g):] if r['similarity_birth_to_last'] is not None)} resolved")
    return pd.DataFrame(results)


def full_survival_test(mod_results, n_perms=300, seed=20260824):
    """Combines this module's two survival components into the
    request's own stated definition - "modified more than 50% or deleted
    means it did not survive" - for the candidate set
    `compute_modification_similarity` actually resolved (rows with
    `similarity_birth_to_last` present; unresolved lookups are excluded,
    not counted either way). `survived_modification` already came back
    None for every one of the small number of unresolved rows, so
    `full_survival = survived_modification` for this candidate set (it
    was built from `~ended` rows only - see
    `sample_modification_candidates` - so the deletion half is
    definitionally satisfied for all of them; deletion-caused
    non-survival was already tested full-corpus in
    `survival_deletion_test`/its stratified check above, on all 166K
    lineages, not just this similarity-resolved subset)."""
    resolved = mod_results.dropna(subset=["similarity_birth_to_last"]).copy()
    resolved["full_survival"] = resolved["survived_modification"]

    rows = []
    groups = list(resolved.groupby("full_name")) + [("pooled (non-independent, see caveat)", resolved)]
    for full_name, g in groups:
        agent = g.loc[g["is_born_agent"], "full_survival"]
        other = g.loc[~g["is_born_agent"], "full_survival"]
        if len(agent) < 5 or len(other) < 5:
            continue
        table = [[agent.sum(), len(agent) - agent.sum()],
                  [other.sum(), len(other) - other.sum()]]
        odds_ratio, p = stats.fisher_exact(table)
        rows.append({
            "full_name": full_name, "n_agent": len(agent), "n_other": len(other),
            "pct_survived_agent": 100 * agent.mean(), "pct_survived_other": 100 * other.mean(),
            "fisher_p": p, "odds_ratio": odds_ratio,
        })
    test = pd.DataFrame(rows)

    is_agent = resolved["is_born_agent"].to_numpy()
    survived = resolved["full_survival"].to_numpy(dtype=bool)
    full_name = resolved["full_name"].to_numpy()
    real_diff = survived[is_agent].mean() - survived[~is_agent].mean()
    rng = np.random.default_rng(seed)
    repo_masks = [full_name == name for name in np.unique(full_name)]
    null_diffs = np.empty(n_perms)
    for i in range(n_perms):
        shuffled = is_agent.copy()
        for mask in repo_masks:
            shuffled[mask] = rng.permutation(shuffled[mask])
        null_diffs[i] = survived[shuffled].mean() - survived[~shuffled].mean()
    frac_le = (null_diffs <= real_diff).mean()
    p_two_sided = min(1.0, 2 * min(
        (np.sum(null_diffs <= real_diff) + 1) / (n_perms + 1),
        (np.sum(null_diffs >= real_diff) + 1) / (n_perms + 1),
    ))
    strat = pd.DataFrame([{
        "n_perms": n_perms, "real_pooled_pct_diff": real_diff * 100,
        "null_mean_pct_diff": float(null_diffs.mean()) * 100,
        "null_std_pct_diff": float(null_diffs.std(ddof=1)) * 100,
        "null_percentile_of_real": frac_le * 100, "p_empirical_two_sided": p_two_sided,
    }])
    return test, strat


def run():
    repos = scoped_repos()
    print(f"=== {len(repos)} repos in scope "
          f"({(repos['language'] == 'Python').sum()} Python, "
          f"{(repos['language'] == 'C#').sum()} C#) ===\n")

    resolved = resolve_agent_shas_all_repos(repos)
    labeled = label_pooled_lineages(resolved)

    today = date.today()
    prefix = f"{today.month:02d}-{today.day:02d}"

    resolved_out = resolved.drop(columns=["agent_shas"])
    resolved_out.to_csv(OUT_DIR / f"{prefix}-agent-survival-fc-pr-resolution.csv", index=False)
    labeled.to_csv(OUT_DIR / f"{prefix}-agent-survival-fc-labeled-lineages.csv", index=False)

    n_agent_born = int(labeled["is_born_agent"].sum())
    n_human_born = int((~labeled["is_born_agent"]).sum())
    print(f"\n=== {len(labeled)} lineages labeled across {labeled['full_name'].nunique()} repos: "
          f"{n_agent_born} agent-born, {n_human_born} human-born ===")

    coverage = labeled.groupby("is_born_agent")["change_entropy"].agg(
        n_total="size", n_with_entropy=lambda s: s.notna().sum(),
    ).reset_index()
    coverage["coverage_pct"] = 100 * coverage["n_with_entropy"] / coverage["n_total"]
    coverage_path = OUT_DIR / f"{prefix}-agent-survival-fc-entropy-coverage.csv"
    coverage.to_csv(coverage_path, index=False)
    print(f"\n=== change_entropy coverage (needs >=3 touches, MIN_TOUCHES_FOR_ENTROPY) -> {coverage_path} ===")
    print(coverage.to_string(index=False))

    for value_col in ["touches_after_birth", "touches_per_day", "change_entropy"]:
        test = frequency_test(labeled, value_col)
        test_path = OUT_DIR / f"{prefix}-agent-survival-fc-freq-{value_col}.csv"
        test.to_csv(test_path, index=False)
        print(f"\n=== frequency ({value_col}): agent-born vs. human-born -> {test_path} ===")
        print(test.to_string(index=False))

        strat = stratified_permutation_test(labeled, value_col)
        strat_path = OUT_DIR / f"{prefix}-agent-survival-fc-freq-{value_col}-stratified-permutation.csv"
        strat.to_csv(strat_path, index=False)
        print(f"--- repo-stratified permutation check -> {strat_path} ---")
        print(strat.to_string(index=False))

    del_test = survival_deletion_test(labeled)
    del_path = OUT_DIR / f"{prefix}-agent-survival-fc-deletion.csv"
    del_test.to_csv(del_path, index=False)
    print(f"\n=== survival, deletion half only: agent-born vs. human-born -> {del_path} ===")
    print(del_test.to_string(index=False))

    del_strat = stratified_permutation_test_proportion(labeled, "ended")
    del_strat_path = OUT_DIR / f"{prefix}-agent-survival-fc-deletion-stratified-permutation.csv"
    del_strat.to_csv(del_strat_path, index=False)
    print(f"--- repo-stratified permutation check on pooled deletion-rate difference -> {del_strat_path} ---")
    print(del_strat.to_string(index=False))

    candidates = sample_modification_candidates(labeled)
    mod_results = compute_modification_similarity(candidates)
    mod_path = OUT_DIR / f"{prefix}-agent-survival-fc-modification-similarity.csv"
    mod_results.to_csv(mod_path, index=False)
    print(f"\n=== birth-to-last token similarity (both languages) -> {mod_path} ===")

    full_test, full_strat = full_survival_test(mod_results)
    full_test_path = OUT_DIR / f"{prefix}-agent-survival-fc-full-survival.csv"
    full_strat_path = OUT_DIR / f"{prefix}-agent-survival-fc-full-survival-stratified-permutation.csv"
    full_test.to_csv(full_test_path, index=False)
    full_strat.to_csv(full_strat_path, index=False)
    print(f"\n=== full survival (not deleted AND <50% modified since birth) -> {full_test_path} ===")
    print(full_test.to_string(index=False))
    print(f"--- repo-stratified permutation check -> {full_strat_path} ---")
    print(full_strat.to_string(index=False))

    return repos, resolved, labeled


if __name__ == "__main__":
    run()
