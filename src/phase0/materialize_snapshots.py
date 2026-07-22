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
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CLONE_CACHE_DIR = ROOT / "data" / "repo_cache"
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
MANIFEST_DIR = ROOT / "results" / "snapshots"

LANGUAGE_PATHSPEC = {"Python": "*.py", "C#": "*.cs"}
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
    resolved = df[df["commit_sha"].notna()]
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
    (repo_dir / ".git" / "info" / "sparse-checkout").write_text(pathspec + "\n")
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


def archive_commit(full_name, commit_sha, pathspec, dest):
    repo_dir = CLONE_CACHE_DIR / _safe_dirname(full_name)
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.Popen(
        ["git", *GIT_HTTP_OVERRIDE, "-C", str(repo_dir), "archive", commit_sha, "--", pathspec],
        stdout=subprocess.PIPE,
    )
    tar = subprocess.Popen(["tar", "-x", "-C", str(dest)], stdin=archive.stdout)
    archive.stdout.close()
    try:
        tar.wait(timeout=ARCHIVE_TIMEOUT_SECONDS)
        archive.wait(timeout=5)
    except subprocess.TimeoutExpired:
        archive.kill()
        tar.kill()
        return False
    return archive.returncode == 0 and tar.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=str, default=None,
                         help="only process this full_name (e.g. crewAIInc/crewAI); default: all repos in the manifest")
    args = parser.parse_args()

    commits = unique_commits()
    if args.repo:
        commits = commits[commits["full_name"] == args.repo]
        if commits.empty:
            print(f"no rows for --repo {args.repo}")
            return

    for full_name, group in commits.groupby("full_name"):
        language = group["language"].iloc[0]
        pathspec = LANGUAGE_PATHSPEC.get(language)
        if pathspec is None:
            print(f"=== {full_name}: skipping, no pathspec mapped for language {language!r}")
            continue

        repo_dest_root = SNAPSHOT_DIR / _safe_dirname(full_name)
        todo = [sha for sha in group["commit_sha"] if not (repo_dest_root / sha).exists()]
        print(f"\n=== {full_name} ({language}) - {len(group)} unique commits, {len(todo)} not yet materialized ===")
        if not todo:
            print("  nothing to do")
            continue

        backfill_repo(full_name, pathspec)

        done = failed = 0
        for sha in todo:
            ok = archive_commit(full_name, sha, pathspec, repo_dest_root / sha)
            if ok:
                done += 1
            else:
                failed += 1
                print(f"  [archive] {full_name}@{sha[:7]}: failed or timed out")
        print(f"  materialized {done}/{len(todo)} ({failed} failed - rerun to retry, backfill/archives are idempotent)")


if __name__ == "__main__":
    main()
