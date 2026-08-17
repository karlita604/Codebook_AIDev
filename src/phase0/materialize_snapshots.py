"""
Materialize the actual source tree for each unique commit in the Track A1/A2
snapshot manifest (results/snapshots/*.csv), so DPy/Designite have something
to run against once installed (Phase 1d).

Design (see Writing/Longitudinal.md, section 7):
- Dedup by (repo, commit_sha), not by manifest row - several grid points can
  resolve to the same commit.
- Language-filtered extraction (git archive with a '*.py' / '*.cs' pathspec),
  not a full checkout - DPy/Designite only read one language, and a full
  checkout pulls in test fixtures/data/docs that dwarf the actual source.
- One-time per-repo blob backfill (git backfill --sparse) before archiving:
  archiving directly against a --filter=blob:none clone (data/repo_cache/)
  triggers a slow one-object-at-a-time lazy fetch per file. HTTP/1.1 is
  forced for both backfill and archive (-c http.version=HTTP/1.1) - this
  environment's HTTPS transport resets mid-transfer under HTTP/2 for large
  sequential fetches ("schannel: server closed abruptly"); forcing HTTP/1.1
  fixed it in testing.
- Both backfill and the per-commit archive loop are idempotent/resumable:
  reruns skip repos/commits already done, and git backfill itself resumes
  from wherever a previous (possibly interrupted) run left off.

Output: data/snapshots/<owner>__<repo>/<commit_sha>/ - one directory per
unique commit, containing just that repo's source-language files at that
commit. Gitignored, same as data/repo_cache/.

Usage:
    python materialize_snapshots.py                       # all repos in the manifest
    python materialize_snapshots.py --repo crewAIInc/crewAI  # just one repo

Large repos may need more than one call to finish backfilling within a single
run's time budget - rerun with the same --repo and it picks up where it left off.
"""

import argparse
import fnmatch
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
import exclusions  # noqa: E402
import parallel_repo  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CLONE_CACHE_DIR = ROOT / "data" / "repo_cache"
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
MANIFEST_DIR = ROOT / "results" / "snapshots"

LANGUAGE_PATHSPEC = {
    "Python": ["*.py"],
    # Designite (Roslyn MSBuildWorkspace) needs an actual .sln/.csproj graph,
    # not just source - see DESIGNITE_TASK.md. Historical solutions may also
    # reference .props/.targets imports or a legacy packages.config; pull
    # those too since MSBuildWorkspace may need them to resolve projects.
    # .slnx (newer XML solution format) is also needed - e.g. Dock migrated
    # Dock.sln -> Dock.slnx on 2025-12-25 (b8fb130d), so post-migration
    # commits have no .sln at all.
    "C#": [
        "*.cs", "*.sln", "*.slnx", "*.csproj", "*.props", "*.targets",
        "packages.config",
    ],
}

# Repos permanently out of scope for materialization/analysis, keyed by
# full_name. Not a manifest edit - the manifest reflects real repo selection
# history and shouldn't be silently changed; this is a pipeline-level scope
# decision. Loaded from results/repos/excluded_repos.csv (scope=permanent
# rows only - "permanent" here means "this tool can never handle this
# repo", not "excluded forever"; see src/common/exclusions.py's docstring)
# rather than hardcoded, so a new permanently-blocked repo found at
# 100/1000-repo scale is a registry edit, not a code change in three
# different files. dotnet/aspire is the seed case (see the registry) -
# Designite's MSBuildWorkspace can't evaluate its project graph.
EXCLUDED_REPOS = exclusions.load_exclusions(scope="permanent")
GIT_HTTP_OVERRIDE = ["-c", "http.version=HTTP/1.1"]
ARCHIVE_TIMEOUT_SECONDS = 120
BACKFILL_TIMEOUT_SECONDS = 570  # leave headroom under a 600s call budget


def _safe_dirname(full_name):
    return full_name.replace("/", "__")


def latest_manifest():
    files = sorted(MANIFEST_DIR.glob("*-repo-snapshot-manifest-*.csv"))
    if not files:
        raise FileNotFoundError(f"No manifest found in {MANIFEST_DIR}")
    return files[-1]


