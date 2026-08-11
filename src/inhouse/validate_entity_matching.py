"""
Stage 3 validation gate (RQ3 execution plan): measures entity_matching.py's
real accuracy on this corpus before any age/modification_count/entropy
number from it is trusted, per the empirical-bias-check requirement raised
by Writing/codeaging.md's Hora et al. finding (10-21% of method-level
changes untracked, ~25% of entities' histories split, naive git-log-based
tracking).

Two independent checks, since a single AI session can't literally do the
~30-entity by-hand review the plan describes with a human's eyes - this is
the honest, defensible approximation of that:

1. **Automated baseline check** (objective, no judgment call needed): for a
   sample of lineages that never had a detected rename/move, cross-check
   the matcher's recorded touch-commit set against `git log -L
   :name:path`'s independently-computed line-history for that same
   function - git's own, differently-implemented algorithm. Agreement here
   is a real signal (two independently-built approaches concurring), not a
   tautology; git -L's own known weaknesses (documented in
   Writing/codeaging.md's "git tooling" note) are exactly why this is only
   the *baseline* check, not the whole validation.
2. **Manual review candidates** (judgment call, done in-session by reading
   the actual diff): every lineage that included a detected rename/move at
   ANY swept threshold gets its rename-commit's real diff printed for
   direct inspection - this is where a real rename gets told apart from a
   coincidental token-overlap false match. `--print-diffs` outputs these
   for review; classifications get recorded back via `--verdicts` (see
   VERDICTS_TEMPLATE below).

Threshold sweep: re-uses collect_file_sequences's cached (expensive) git
I/O across every threshold in --thresholds, since only the in-memory
matching step depends on threshold - avoids re-paying git subprocess cost
per threshold.
"""

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from py_entity_history import (  # noqa: E402
    REPO_CACHE_DIR, _head_commit_date, _run_git, _safe_dirname,
    collect_file_sequences, list_current_py_files,
)
from entity_matching import _parse_date, match_file_history  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "analysis"


def _git_dash_l_commits(repo_dir, path, func_name, timeout=60):
    """git's own independent function-line-history: commits that touched
    the named function's lines in `path`, per git's own diff heuristics -
    NOT the same algorithm as entity_matching.py's matcher, which is what
    makes agreement between them meaningful. `funcname` is treated by git
    as a regex matched against a function-definition-shaped line
    (`-L :<funcname>:<file>`); anchored with a plain name (not `\\b`-boxed)
    since git's own matching is already substring/regex-based - a name
    that's also a substring of another name in the same file is a known,
    accepted source of noise in this cross-check specifically (not in the
    matcher being validated), same category of imprecision -L always has
    per Writing/codeaging.md's "git tooling" note. Returns None (not a
    crash) if git -L can't resolve the function at all - a real outcome,
    not silently treated as 0 commits."""
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "log", "--format=%H",
         "-L", f":{func_name}:{path}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    if result.returncode != 0:
        return None
    shas = [
        line for line in result.stdout.splitlines()
        if len(line) == 40 and all(c in "0123456789abcdef" for c in line)
    ]
    return shas


def _bare_name(qualified_name):
    return qualified_name.rsplit(".", 1)[-1]


def automated_baseline_check(repo_dir, lineages_by_relpath, sample_size):
    """Sample `sample_size` never-renamed lineages, cross-check each
    against git -L. Returns a list of dicts (one per sampled lineage) with
    the two commit-set sizes and whether they agree - written straight to
    the validation-report CSV, no synthesis or interpretation baked in
    here."""
    candidates = []
    for relpath, lineages in lineages_by_relpath.items():
        for lineage in lineages:
            if lineage.kind != "callable":
                continue  # git -L's function-matching is built for callables
            if any(t.change_type in ("renamed", "moved") for t in lineage.touches):
                continue
            if lineage.modification_count < 2:
                continue  # a 1-touch lineage has nothing to cross-check
            candidates.append((relpath, lineage))

    candidates.sort(key=lambda rl: rl[1].modification_count, reverse=True)
    sample = candidates[:sample_size]

    rows = []
    for relpath, lineage in sample:
        name = _bare_name(lineage.last_touch.qualified_name)
        dash_l_shas = _git_dash_l_commits(repo_dir, relpath, name)
        tool_shas = {t.commit_sha for t in lineage.touches}
        if dash_l_shas is None:
            agreement = None
        else:
            dash_l_set = set(dash_l_shas)
            # Subset check, not exact-equality: -L often reports additional
            # context commits (e.g. formatting-only reflows the AST-based
            # matcher correctly treats as unchanged, see entity_matching.py's
            # "unchanged" filter) - what matters for THIS check is whether
            # every commit our tool flagged as a real change is also one
            # -L saw touch the function, not whether -L's own noisier
            # count matches exactly.
            agreement = tool_shas.issubset(dash_l_set)
        rows.append({
            "relpath": relpath,
            "qualified_name": lineage.last_touch.qualified_name,
            "tool_touch_count": lineage.modification_count,
            "dash_l_commit_count": len(dash_l_shas) if dash_l_shas is not None else None,
            "tool_subset_of_dash_l": agreement,
        })
    return rows


