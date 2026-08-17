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
Use --limit/--repo to test on a handful of repos first. Use --stale-check
to report done-repo bookkeeping without running anything.

The resumability/progress plumbing itself now lives in
src/common/resumable_run.py (2026-08-17 extraction - this file,
pool_inhouse_metrics.py, and pool_inhouse_smells.py had independently
reimplemented the same done-keys/progress/error-file pattern) - see that
module's docstring for the schema_version/staleness behavior added at the
same time. This file's unit of "done" is one repo (repo_id, full_name),
not one snapshot-grid row, so it uses resumable_run's generic key_cols
support rather than the other two scripts' 4-column snapshot key.
"""

import argparse
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cs_entity_history  # noqa: E402
import py_entity_history  # noqa: E402
from entity_matching import _parse_date  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
import parallel_repo  # noqa: E402
import resumable_run as rr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "analysis"
MANIFEST_DIR = ROOT / "results" / "snapshots"
REPO_SUMMARY_DIR = ROOT / "results" / "repos"

DEFAULT_MAX_FILES_PER_REPO = 150

KEY_COLS = ["repo_id", "full_name"]

# Bump when a fix changes what "done" should mean for existing rows (e.g.
# the 2026-08-13 sorted-path sampling-bias fix or a future entity-matching
# change) - see resumable_run.py's docstring. Rows written under a prior
# schema_version are excluded from the done-set and reprocessed rather
# than trusted as-is; rows from before this tracking existed (no
# .runinfo.json sidecar) are still trusted, unaffected by this constant.
SCHEMA_VERSION = 1

LANGUAGE_BUILDER = {
    "Python": py_entity_history.build_repo_lineages,
    "C#": cs_entity_history.build_repo_lineages_cs,
}


def latest_manifest():
    files = sorted(MANIFEST_DIR.glob("*-repo-snapshot-manifest-*.csv"))
    if not files:
        raise FileNotFoundError(f"no manifest found in {MANIFEST_DIR}")
    return files[-1]


def load_intervention_dates(repo_summary_path=None):
    """{repo_id: parsed intervention_date} - the same file
    entity_history_windowed_cut.py already reads for Stage 6's lineage-
    level bucketing. Loaded once per run, not per repo - it's one small
    CSV, no reason to re-read it 21 times. A repo with no intervention_date
    in this file (shouldn't happen for anything in the Phase 2 manifest,
    but not assumed) is simply absent from the returned dict - callers
    treat a missing key the same way `--intervention-date-required=False`
    would, by skipping the pre/post columns for that repo rather than
    crashing the whole run over one repo's missing metadata."""
    if repo_summary_path is None:
        files = sorted(REPO_SUMMARY_DIR.glob("*-repo-summary-*.csv"))
        if not files:
            raise FileNotFoundError(f"no repo-summary csv found in {REPO_SUMMARY_DIR}")
        repo_summary_path = files[-1]
    df = pd.read_csv(repo_summary_path)
    df = df.dropna(subset=["intervention_date"])
    return {
        row["repo_id"]: _parse_date(row["intervention_date"])
        for _, row in df.iterrows()
    }


def eligible_repos(manifest_path):
    df = pd.read_csv(manifest_path)
    repos = (
        df[["repo_id", "full_name", "language"]]
        .drop_duplicates()
        .sort_values("full_name")
    )
    return repos[repos["language"].isin(LANGUAGE_BUILDER.keys())]


# repo-summary is a derived per-repo aggregate written alongside the real
# output (see main()) - it matches the same tag glob but isn't an
# independent output, so it's excluded from done-key loading (see
# resumable_run.load_done_keys's docstring).
_ENTITY_HISTORY_EXCLUDE_SUFFIXES = ("-errors.csv", "-repo-summary.csv")


def process_repo(repo_id, full_name, language, max_files_per_repo, threshold, dry_run,
                  intervention_date=None, seed=py_entity_history.DEFAULT_SEED):
    builder = LANGUAGE_BUILDER[language]
    if dry_run:
        repo_dir = py_entity_history.REPO_CACHE_DIR / py_entity_history._safe_dirname(full_name)
        row = {
            "repo_id": repo_id, "full_name": full_name, "language": language,
            "status": "dry_run", "repo_cache_exists": repo_dir.exists(),
            "has_intervention_date": intervention_date is not None,
        }
        return {"status": "dry_run", "n_lineages": None, "n_file_errors": None}, [row]

    rows = builder(
        full_name, limit_files=max_files_per_repo, threshold=threshold,
        intervention_date=intervention_date, seed=seed,
    )
    for row in rows:
        row["repo_id"] = repo_id
        row["full_name"] = full_name
        row["language"] = language
    n_ok = sum(1 for r in rows if r["status"] == "ok")
    n_err = sum(1 for r in rows if r["status"] == "error")
    return {"status": "ok", "n_lineages": n_ok, "n_file_errors": n_err}, rows