def unique_commits():
    df = pd.read_csv(latest_manifest())
    resolved = df[df["commit_sha"].notna() & ~df["full_name"].isin(EXCLUDED_REPOS)]
    return (
        resolved[["repo_id", "full_name", "language", "commit_sha"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )


def backfill_repo(full_name, pathspec):
    repo_dir = CLONE_CACHE_DIR / _safe_dirname(full_name)
    subprocess.run(
        ["git", "sparse-checkout", "init", "--no-cone"],
        cwd=repo_dir, check=True, capture_output=True, text=True,
    )
    (repo_dir / ".git" / "info" / "sparse-checkout").write_text("\n".join(pathspec) + "\n")
    print(f"  [backfill] {full_name}: fetching {pathspec} blobs for all history...")
    try:
        subprocess.run(
            ["git", *GIT_HTTP_OVERRIDE, "backfill", "--sparse"],
            cwd=repo_dir, check=True, capture_output=True, text=True,
            timeout=BACKFILL_TIMEOUT_SECONDS,
        )
        print(f"  [backfill] {full_name}: done")
    except subprocess.TimeoutExpired:
        print(f"  [backfill] {full_name}: hit the {BACKFILL_TIMEOUT_SECONDS}s budget for "
              f"this call - resumable, rerun the script to continue")
    except subprocess.CalledProcessError as e:
        print(f"  [backfill] {full_name}: error - {e.stderr.strip()[:300]} - resumable, rerun to retry")
    finally:
        subprocess.run(
            ["git", "sparse-checkout", "disable"],
            cwd=repo_dir, check=False, capture_output=True, text=True,
        )


def _is_materialized(dest):
    """A destination only counts as done if it actually has content - a
    directory can exist and be empty from a prior failed/interrupted attempt."""
    return dest.exists() and any(dest.iterdir())


def _present_patterns(repo_dir, commit_sha, patterns):
    """`git archive` (unlike ls-tree/checkout) hard-fails with exit 128 if ANY
    given pathspec matches zero files in the tree - there's no --ignore-unmatch
    for archive. A fixed multi-extension C# pathspec WILL hit this per-commit
    (e.g. Dock has no *.sln at all after its 2025-12-25 .sln -> .slnx
    migration, and no *.slnx before it) so filter down to only the patterns
    that actually match something at this commit before archiving.

    Match against the full relative path, not the basename: git's own
    pathspec matching treats a literal (non-wildcard) pattern like
    `packages.config` as an exact top-level path, NOT a basename match at any
    depth - a repo with only `eng/common/sdl/packages.config` (no top-level
    one) makes git archive itself reject that pathspec as unmatched, so
    checking basenames here would wrongly keep a pattern archive then fails
    on."""
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "ls-tree", "-r", "--name-only", commit_sha],
        check=True, capture_output=True, text=True,
    )
    paths = result.stdout.splitlines()
    return [pat for pat in patterns if any(fnmatch.fnmatch(p, pat) for p in paths)]


def archive_commit(full_name, commit_sha, pathspec, dest):
    """Extracts into a temp dir and only renames to `dest` on success, so a
    failed/killed attempt never leaves behind a directory that looks done."""
    repo_dir = CLONE_CACHE_DIR / _safe_dirname(full_name)
    present = _present_patterns(repo_dir, commit_sha, pathspec)
    if not present:
        return False

    tmp_dest = dest.parent / (dest.name + ".tmp")
    if tmp_dest.exists():
        shutil.rmtree(tmp_dest)
    tmp_dest.mkdir(parents=True)

    archive = subprocess.Popen(
        ["git", *GIT_HTTP_OVERRIDE, "-C", str(repo_dir), "archive", commit_sha, "--", *present],
        stdout=subprocess.PIPE,
    )
    tar = subprocess.Popen(["tar", "-x", "-C", str(tmp_dest)], stdin=archive.stdout)
    archive.stdout.close()
    try:
        tar.wait(timeout=ARCHIVE_TIMEOUT_SECONDS)
        archive.wait(timeout=5)
    except subprocess.TimeoutExpired:
        archive.kill()
        tar.kill()
        shutil.rmtree(tmp_dest, ignore_errors=True)
        return False

    ok = archive.returncode == 0 and tar.returncode == 0 and any(tmp_dest.iterdir())
    if ok:
        if dest.exists():
            shutil.rmtree(dest)
        # Windows sometimes still holds a transient handle (AV scan, search
        # indexer) right after tar closes its files - retry the rename a
        # few times before giving up rather than losing a good extraction.
        for attempt in range(5):
            try:
                tmp_dest.rename(dest)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(1)
    else:
        shutil.rmtree(tmp_dest, ignore_errors=True)
    return ok


