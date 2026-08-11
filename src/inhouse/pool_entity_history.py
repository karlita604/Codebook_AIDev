"""
Stage 5 orchestrator (RQ3 execution plan): runs entity-lineage extraction
(py_entity_history.py for Python, cs_entity_history.py for C#) across every
repo in the Phase 2 manifest, pooling into one table.

CLI shape, resumability, and progress/error-file conventions mirror
pool_inhouse_metrics.py deliberately - same pipeline family, just resumable
per (repo_id, full_name) instead of per manifest grid row, since RQ3's unit
of work is "one repo's full git history," not one snapshot. Reads repos
directly from data/repo_cache/ (full-history clones), not data/snapshots/
(Phase 1e's monthly grid) - so a repo that isn't materialized for the
structural-metrics tools (julep-ai/julep) is still includable here.

--max-files-per-repo (default 150) is a real, deliberate scoping decision,
not an oversight: several Phase 2 repos are far too large for an exhaustive
per-file, full-history walk in one run (Azure/azure-sdk-for-python alone has
44,112 Python files at HEAD - confirmed by direct count, not assumed). The
cap trades completeness-per-repo for breadth-across-repos: every repo in
scope gets real coverage now, rather than fully covering a handful and
never reaching the rest. Files are taken in sorted-path order (same
determinism py_entity_history.py's list_current_py_files already has) -
not randomized, so a low cap is biased toward alphabetically-early paths;
documented here, not hidden.

Use --dry-run to check repo_cache coverage without running any analysis.
Use --limit/--repo to test on a handful of repos first.
"""

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cs_entity_history  # noqa: E402
import py_entity_history  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "analysis"
MANIFEST_DIR = ROOT / "results" / "snapshots"

DEFAULT_MAX_FILES_PER_REPO = 150

LANGUAGE_BUILDER = {
    "Python": py_entity_history.build_repo_lineages,
    "C#": cs_entity_history.build_repo_lineages_cs,
}


def latest_manifest():
    files = sorted(MANIFEST_DIR.glob("*-repo-snapshot-manifest-*.csv"))
    if not files:
        raise FileNotFoundError(f"no manifest found in {MANIFEST_DIR}")
    return files[-1]


def eligible_repos(manifest_path):
    df = pd.read_csv(manifest_path)
    repos = (
        df[["repo_id", "full_name", "language"]]
        .drop_duplicates()
        .sort_values("full_name")
    )
    return repos[repos["language"].isin(LANGUAGE_BUILDER.keys())]


def _load_done_repos(tag):
    """Global across every prior real-output file matching this tag, same
    convention as pool_inhouse_metrics.py's _load_done_keys - a repo counts
    as done if it appears in ANY prior same-tag output (including a
    previous --repo-scoped run), so parallel/resumed runs never redo work."""
    done = set()
    for path in OUT_DIR.glob(f"*-{tag}-*.csv"):
        if path.name.endswith("-errors.csv"):
            continue
        try:
            df = pd.read_csv(path, usecols=["repo_id", "full_name"])
        except (ValueError, pd.errors.EmptyDataError):
            continue
        done.update(df[["repo_id", "full_name"]].itertuples(index=False, name=None))
    return done


def _append_rows(path, rows):
    if not rows:
        return
    write_header = not path.exists()
    pd.DataFrame(rows).to_csv(path, mode="a", header=write_header, index=False)


def _write_progress(progress_path, started_at, total, done, ok, failed, current):
    elapsed = time.time() - started_at
    rate = done / elapsed if elapsed > 0 else 0
    eta_seconds = (total - done) / rate if rate > 0 else None
    progress_path.write_text(json.dumps({
        "started_at": started_at,
        "total": total,
        "done": done,
        "ok": ok,
        "failed": failed,
        "elapsed_seconds": round(elapsed, 1),
        "eta_seconds": round(eta_seconds, 1) if eta_seconds is not None else None,
        "current": current,
    }))


