"""
Batch runner for py_smells.py - same CLI shape, resumability, and
progress/error-file conventions as pool_inhouse_metrics.py (which this
mirrors deliberately - same pipeline, same manifest/snapshot inputs, just
the smell-detection engine instead of the OO-metrics one). See
Writing/PySmellDetection.md for the detection strategies themselves and
Writing/InHouseTooling.md for why an in-house tool exists at all.

Use --dry-run to smoke-test snapshot lookup/bookkeeping without running the
analyzer. Use --limit/--repo to test on a handful of rows first.
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
import py_smells  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase0"))
from materialize_snapshots import (  # noqa: E402
    EXCLUDED_REPOS, SNAPSHOT_DIR, _is_materialized, _safe_dirname,
    latest_manifest,
)

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "analysis"


def _snapshot_key(row):
    return {
        "repo_id": row["repo_id"],
        "full_name": row["full_name"],
        "language": row["language"],
        "track": row["track"],
        "target_date": row["target_date"],
        "commit_sha": row["commit_sha"],
    }


def _row_key_tuple(row):
    return (
        row["repo_id"], row["track"], row["target_date"], row["commit_sha"],
    )


def _load_done_keys(tag):
    """Same convention as pool_inhouse_metrics.py's _load_done_keys():
    global across every prior real-output file matching this tag, not
    just this invocation's own, so parallel --repo-scoped runs never redo
    each other's work. Only successes count as done."""
    done = set()
    key_cols = ["repo_id", "track", "target_date", "commit_sha"]
    for path in OUT_DIR.glob(f"*-{tag}-*.csv"):
        if path.name.endswith("-errors.csv"):
            continue
        df = pd.read_csv(path)
        if not set(key_cols).issubset(df.columns):
            continue
        done.update(df[key_cols].itertuples(index=False, name=None))
    return done


def _append_row(path, row_dict):
    write_header = not path.exists()
    pd.DataFrame([row_dict]).to_csv(
        path, mode="a", header=write_header, index=False
    )


def _write_progress(
    progress_path, started_at, total, done, ok, failed, current
):
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
        "eta_seconds": (
            round(eta_seconds, 1) if eta_seconds is not None else None
        ),
        "current": current,
    }))


def process_row(row, dry_run):
    snapshot_dir = (
        SNAPSHOT_DIR / _safe_dirname(row["full_name"]) / row["commit_sha"]
    )
    if not _is_materialized(snapshot_dir):
        raise FileNotFoundError(
            f"{row['full_name']}@{row['commit_sha'][:8]} not materialized at "
            f"{snapshot_dir} - run materialize_snapshots.py (Phase 1e) first"
        )

    if dry_run:
        n_files = sum(1 for p in snapshot_dir.rglob("*.py") if p.is_file())
        return {
            **_snapshot_key(row), "n_py_files": n_files, "status": "dry_run",
        }

    smells = py_smells.analyze_snapshot(snapshot_dir)
    return {**_snapshot_key(row), **smells}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=None,
        help="snapshot manifest csv (default: latest in results/snapshots/)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="look up each materialized snapshot and record bookkeeping "
             "only - skip the actual smell analysis",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="only process the first N eligible rows (smoke testing)",
    )
    parser.add_argument(
        "--repo", type=str, default=None,
        help="only process rows whose full_name contains this substring",
    )
    args = parser.parse_args()

    manifest_path = args.manifest or latest_manifest()
    manifest = pd.read_csv(manifest_path)
    print(f"manifest: {manifest_path} ({len(manifest)} rows)", flush=True)

    eligible = manifest[
        manifest["commit_sha"].notna()
        & (manifest["language"] == "Python")
        & ~manifest["full_name"].isin(EXCLUDED_REPOS)
    ].sort_values("full_name")
    if args.repo:
        eligible = eligible[eligible["full_name"].str.contains(args.repo)]
    if args.limit:
        eligible = eligible.head(args.limit)
    total = len(eligible)
    print(
        f"{total} eligible Python row(s) (have a resolved commit)",
        flush=True,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = "dryrun-inhouse-smells" if args.dry_run else "inhouse-smells-python"

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

    done_keys = _load_done_keys(tag)
    if done_keys:
        print(
            f"resuming: {len(done_keys)} row(s) already done in {out_path}, "
            "skipping",
            flush=True,
        )

    started_at = time.time()
    ok_count, fail_count = len(done_keys), 0
    for i, (_, row) in enumerate(eligible.iterrows(), start=1):
        label = (
            f"{row['full_name']} {row['track']} {row['target_date'][:10]} "
            f"@{row['commit_sha'][:8]}"
        )
        if _row_key_tuple(row) in done_keys:
            continue

        try:
            result = process_row(row, args.dry_run)
            _append_row(out_path, result)
            ok_count += 1
            print(f"  [ok] ({i}/{total}) {label}", flush=True)
        except Exception as e:
            fail_count += 1
            _append_row(err_path, {**_snapshot_key(row), "error": str(e)})
            print(f"  [FAIL] ({i}/{total}) {label}: {e}", flush=True)

        _write_progress(
            progress_path, started_at, total,
            ok_count + fail_count, ok_count, fail_count, label,
        )

    print(
        f"\ndone: {ok_count} ok, {fail_count} failed -> {out_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