def _process_one_repo(full_name, item):
    """Worker body for one repo's backfill+archive - runs inline
    (--workers<=1) or in a ProcessPoolExecutor worker (--workers>1, see
    src/common/parallel_repo.py). Must stay module-level (picklable by
    reference) for the latter. No output-file-shape concern here unlike
    the pool_inhouse_*.py scripts' --workers - this produces
    data/snapshots/ directories, not appendable CSV fragments, so there's
    no "unscoped run's on-disk shape" to preserve identically between
    modes; resumability is just `_is_materialized()` checking each
    destination directory directly, already safe for concurrent workers
    to check independently (a repo either has its own already-materialized
    commits skipped, or doesn't - no shared file for two workers to race
    on, since each worker only ever touches its own repo's directories)."""
    language, commit_shas = item
    pathspec = LANGUAGE_PATHSPEC.get(language)
    if pathspec is None:
        print(f"=== {full_name}: skipping, no pathspec mapped for language {language!r}")
        return {"full_name": full_name, "done": 0, "failed": 0}

    repo_dest_root = SNAPSHOT_DIR / _safe_dirname(full_name)
    todo = [sha for sha in commit_shas if not _is_materialized(repo_dest_root / sha)]
    print(f"\n=== {full_name} ({language}) - {len(commit_shas)} unique commits, {len(todo)} not yet materialized ===")
    if not todo:
        print("  nothing to do")
        return {"full_name": full_name, "done": 0, "failed": 0}

    backfill_repo(full_name, pathspec)

    done = failed = 0
    for i, sha in enumerate(todo, start=1):
        try:
            ok = archive_commit(full_name, sha, pathspec, repo_dest_root / sha)
        except OSError as e:
            print(f"  [archive] {full_name}@{sha[:7]}: OS error - {e} - rerun to retry")
            ok = False
        if ok:
            done += 1
            print(f"  [archive] {full_name} ({i}/{len(todo)}) @{sha[:7]}: ok", flush=True)
        else:
            failed += 1
            print(f"  [archive] {full_name} ({i}/{len(todo)}) @{sha[:7]}: failed or timed out", flush=True)
    print(f"  materialized {done}/{len(todo)} for {full_name} ({failed} failed - rerun to retry, backfill/archives are idempotent)")
    return {"full_name": full_name, "done": done, "failed": failed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=str, default=None,
                         help="only process this full_name (e.g. crewAIInc/crewAI); default: all repos in the manifest")
    parser.add_argument(
        "--workers", type=int, default=1,
        help="repos to backfill/archive in parallel (default 1 = "
             "sequential). >1 dispatches one process per repo via "
             "ProcessPoolExecutor - each repo's git operations are "
             "already fully independent (own clone directory in "
             "data/repo_cache/), so this is safe with no output-shape "
             "change, unlike the pool_inhouse_*.py scripts' --workers. "
             "git subprocess calls (backfill/archive) have real startup "
             "and network cost - start low (4-6) on a single workstation.",
    )
    args = parser.parse_args()

    commits = unique_commits()
    if args.repo:
        commits = commits[commits["full_name"] == args.repo]
        if commits.empty:
            print(f"no rows for --repo {args.repo}")
            return

    items_by_repo = {
        full_name: (group["language"].iloc[0], list(group["commit_sha"]))
        for full_name, group in commits.groupby("full_name")
    }

    if args.workers > 1:
        print(
            f"dispatching {len(items_by_repo)} repo(s) across "
            f"{args.workers} worker(s)", flush=True,
        )
    total_done = total_failed = 0
    for full_name, summary in parallel_repo.run_by_repo(
        items_by_repo, _process_one_repo, workers=args.workers,
    ):
        total_done += summary["done"]
        total_failed += summary["failed"]
    print(
        f"\ndone: {total_done} materialized, {total_failed} failed "
        f"across {len(items_by_repo)} repo(s)", flush=True,
    )


if __name__ == "__main__":
    main()
