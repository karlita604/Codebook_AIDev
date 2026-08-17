"""
Storage lifecycle for data/repo_cache/ - the full git-history clones
materialize_snapshots.py and pool_entity_history.py both read from.

At ~430MB/repo average (confirmed: 9.9GB measured across ~23 repos), this
scales to ~43GB at 100 repos, ~430GB at 1000 - not something to leave
unmanaged as the corpus grows. This module identifies which repos'
repo_cache/ clones are safe to reclaim (entity-history done for that
repo, not on the keep-list) and reports or deletes them on request.

Deletion is NEVER automatic and NEVER the default action here, and this
module is deliberately NOT wired into materialize_snapshots.py's main
flow or src/pipeline/run_pipeline.py's stage list - a real risk with
auto-pruning right after entity-history finishes (the scaling plan's
original framing) is that a repo's repo_cache/ clone may be needed again
later even after entity-history is "done" for it today: the manifest
could later be regenerated with a wider date grid (e.g. the A1 track's
end date moving forward as time passes), or --max-files-per-repo could
be raised for a fuller entity-history pass over the same repo. Deleting
the only full-history clone on the assumption that today's "done" is
final would make either of those a full re-clone instead of a quick
re-run. So: this is framed as a manual, deliberate disk-reclaiming
action a researcher runs when THEY decide a repo is truly done, not
something the pipeline does on its own - `main()`'s dry-run-by-default,
--confirm-gated design reflects that directly.

results/repos/keep_cache.csv (same CSV shape as
results/repos/excluded_repos.csv, src/common/exclusions.py, but a
different registry with a different meaning): full_name repos never
eligible for pruning regardless of entity-history status - e.g. a repo
under active debugging where re-cloning would slow down iteration.

Not implemented here (documented as a real follow-up, not done because
data/snapshots/ is the much smaller half of the disk cost per the numbers
above, and correctly identifying "this exact commit's snapshot is no
longer needed by anything" requires checking every relevant consolidated
output, not just one): a lighter secondary policy for pruning individual
data/snapshots/<repo>/<sha>/ directories once their rows are confirmed
present in every consolidated metrics/smells output.
"""

import argparse
import csv
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import resumable_run as rr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REPO_CACHE_DIR = ROOT / "data" / "repo_cache"
ANALYSIS_DIR = ROOT / "results" / "analysis"
KEEP_CACHE_PATH = ROOT / "results" / "repos" / "keep_cache.csv"

# Matches pool_entity_history.py's own tag/key_cols/exclude_suffixes -
# "done" here means the exact same thing it means there (see that
# script's SCHEMA_VERSION/_ENTITY_HISTORY_EXCLUDE_SUFFIXES).
ENTITY_HISTORY_TAG = "entity-history"
ENTITY_HISTORY_KEY_COLS = ["repo_id", "full_name"]
_ENTITY_HISTORY_EXCLUDE_SUFFIXES = ("-errors.csv", "-repo-summary.csv")


def _safe_dirname(full_name):
    """Same convention as materialize_snapshots.py's _safe_dirname - kept
    duplicated rather than imported for the same reason
    py_entity_history.py's own copy gives (avoiding a cross-package
    src/phase0 <-> src/common import for one one-line function)."""
    return full_name.replace("/", "__")


def load_keep_list(path=KEEP_CACHE_PATH):
    """Set of full_name repos never eligible for pruning, regardless of
    entity-history status. Missing file = empty set (nothing pinned yet),
    not an error - matches src/common/exclusions.py's own convention for
    an absent registry."""
    path = Path(path)
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        return {row["full_name"] for row in csv.DictReader(f)}


def dir_size_bytes(path):
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def find_prunable_repos(only_full_name=None):
    """Repos where: (a) repo_cache/<repo>/ exists on disk, (b) entity-
    history has a done-key recorded for that repo (the same
    resumable_run.load_done_keys check pool_entity_history.py itself
    uses to decide "already done" - not a separate, possibly-inconsistent
    notion of done), (c) not in the keep-list. Returns a list of
    {full_name, dir_path, size_bytes} dicts, largest first (so a
    --confirm run reclaims the most space soonest if interrupted).

    `only_full_name` filters BEFORE the (potentially slow - a full
    recursive directory walk per repo) size computation, not after -
    passing --repo should cost roughly one repo's disk-walk time, not
    every eligible repo's."""
    done_repos = rr.load_done_keys(
        ANALYSIS_DIR, ENTITY_HISTORY_TAG, ENTITY_HISTORY_KEY_COLS,
        exclude_suffixes=_ENTITY_HISTORY_EXCLUDE_SUFFIXES, verbose=False,
    )
    done_full_names = {full_name for (_repo_id, full_name) in done_repos}
    keep_list = load_keep_list()
    eligible_names = sorted(done_full_names - keep_list)
    if only_full_name is not None:
        eligible_names = [n for n in eligible_names if n == only_full_name]

    candidates = []
    for full_name in eligible_names:
        repo_dir = REPO_CACHE_DIR / _safe_dirname(full_name)
        if not repo_dir.exists():
            continue
        candidates.append({
            "full_name": full_name,
            "dir_path": repo_dir,
            "size_bytes": dir_size_bytes(repo_dir),
        })
    return sorted(candidates, key=lambda c: c["size_bytes"], reverse=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm", action="store_true",
        help="actually delete the prunable repo_cache/ directories found "
             "- without this flag, only reports what WOULD be deleted "
             "(the default, and the only thing this tool does unless you "
             "pass this explicitly). Add a repo to "
             "results/repos/keep_cache.csv first if it should never be "
             "pruned regardless of entity-history status.",
    )
    parser.add_argument(
        "--repo", type=str, default=None,
        help="only consider this one full_name, instead of every "
             "prunable repo found",
    )
    args = parser.parse_args()

    candidates = find_prunable_repos(only_full_name=args.repo)

    if not candidates:
        print(
            "nothing prunable (entity-history not done for any repo "
            "outside keep_cache.csv, or repo_cache/ already clean)"
        )
        return

    total_bytes = sum(c["size_bytes"] for c in candidates)
    print(
        f"{len(candidates)} repo(s) eligible for pruning "
        f"({total_bytes / 1e9:.2f} GB total):", flush=True,
    )
    for c in candidates:
        print(f"  {c['size_bytes'] / 1e6:8.1f} MB  {c['full_name']}")

    if not args.confirm:
        print(
            "\ndry-run only (default) - pass --confirm to actually "
            "delete these directories.", flush=True,
        )
        return

    for c in candidates:
        print(f"deleting {c['dir_path']} ...", flush=True)
        shutil.rmtree(c["dir_path"])
    print(
        f"\ndeleted {len(candidates)} repo(s), freed "
        f"{total_bytes / 1e9:.2f} GB", flush=True,
    )


if __name__ == "__main__":
    main()