def process_repo(repo_id, full_name, language, max_files_per_repo, threshold, dry_run):
    builder = LANGUAGE_BUILDER[language]
    if dry_run:
        repo_dir = py_entity_history.REPO_CACHE_DIR / py_entity_history._safe_dirname(full_name)
        row = {
            "repo_id": repo_id, "full_name": full_name, "language": language,
            "status": "dry_run", "repo_cache_exists": repo_dir.exists(),
        }
        return {"status": "dry_run", "n_lineages": None, "n_file_errors": None}, [row]

    rows = builder(full_name, limit_files=max_files_per_repo, threshold=threshold)
    for row in rows:
        row["repo_id"] = repo_id
        row["full_name"] = full_name
        row["language"] = language
    n_ok = sum(1 for r in rows if r["status"] == "ok")
    n_err = sum(1 for r in rows if r["status"] == "error")
    return {"status": "ok", "n_lineages": n_ok, "n_file_errors": n_err}, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="only process the first N eligible repos")
    parser.add_argument("--repo", type=str, default=None, help="only process repos whose full_name contains this substring")
    parser.add_argument(
        "--max-files-per-repo", type=int, default=DEFAULT_MAX_FILES_PER_REPO,
        help=f"cap on .py/.cs files walked per repo (default {DEFAULT_MAX_FILES_PER_REPO}) "
             "- see module docstring for why this exists",
    )
    parser.add_argument("--threshold", type=float, default=None)
    args = parser.parse_args()

    manifest_path = args.manifest or latest_manifest()
    repos = eligible_repos(manifest_path)
    print(f"manifest: {manifest_path} ({len(repos)} eligible repo(s), "
          f"Python or C#)", flush=True)

    if args.repo:
        repos = repos[repos["full_name"].str.contains(args.repo)]
    if args.limit:
        repos = repos.head(args.limit)
    total = len(repos)
    print(f"{total} repo(s) selected for this run "
          f"(--max-files-per-repo={args.max_files_per_repo})", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = "dryrun-entity-history" if args.dry_run else "entity-history"

    scope = re.sub(r"[^a-zA-Z0-9]+", "", args.repo)[:30] if args.repo else None
    scope_suffix = f"{scope}-{total}" if scope else str(total)

    existing = sorted(
        OUT_DIR.glob(f"*-{tag}-{scope_suffix}.csv"),
        key=lambda p: p.stat().st_mtime,
    )
    if existing:
        stem = existing[-1].stem
        print(f"continuing existing run: {existing[-1]}", flush=True)
    else:
        today = date.today()
        stem = f"{today.month:02d}-{today.day:02d}-{tag}-{scope_suffix}"
    out_path = OUT_DIR / f"{stem}.csv"
    err_path = OUT_DIR / f"{stem}-errors.csv"
    progress_path = OUT_DIR / f"{stem}-progress.json"
    repo_summary_path = OUT_DIR / f"{stem}-repo-summary.csv"

    done_repos = _load_done_repos(tag)
    if done_repos:
        print(f"resuming: {len(done_repos)} repo(s) already done, skipping", flush=True)

    started_at = time.time()
    ok_count, fail_count = len(done_repos), 0
    repo_summaries = []
    for i, (_, repo) in enumerate(repos.iterrows(), start=1):
        key = (repo["repo_id"], repo["full_name"])
        label = f"{repo['full_name']} ({repo['language']})"
        if key in done_repos:
            continue

        t0 = time.time()
        try:
            summary, rows = process_repo(
                repo["repo_id"], repo["full_name"], repo["language"],
                args.max_files_per_repo, args.threshold, args.dry_run,
            )
            _append_rows(out_path, rows)
            elapsed = time.time() - t0
            ok_count += 1
            print(
                f"  [ok] ({i}/{total}) {label}: "
                f"{summary.get('n_lineages', '-')} lineage(s), "
                f"{summary.get('n_file_errors', 0)} file error(s), "
                f"{elapsed:.1f}s",
                flush=True,
            )
            repo_summaries.append({
                "repo_id": repo["repo_id"], "full_name": repo["full_name"],
                "language": repo["language"], "n_lineages": summary.get("n_lineages"),
                "n_file_errors": summary.get("n_file_errors"), "elapsed_seconds": round(elapsed, 1),
            })
        except Exception as e:
            fail_count += 1
            _append_rows(err_path, [{
                "repo_id": repo["repo_id"], "full_name": repo["full_name"],
                "language": repo["language"], "error": str(e),
            }])
            print(f"  [FAIL] ({i}/{total}) {label}: {e}", flush=True)

        _write_progress(progress_path, started_at, total, ok_count + fail_count, ok_count, fail_count, label)

    if repo_summaries:
        pd.DataFrame(repo_summaries).to_csv(repo_summary_path, index=False)

    print(f"\ndone: {ok_count} ok, {fail_count} failed -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