def _repo_scoped_stem(out_dir, tag, full_name):
    """Same continue-existing-or-mint-new stem convention main()'s
    single-run logic uses below, scoped to one repo (n=1, since this
    script's unit of work is already one whole repo) - the exact shape a
    manual `--repo <name>` invocation already produces, reused here so
    --workers>1's per-repo fragments are indistinguishable on disk from
    someone having run several --repo-scoped invocations by hand."""
    scope = re.sub(r"[^a-zA-Z0-9]+", "", full_name)[:30]
    scope_suffix = f"{scope}-1"
    existing = sorted(
        out_dir.glob(f"*-{tag}-{scope_suffix}.csv"),
        key=lambda p: p.stat().st_mtime,
    )
    if existing:
        return existing[-1].stem
    today = date.today()
    return f"{today.month:02d}-{today.day:02d}-{tag}-{scope_suffix}"


def _process_repo_group(
    full_name, repo, done_repos, dry_run, max_files_per_repo, threshold,
    seed, intervention_dates, tag,
):
    """Worker body for one repo under --workers > 1 - see
    src/common/parallel_repo.py's docstring for the dispatch mechanism.
    Must stay module-level (picklable by reference) to run in a
    ProcessPoolExecutor worker. `repo` is a plain dict (a DataFrame row's
    .to_dict()), unlike the sequential path below which iterates the
    DataFrame directly - dicts pickle cleanly across the process
    boundary."""
    key = (repo["repo_id"], repo["full_name"])
    stem = _repo_scoped_stem(OUT_DIR, tag, full_name)
    out_path = OUT_DIR / f"{stem}.csv"
    err_path = OUT_DIR / f"{stem}-errors.csv"
    progress_path = OUT_DIR / f"{stem}-progress.json"
    repo_summary_path = OUT_DIR / f"{stem}-repo-summary.csv"
    rr.write_runinfo(out_path, SCHEMA_VERSION)

    if key in done_repos:
        print(f"  [skip] {full_name}: already done", flush=True)
        return {"full_name": full_name, "ok": 1, "fail": 0, "out_path": str(out_path)}

    started_at = time.time()
    label = f"{repo['full_name']} ({repo['language']})"
    ok_count = fail_count = 0
    try:
        summary, rows = process_repo(
            repo["repo_id"], repo["full_name"], repo["language"],
            max_files_per_repo, threshold, dry_run,
            intervention_date=intervention_dates.get(repo["repo_id"]),
            seed=seed,
        )
        rr.append_rows(out_path, rows)
        elapsed = time.time() - started_at
        ok_count = 1
        print(
            f"  [ok] {full_name}: {summary.get('n_lineages', '-')} "
            f"lineage(s), {summary.get('n_file_errors', 0)} file "
            f"error(s), {elapsed:.1f}s", flush=True,
        )
        pd.DataFrame([{
            "repo_id": repo["repo_id"], "full_name": repo["full_name"],
            "language": repo["language"],
            "n_lineages": summary.get("n_lineages"),
            "n_file_errors": summary.get("n_file_errors"),
            "elapsed_seconds": round(elapsed, 1),
        }]).to_csv(repo_summary_path, index=False)
    except Exception as e:
        fail_count = 1
        rr.append_rows(err_path, [{
            "repo_id": repo["repo_id"], "full_name": repo["full_name"],
            "language": repo["language"], "error": str(e),
        }])
        print(f"  [FAIL] {full_name}: {e}", flush=True)

    rr.write_progress(
        progress_path, started_at, 1, ok_count + fail_count, ok_count,
        fail_count, label,
    )
    return {
        "full_name": full_name, "ok": ok_count, "fail": fail_count,
        "out_path": str(out_path),
    }


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
    parser.add_argument(
        "--seed", type=int, default=py_entity_history.DEFAULT_SEED,
        help="seed for the random file sample --max-files-per-repo takes "
             "(replaces plain sorted-order truncation, which correlated "
             "alphabetical path order with directory-creation history)",
    )
    parser.add_argument(
        "--stale-check", action="store_true",
        help="report done-repo bookkeeping (file count, oldest/newest, any "
             "stale schema_version exclusions) and exit without running "
             "anything - sanity-check before a real run.",
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="repos to process in parallel (default 1 = sequential, "
             "byte-identical to pre-concurrency behavior including the "
             "single unscoped output file). >1 dispatches one process per "
             "repo via ProcessPoolExecutor and writes one fragment file "
             "PER REPO instead - a different on-disk shape than an "
             "unscoped sequential run, though _load_done_keys() already "
             "handles either shape transparently. Doesn't fix the "
             "browser-use-style per-touch git-show hotspot (that's within "
             "one repo, not across repos - see the entity-history git-"
             "batching item in the scaling plan) but does mean one slow "
             "repo no longer blocks every other repo behind it.",
    )
    args = parser.parse_args()

    if args.stale_check:
        tag = "dryrun-entity-history" if args.dry_run else "entity-history"
        rr.stale_check_report(
            OUT_DIR, tag, KEY_COLS, schema_version=SCHEMA_VERSION,
            exclude_suffixes=_ENTITY_HISTORY_EXCLUDE_SUFFIXES,
        )
        return

    manifest_path = args.manifest or latest_manifest()
    repos = eligible_repos(manifest_path)
    print(f"manifest: {manifest_path} ({len(repos)} eligible repo(s), "
          f"Python or C#)", flush=True)

    intervention_dates = load_intervention_dates()
    n_missing = (~repos["repo_id"].isin(intervention_dates.keys())).sum()
    print(f"intervention dates loaded for {len(intervention_dates)} repo(s) "
          f"({n_missing} of this run's repos have none - pre/post churn "
          f"columns will be absent for those rows, not fabricated)", flush=True)

    if args.repo:
        repos = repos[repos["full_name"].str.contains(args.repo)]
    if args.limit:
        repos = repos.head(args.limit)
    total = len(repos)
    print(f"{total} repo(s) selected for this run "
          f"(--max-files-per-repo={args.max_files_per_repo})", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = "dryrun-entity-history" if args.dry_run else "entity-history"

    if args.workers > 1:
        done_repos = rr.load_done_keys(
            OUT_DIR, tag, KEY_COLS, schema_version=SCHEMA_VERSION,
            exclude_suffixes=_ENTITY_HISTORY_EXCLUDE_SUFFIXES,
        )
        items_by_repo = {
            row["full_name"]: row.to_dict()
            for _, row in repos.iterrows()
        }
        print(
            f"dispatching {len(items_by_repo)} repo(s) across "
            f"{args.workers} worker(s)", flush=True,
        )
        ok_total = fail_total = 0
        for full_name, summary in parallel_repo.run_by_repo(
            items_by_repo, _process_repo_group, workers=args.workers,
            worker_args=(
                done_repos, args.dry_run, args.max_files_per_repo,
                args.threshold, args.seed, intervention_dates, tag,
            ),
        ):
            ok_total += summary["ok"]
            fail_total += summary["fail"]
            print(
                f"[repo done] {full_name}: {summary['ok']} ok, "
                f"{summary['fail']} failed -> {summary['out_path']}",
                flush=True,
            )
        print(
            f"\ndone: {ok_total} ok, {fail_total} failed across "
            f"{len(items_by_repo)} repo(s)", flush=True,
        )
        return

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
    rr.write_runinfo(out_path, SCHEMA_VERSION)

    done_repos = rr.load_done_keys(
        OUT_DIR, tag, KEY_COLS, schema_version=SCHEMA_VERSION,
        exclude_suffixes=_ENTITY_HISTORY_EXCLUDE_SUFFIXES,
    )
    if done_repos:
        print(f"resuming: {len(done_repos)} repo(s) already done, skipping", flush=True)

    started_at = time.time()
    ok_count, fail_count = len(done_repos), 0
    repo_summaries = []
    for i, (_, repo) in enumerate(repos.iterrows(), start=1):
        key = rr.row_key_tuple(repo, KEY_COLS)
        label = f"{repo['full_name']} ({repo['language']})"
        if key in done_repos:
            continue

        t0 = time.time()
        try:
            summary, rows = process_repo(
                repo["repo_id"], repo["full_name"], repo["language"],
                args.max_files_per_repo, args.threshold, args.dry_run,
                intervention_date=intervention_dates.get(repo["repo_id"]),
                seed=args.seed,
            )
            rr.append_rows(out_path, rows)
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
            rr.append_rows(err_path, [{
                "repo_id": repo["repo_id"], "full_name": repo["full_name"],
                "language": repo["language"], "error": str(e),
            }])
            print(f"  [FAIL] ({i}/{total}) {label}: {e}", flush=True)

        rr.write_progress(progress_path, started_at, total, ok_count + fail_count, ok_count, fail_count, label)

    if repo_summaries:
        pd.DataFrame(repo_summaries).to_csv(repo_summary_path, index=False)

    print(f"\ndone: {ok_count} ok, {fail_count} failed -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