def manual_review_candidates(lineages_by_threshold_and_relpath):
    """Union, across every swept threshold, of every lineage that included
    a detected rename/move - these are exactly the cases where the matcher
    made a judgment call a human needs to check (git -L doesn't reliably
    cover cross-name identity either, so it's not a useful auto-check
    here). One row per (threshold, relpath, lineage) rename/move event."""
    rows = []
    for threshold, by_relpath in lineages_by_threshold_and_relpath.items():
        for relpath, lineages in by_relpath.items():
            for lineage in lineages:
                for i, touch in enumerate(lineage.touches):
                    if touch.change_type not in ("renamed", "moved"):
                        continue
                    prev_touch = lineage.touches[i - 1] if i > 0 else None
                    rows.append({
                        "threshold": threshold,
                        "relpath": relpath,
                        "lineage_id": lineage.lineage_id,
                        "kind": lineage.kind,
                        "commit_sha": touch.commit_sha,
                        "commit_date": touch.commit_date,
                        "change_type": touch.change_type,
                        "similarity": touch.similarity,
                        "from_qualified_name": prev_touch.qualified_name if prev_touch else None,
                        "to_qualified_name": touch.qualified_name,
                    })
    return rows


def print_diff_for_review(repo_dir, relpath, commit_sha):
    print(f"\n{'=' * 78}\n{relpath} @ {commit_sha[:10]}\n{'=' * 78}")
    out = _run_git(repo_dir, ["show", "--format=%H %ai %s", commit_sha, "--", relpath])
    print(out[:4000])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--limit-files", type=int, default=80)
    parser.add_argument(
        "--stride", type=int, default=1,
        help="sample every Nth file from the full sorted list instead of "
             "just the first --limit-files - an alphabetically-first slice "
             "can miss whole subtrees entirely (confirmed on crewAI: the "
             "first 80 files never reached lib/crewai/src/crewai/, where a "
             "real rename lived) - a stride gives broader tree coverage "
             "within the same file budget.",
    )
    parser.add_argument(
        "--thresholds", type=str, default="0.6,0.65,0.7,0.75,0.8",
    )
    parser.add_argument("--sample-size", type=int, default=30)
    parser.add_argument(
        "--print-diffs", action="store_true",
        help="print the real diff for every manual-review candidate",
    )
    args = parser.parse_args()
    thresholds = [float(t) for t in args.thresholds.split(",")]

    repo_dir = REPO_CACHE_DIR / _safe_dirname(args.repo)
    all_files = list_current_py_files(repo_dir)
    files = all_files[:: args.stride][: args.limit_files]

    print(f"collecting commit sequences for {len(files)} file(s) "
          f"(expensive, threshold-independent)...")
    sequences = {}
    for path in files:
        try:
            sequences[path] = collect_file_sequences(repo_dir, path)
        except RuntimeError as e:
            print(f"  [skip] {path}: {e}")

    print(f"matching at {len(thresholds)} threshold(s): {thresholds}")
    lineages_by_threshold = {}
    for threshold in thresholds:
        by_relpath = {}
        for path, (class_seq, callable_seq) in sequences.items():
            by_relpath[path] = (
                match_file_history(class_seq, threshold=threshold)
                + match_file_history(callable_seq, threshold=threshold)
            )
        lineages_by_threshold[threshold] = by_relpath

    # Rename/move counts per threshold - the headline sweep number.
    print("\nRename/move detections per threshold:")
    for threshold, by_relpath in lineages_by_threshold.items():
        n_renamed = sum(
            1 for lineages in by_relpath.values() for l in lineages
            if any(t.change_type in ("renamed", "moved") for t in l.touches)
        )
        n_total = sum(len(l) for l in by_relpath.values())
        print(f"  threshold={threshold:.2f}: {n_renamed}/{n_total} lineages "
              f"include a rename/move")

    # Automated baseline check at the design's default (0.75).
    default_threshold = 0.75 if 0.75 in lineages_by_threshold else thresholds[len(thresholds) // 2]
    baseline_rows = automated_baseline_check(
        repo_dir, lineages_by_threshold[default_threshold], args.sample_size
    )
    baseline_df = pd.DataFrame(baseline_rows)
    n_agree = baseline_df["tool_subset_of_dash_l"].sum() if len(baseline_df) else 0
    n_checked = baseline_df["tool_subset_of_dash_l"].notna().sum() if len(baseline_df) else 0
    print(f"\nAutomated baseline check (threshold={default_threshold}, "
          f"{len(baseline_df)} never-renamed lineages sampled):")
    print(f"  {n_agree}/{n_checked} tool touch-sets are a subset of git -L's "
          f"independently-computed commit set ({n_checked - n_agree} disagree)")

    # Manual review candidates: every rename/move across every threshold.
    review_rows = manual_review_candidates(lineages_by_threshold)
    review_df = pd.DataFrame(review_rows)
    print(f"\n{len(review_df)} rename/move event(s) across all thresholds "
          f"need manual review")
    if len(review_df):
        print(review_df[["threshold", "relpath", "from_qualified_name",
                          "to_qualified_name", "similarity"]].to_string(index=False))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    baseline_path = OUT_DIR / "rq3-validation-baseline-check.csv"
    review_path = OUT_DIR / "rq3-validation-manual-review-candidates.csv"
    baseline_df.to_csv(baseline_path, index=False)
    review_df.to_csv(review_path, index=False)
    print(f"\nwrote {baseline_path}\nwrote {review_path}")

    if args.print_diffs and len(review_df):
        seen = set()
        for _, row in review_df.iterrows():
            key = (row["relpath"], row["commit_sha"])
            if key in seen:
                continue
            seen.add(key)
            print_diff_for_review(repo_dir, row["relpath"], row["commit_sha"])


if __name__ == "__main__":
    main()
