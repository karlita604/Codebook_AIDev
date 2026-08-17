"""
Shared resumability conventions for batch pipeline stages.

Extracted from pool_inhouse_metrics.py, pool_inhouse_smells.py, and
pool_entity_history.py, which independently reimplemented the same
done-keys/progress/error-file pattern (byte-for-byte identical in most of
these functions before this extraction). All three share this shape: a
batch runner iterates eligible rows/repos from a manifest, appends each
result to a tagged output CSV, tracks failures in a sibling -errors.csv,
and reports progress via a -progress.json sidecar - and crucially, treats
ANY prior output file matching a tag prefix as already done, so parallel
--repo-scoped runs and resumed runs never redo each other's work.

That "any prior file with this tag prefix counts as done" behavior is
deliberate and load-bearing (see each caller's own docstring) - this
module does not remove it. What it adds is a `schema_version` check: each
run stem can get a `<stem>.runinfo.json` sidecar recording the
schema_version its rows were produced under. A fragment file whose
runinfo.json schema_version doesn't match the version passed to
`load_done_keys` this run is excluded from the done-set (and reported)
instead of being silently trusted - so a bug fix that changes what "done"
should mean (e.g. the 2026-08-13 entity-history sorted-path sampling-bias
fix, or the Dock stale-clone fix) can be reflected by bumping a caller's
SCHEMA_VERSION constant, rather than relying on someone remembering to
manually move old files into an archive_*/ folder before re-running - the
workaround documented in PySmellDetection.md and RQ3_CodeTracking.md
after this exact footgun bit twice.

Fragment files with no runinfo.json at all (everything produced before
this module existed) are still trusted as done, by design - this is
additive protection going forward, not retroactive invalidation of
already-verified data sitting in results/analysis/.

long_analysis.py (the legacy DPy/Designite driver) is not migrated to
this module. It's being scoped down to pilot-only use (see
src/pipeline/run_pipeline.py's corpus-size gate) rather than run at
100/1000-repo scale, so the value of sharing this code there is low
relative to the risk of touching a path that still matters for licensed-
tool baseline recalibration.
"""

import json
import time
from pathlib import Path

import pandas as pd


def row_key_tuple(row, key_cols):
    return tuple(row[c] for c in key_cols)


def _runinfo_path(out_path):
    return Path(out_path).with_name(f"{Path(out_path).stem}.runinfo.json")


def load_done_keys(
    out_dir, tag, key_cols, schema_version=None, verbose=True,
    exclude_suffixes=("-errors.csv",),
):
    """Done-key set for `tag`, pooled across every prior
    `<out_dir>/*-{tag}-*.csv` fragment (excluding -errors.csv by default)
    - the convention every batch runner in this pipeline relies on so that
    parallel/resumed runs share progress. If `schema_version` is given, a
    fragment whose sibling `<stem>.runinfo.json` records a different
    schema_version is excluded (and reported) rather than trusted;
    fragments with no runinfo.json at all are still trusted (see module
    docstring).

    `exclude_suffixes` also filters out any other same-tag fragment that
    isn't a real per-row output file - e.g. pool_entity_history.py's
    `<stem>-repo-summary.csv` (one row per successfully-processed repo,
    same key columns, but a derived aggregate rather than an independent
    output the schema_version check should track) also matches the tag
    glob and would otherwise be double-read."""
    out_dir = Path(out_dir)
    done = set()
    n_trusted_files = 0
    n_skipped_stale = 0
    n_trusted_legacy = 0
    for path in sorted(out_dir.glob(f"*-{tag}-*.csv")):
        if any(path.name.endswith(suf) for suf in exclude_suffixes):
            continue
        runinfo_path = _runinfo_path(path)
        if schema_version is not None and runinfo_path.exists():
            try:
                info = json.loads(runinfo_path.read_text())
            except (json.JSONDecodeError, OSError):
                info = {}
            file_schema = info.get("schema_version")
            if file_schema != schema_version:
                n_skipped_stale += 1
                if verbose:
                    print(
                        f"  [stale] {path.name}: schema_version={file_schema!r} "
                        f"!= current {schema_version!r} - not counted as done, "
                        "will be reprocessed",
                        flush=True,
                    )
                continue
        elif not runinfo_path.exists():
            n_trusted_legacy += 1
        try:
            df = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            continue
        if not set(key_cols).issubset(df.columns):
            continue
        done.update(df[key_cols].itertuples(index=False, name=None))
        n_trusted_files += 1
    if verbose and (n_skipped_stale or n_trusted_legacy):
        print(
            f"  done-keys: {n_trusted_files} file(s) trusted "
            f"({n_trusted_legacy} pre-dating schema_version tracking), "
            f"{n_skipped_stale} stale file(s) excluded",
            flush=True,
        )
    return done


def write_runinfo(out_path, schema_version, extra=None):
    """Write `<stem>.runinfo.json` next to a run's output CSV, recording
    the schema_version this run's rows are being produced under. Call once
    per invocation (new or resumed) before the row loop starts - cheap,
    and keeps the sidecar in sync with whatever code actually wrote into
    the file this time."""
    payload = {"schema_version": schema_version, "updated_at": time.time()}
    if extra:
        payload.update(extra)
    _runinfo_path(out_path).write_text(json.dumps(payload, indent=2))


def stale_check_report(
    out_dir, tag, key_cols, schema_version=None,
    exclude_suffixes=("-errors.csv",),
):
    """--stale-check diagnostic: how many done-keys would be loaded, from
    how many files, oldest/newest - printed up front so drift is visible
    before a real run starts, instead of only discoverable after the fact
    by noticing a suspiciously instant "0 rows processed" resume."""
    out_dir = Path(out_dir)
    files = sorted(
        (
            p for p in out_dir.glob(f"*-{tag}-*.csv")
            if not any(p.name.endswith(suf) for suf in exclude_suffixes)
        ),
        key=lambda p: p.stat().st_mtime,
    )
    done = load_done_keys(
        out_dir, tag, key_cols, schema_version=schema_version, verbose=True,
        exclude_suffixes=exclude_suffixes,
    )
    print(
        f"\nstale-check: {len(done)} done-key(s) loaded from "
        f"{len(files)} matching file(s)",
        flush=True,
    )
    if files:
        oldest, newest = files[0], files[-1]
        print(f"  oldest: {oldest.name} ({time.ctime(oldest.stat().st_mtime)})",
              flush=True)
        print(f"  newest: {newest.name} ({time.ctime(newest.stat().st_mtime)})",
              flush=True)
    return done


def append_row(path, row_dict):
    """Append one row to a CSV immediately, writing the header only if
    the file doesn't exist yet - a crash mid-run loses at most the row in
    flight, not everything done so far."""
    write_header = not Path(path).exists()
    pd.DataFrame([row_dict]).to_csv(path, mode="a", header=write_header, index=False)


def append_rows(path, rows):
    if not rows:
        return
    write_header = not Path(path).exists()
    pd.DataFrame(rows).to_csv(path, mode="a", header=write_header, index=False)


def write_progress(progress_path, started_at, total, done, ok, failed, current):
    elapsed = time.time() - started_at
    rate = done / elapsed if elapsed > 0 else 0
    eta_seconds = (total - done) / rate if rate > 0 else None
    Path(progress_path).write_text(json.dumps({
        "started_at": started_at,
        "total": total,
        "done": done,
        "ok": ok,
        "failed": failed,
        "elapsed_seconds": round(elapsed, 1),
        "eta_seconds": round(eta_seconds, 1) if eta_seconds is not None else None,
        "current": current,
    }))
