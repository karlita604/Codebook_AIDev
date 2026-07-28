"""
Phase 1d: run DPy (Python repos) / Designite (C# repos) against every
materialized snapshot from Phase 1e (materialize_snapshots.py), and
consolidate their smell/metric output into one table keyed by
(repo_id, track, target_date, commit_sha).

STATUS (2026-07-27, see Writing/ProjectUpdate.md for the full history):
- DPy is installed and wired in for real (run_dpy_chunked / parse_tool_output
  below). Its Trial license caps CSV export at <10,000 LOC per invocation -
  every pilot Python snapshot is far over that - so large snapshots are
  split into sub-10K-LOC chunks along real package boundaries and DPy is run
  once per chunk (see run_dpy_chunked's docstring for what that does and
  does NOT make safe to pool across chunks).
- Designite is installed but blocked on a design decision: it requires an
  actual .sln (Roslyn MSBuildWorkspace), and materialized C# snapshots only
  contain *.cs files. run_designite() raises a clear NotImplementedError
  rather than guessing.

Pipeline, per eligible manifest row (has a resolved AND materialized commit):
1. Look up the already-materialized source tree at
   data/snapshots/<owner>__<repo>/<commit_sha>/ (built by
   materialize_snapshots.py / Phase 1e - language-filtered via `git archive`,
   so this is already just the repo's .py or .cs files at that commit,
   nothing else). Rows whose commit was never materialized (e.g. the 2
   crewAI commits that hit a Windows filename incompatibility - see
   Longitudinal.md S8) are skipped and logged as errors, not silently
   checked out from data/repo_cache/ as a fallback - that raw clone is
   Phase 1c/1e's working data, not something this phase should touch itself.
2. Route by the row's `language`: Python -> run_dpy_chunked(), C# ->
   run_designite(). Each tool's raw output lands in
   data/tool_output/<repo>__<track>__<date>/ (gitignored scratch space) and
   gets flattened by parse_tool_output().
3. Append the parsed row (tagged with repo_id/track/target_date/commit_sha)
   to the consolidated output CSV. A row that fails (missing snapshot, tool
   crash, parse error) is logged to a separate errors CSV rather than
   aborting the whole run.

Use --dry-run to smoke-test the snapshot lookup and row bookkeeping without
needing the tools installed at all. Use --limit/--repo to test on a handful
of rows before committing to a full run across all manifest rows.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from materialize_snapshots import SNAPSHOT_DIR, _is_materialized, _safe_dirname  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TOOL_OUTPUT_DIR = ROOT / "data" / "tool_output"
MANIFEST_DIR = ROOT / "results" / "snapshots"
OUT_DIR = ROOT / "results" / "analysis"

TOOL_TIMEOUT_SECONDS = 900

# DPy Trial rejects CSV export at >=10,000 LOC (see run_dpy). Cap chunks
# below that with headroom, since our line count (naive readlines()) won't
# exactly match whatever DPy counts internally (blank lines, encoding, etc).
DPY_LOC_CAP = 8000

# Set these once DPy / Designite are installed - see module docstring.
DPY_EXECUTABLE = os.environ.get("DPY_EXECUTABLE")
DESIGNITE_EXECUTABLE = os.environ.get("DESIGNITE_EXECUTABLE")

LANGUAGE_TOOL = {
    "Python": "dpy",
    "C#": "designite",
}


def _snapshot_key(row):
    return {
        "repo_id": row["repo_id"],
        "full_name": row["full_name"],
        "language": row["language"],
        "track": row["track"],
        "target_date": row["target_date"],
        "commit_sha": row["commit_sha"],
    }


def latest_manifest():
    manifests = sorted(MANIFEST_DIR.glob("*-repo-snapshot-manifest-*.csv"))
    if not manifests:
        raise FileNotFoundError(
            f"No snapshot manifest found in {MANIFEST_DIR} - "
            "run repo_snapshot_pipeline.py (Phase 1c) first"
        )
    return manifests[-1]


def run_dpy(snapshot_dir, out_dir):
    """
    CLI confirmed 2026-07-27 against the real DPy.exe (`analyze --help`):
    `DPy.exe analyze -i <input dir> -o <output dir> -f csv`. Writes
    <out_dir>/<input-dirname>_<suffix>.csv - see parse_tool_output() for the
    confirmed filenames/columns. Analyzes snapshot_dir recursively (a single
    call against all of `mlflow` counted "412 packages" in one pass), so the
    caller controls scope entirely via what directory it's pointed at - see
    run_dpy_chunked(), which is what process_row() actually calls.

    KNOWN BLOCKER: the installed license is Trial, which caps CSV export at
    <10,000 LOC *per invocation* (confirmed: a small ~3K-LOC subdirectory of
    mlflow exported full CSVs; the whole ~271K-LOC mlflow snapshot only
    wrote a log file). See run_dpy_chunked() for the workaround and its
    tradeoffs, and DPY_LOC_CAP above.
    """
    if not DPY_EXECUTABLE:
        raise RuntimeError(
            "DPY_EXECUTABLE not set - install DPy and set the env var to "
            "its executable path before running without --dry-run."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [DPY_EXECUTABLE, "analyze", "-i", str(snapshot_dir), "-o", str(out_dir), "-f", "csv"],
            check=True, capture_output=True, text=True,
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as e:
        # CalledProcessError's default __str__ is just "returned non-zero
        # exit status N" - the actual DPy error message (in stdout/stderr)
        # is what's useful in the errors CSV, so fold it in explicitly.
        raise RuntimeError(
            f"DPy exited {e.returncode} on {snapshot_dir}: "
            f"{(e.stdout or '').strip()[-500:]} {(e.stderr or '').strip()[-500:]}".strip()
        ) from e
    return out_dir


def _file_line_count(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _py_line_count(dir_path):
    return sum(_file_line_count(p) for p in Path(dir_path).rglob("*.py"))


def _stage_loose_files(files, stage_root, label):
    """DPy needs a directory, not a file list. Only used for *.py files that
    sit directly in a directory which itself had to be split (its
    subdirectories become their own chunks below it) - there's no existing
    directory containing exactly those loose files, so copy them into a
    fresh one rather than drop them."""
    dest = Path(stage_root) / f"loose__{label}"
    dest.mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy2(f, dest / f.name)
    return dest


def _bin_pack_files(files, cap):
    """Greedily group files into batches each under `cap` total LOC (a
    single file bigger than cap alone becomes its own oversized batch -
    nothing left to split it further by). Needed alongside directory-level
    splitting because a directory can be flat (many loose files, no
    subdirectories) and still be way over cap - e.g. mlflow/utils has 57
    loose .py files totaling 17K LOC with no child directories at all."""
    batches, current, current_loc = [], [], 0
    for f in files:
        loc = _file_line_count(f)
        if current and current_loc + loc > cap:
            batches.append(current)
            current, current_loc = [], 0
        current.append(f)
        current_loc += loc
    if current:
        batches.append(current)
    return batches


def plan_dpy_chunks(snapshot_dir, cap=DPY_LOC_CAP, stage_root=None, _label="root"):
    """Partition snapshot_dir's *.py files into directory paths, each with
    recursive LOC under `cap`, that together cover every file exactly once -
    no overlap, no gap - by splitting at *real* subdirectory boundaries
    first (recursing into children), then bin-packing whatever's left over
    (loose files with no subdirectory to group by) into further sub-cap
    batches. Only a single file individually bigger than cap can still come
    back oversized - the caller (run_dpy_chunked) checks for and logs that
    rather than silently losing data.
    """
    snapshot_dir = Path(snapshot_dir)
    total = _py_line_count(snapshot_dir)
    if total <= cap:
        return [snapshot_dir]

    subdirs = [p for p in snapshot_dir.iterdir() if p.is_dir()]
    loose = [p for p in snapshot_dir.iterdir() if p.is_file() and p.suffix == ".py"]

    chunks = []
    for d in subdirs:
        chunks.extend(plan_dpy_chunks(d, cap, stage_root, _label=f"{_label}__{d.name}"))
    for i, batch in enumerate(_bin_pack_files(loose, cap)):
        chunks.append(_stage_loose_files(batch, stage_root, f"{_label}__loose{i}"))
    return chunks


def run_dpy_chunked(snapshot_dir, out_dir, verbose=False):
    """
    Works around DPy's Trial license cap (see run_dpy) by splitting
    snapshot_dir into sub-DPY_LOC_CAP chunks along real package boundaries
    (plan_dpy_chunks) and running DPy once per chunk into its own
    out_dir/chunk_NNN/ subfolder - always chunked (even a single-chunk
    snapshot gets chunk_000/), so parse_tool_output() has one consistent
    shape to read.

    A single row can have 100-300+ chunks (mlflow: 304) at ~3-4s each, so a
    whole row can easily run 15-20+ minutes with *zero* output otherwise -
    verbose=True prints one line per chunk (index/total, LOC, timing, a
    running ETA for the rest of *this row*) so a long silence in the log
    doesn't look indistinguishable from a hang.

    IMPORTANT, per the 2026-07-27 decision (Writing/ProjectUpdate.md):
    class/method-level metrics and design/implementation smells are valid
    to pool across chunks - they're local to a class or method regardless
    of what else DPy could see in the same run. Architecture-level smells
    (God component, Feature concentration - *_arch_smells.csv) and
    Fan-In/Fan-Out (in *_class_module_metrics.csv) are NOT repo-wide when
    computed this way: each chunk only sees its own slice of the codebase,
    so those numbers reflect coupling *within the chunk*, not the real repo.
    They are still collected (nothing is discarded) but parse_tool_output()
    keeps them clearly chunk-scoped rather than folding them into the
    primary metric row - do not change that without re-deriving them from a
    real whole-repo DPy run (i.e. a Professional license).
    """
    stage_root = Path(tempfile.mkdtemp(prefix="dpy_chunks_"))
    try:
        chunks = plan_dpy_chunks(snapshot_dir, stage_root=stage_root)
        oversized = [c for c in chunks if _py_line_count(c) > DPY_LOC_CAP]
        if oversized:
            print(f"    [dpy] WARNING: {len(oversized)} chunk(s) still over "
                  f"{DPY_LOC_CAP} LOC and can't be split further (no "
                  f"subdirectories) - DPy will skip CSV export for these: "
                  f"{[str(c) for c in oversized]}", flush=True)

        if verbose:
            total_loc = sum(_py_line_count(c) for c in chunks)
            print(f"    [dpy] {len(chunks)} chunk(s) planned, {total_loc} total LOC", flush=True)

        row_started_at = time.time()
        for i, chunk_dir in enumerate(chunks):
            chunk_started_at = time.time()
            run_dpy(chunk_dir, out_dir / f"chunk_{i:03d}")
            if verbose:
                chunk_elapsed = time.time() - chunk_started_at
                row_elapsed = time.time() - row_started_at
                avg = row_elapsed / (i + 1)
                eta_min = avg * (len(chunks) - i - 1) / 60
                loc = _py_line_count(chunk_dir)
                print(f"    [dpy] chunk {i+1}/{len(chunks)} ({loc} LOC) done in "
                      f"{chunk_elapsed:.1f}s - ~{eta_min:.1f}min left in this row", flush=True)
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)
    return out_dir


def run_designite(snapshot_dir, out_dir):
    """
    KNOWN BLOCKER, confirmed 2026-07-27: DesigniteConsole's `-i`/`--input`
    requires an actual .sln - it's Roslyn MSBuildWorkspace-based (confirmed
    via its BuildHost-net472/netcore DLLs and decompiled strings:
    InterpretBatchFile/GetAllSolutionPaths/IsSolutionFile/OpenSolutionAsync
    all route through solution-level loading), not a plain source-file
    scanner like DPy. Its "batch file" input mode (mentioned in --help) is
    NOT an alternative to needing a .sln - it's just a text file listing
    multiple .sln paths to analyze in one run, confirmed by decompiling
    DesigniteConsole.dll. Tested directly against a materialized snapshot
    dir (just *.cs files, no .sln) and it fails immediately: "Argument
    error!! The specified file doesn't exists: <dir>". Also:
    `DesigniteConsole.exe` (no args) reports no .NET SDK installed, only
    runtimes - even with a .sln, MSBuildWorkspace may need the SDK to
    resolve projects.

    Needs a design decision before this can be implemented for real:
    re-materialize C# snapshots with .sln/.csproj included (git archive
    pathspec currently only pulls *.cs - see materialize_snapshots.py
    LANGUAGE_PATHSPEC) and get the .NET SDK installed. Deferred per the
    2026-07-27 decision to focus on DPy/Python first (see
    Writing/Longitudinal.md Open decisions). Raising instead of guessing at
    an invocation known to fail.
    """
    if not DESIGNITE_EXECUTABLE:
        raise RuntimeError(
            "DESIGNITE_EXECUTABLE not set - install Designite and set the "
            "env var to its executable path before running without --dry-run."
        )
    raise NotImplementedError(
        "run_designite() is blocked on a design decision, not just a missing "
        "executable - see this function's docstring: DesigniteConsole needs "
        "a .sln, and materialized C# snapshots only contain .cs files."
    )


def _read_chunked_csv(out_dir, suffix):
    """Concatenate <chunk>/*<suffix> across every chunk_*/ subfolder,
    tagging each row with which chunk it came from. Missing files (a smell
    category with zero instances isn't written at all) just contribute no
    rows - not an error."""
    frames = []
    for chunk_dir in sorted(Path(out_dir).glob("chunk_*")):
        for csv_path in chunk_dir.glob(f"*{suffix}"):
            df = pd.read_csv(csv_path)
            df["chunk"] = chunk_dir.name
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _parse_dpy_output(out_dir):
    class_module = _read_chunked_csv(out_dir, "_class_module_metrics.csv")
    functions = _read_chunked_csv(out_dir, "_function_metrics.csv")
    design_smells = _read_chunked_csv(out_dir, "_design_smells.csv")
    impl_smells = _read_chunked_csv(out_dir, "_implementation_smells.csv")
    # Chunk-scoped only - see run_dpy_chunked()'s docstring. Collected for
    # traceability, deliberately NOT folded into the pooled metrics below.
    arch_smells = _read_chunked_csv(out_dir, "_arch_smells.csv")

    if class_module.empty:
        classes = class_module
        total_loc = 0
    else:
        is_class_row = class_module["Class"].notna() & (class_module["Class"] != "")
        classes = class_module[is_class_row]
        total_loc = int(class_module.loc[~is_class_row, "LOC"].sum())

    n_methods = len(functions)

    def _pctl(df, col, q):
        return None if df.empty else float(df[col].quantile(q))

    return {
        "total_loc": total_loc,
        "n_chunks": len(list(Path(out_dir).glob("chunk_*"))),
        "n_classes": len(classes),
        "n_methods": n_methods,
        "class_loc_p50": _pctl(classes, "LOC", 0.5),
        "class_loc_p90": _pctl(classes, "LOC", 0.9),
        "method_loc_p50": _pctl(functions, "LOC", 0.5),
        "method_loc_p90": _pctl(functions, "LOC", 0.9),
        "cyclomatic_complexity_p50": _pctl(functions, "CC", 0.5),
        "cyclomatic_complexity_p90": _pctl(functions, "CC", 0.9),
        "design_smell_count": len(design_smells),
        "design_smell_density_per_kloc": (len(design_smells) / total_loc * 1000) if total_loc else None,
        "implementation_smell_count": len(impl_smells),
        "implementation_smell_density_per_kloc": (len(impl_smells) / total_loc * 1000) if total_loc else None,
        # Explicitly chunk-scoped, NOT a repo-level measurement - see
        # run_dpy_chunked()'s docstring before using this for anything.
        "arch_smell_count_chunk_scoped": len(arch_smells),
    }


def parse_tool_output(out_dir, language):
    """
    Designite: still fully unconfirmed - see run_designite()'s blocker.

    DPy: schema confirmed 2026-07-27 against real DPy.exe output (a tiny
    synthetic file under the Trial cap, and a real ~3K-LOC mlflow
    subdirectory). With -f csv it writes <out_dir>/<input-dirname>_<suffix>.csv:
      - _class_module_metrics.csv - Project,Package,Module,Class,LOC,WMC,NOM,
        NOPM,NOF,NOPF,LCOM,Fan-In,Fan-Out,DIT,File. One row per module
        (Class empty) and one per class (Class set).
      - _function_metrics.csv - Project,Package,Module,Class,Method,LOC,CC,PC
        (CC = cyclomatic complexity, PC = param count). One row per method.
      - _implementation_smells.csv - Project,Package,Module,Class,Smell,
        Method,Line no,File,Description.
      - _design_smells.csv - Project,Package,Module,Smell,Class,Line no,File,
        Description.
      - _arch_smells.csv - Project,Package,Smell,Description. Chunk-scoped
        only when run via run_dpy_chunked() - see its docstring.
    ML smell CSV (_ml_smells.csv, guessed name) still unconfirmed - neither
    test project had one.
    """
    if language == "C#":
        raise NotImplementedError(
            "parse_tool_output() for Designite is a stub - blocked on "
            "run_designite() itself (see its docstring)."
        )
    return _parse_dpy_output(out_dir)


def process_row(row, dry_run, keep_tool_output=False, verbose=False):
    snapshot_dir = SNAPSHOT_DIR / _safe_dirname(row["full_name"]) / row["commit_sha"]
    if not _is_materialized(snapshot_dir):
        raise FileNotFoundError(
            f"{row['full_name']}@{row['commit_sha'][:8]} not materialized at "
            f"{snapshot_dir} - run materialize_snapshots.py (Phase 1e) first "
            "(or this commit is a known gap - see Longitudinal.md S8)"
        )

    if dry_run:
        n_files = sum(1 for p in snapshot_dir.rglob("*") if p.is_file())
        return {**_snapshot_key(row), "n_files": n_files, "status": "dry_run"}

    tool = LANGUAGE_TOOL.get(row["language"])
    if tool is None:
        raise ValueError(
            f"no DPy/Designite mapping for language={row['language']!r}"
        )

    snapshot_tag = (
        f"{_safe_dirname(row['full_name'])}__{row['track']}"
        f"__{row['target_date'][:10]}"
    )
    out_dir = TOOL_OUTPUT_DIR / snapshot_tag

    if tool == "dpy":
        run_dpy_chunked(snapshot_dir, out_dir, verbose=verbose)
    else:
        run_designite(snapshot_dir, out_dir)

    metrics = parse_tool_output(out_dir, row["language"])
    result = {**_snapshot_key(row), **metrics, "status": "ok"}

    # A full run can touch hundreds of chunks per row (each with its own
    # small CSVs) across hundreds of rows - clean up the raw per-chunk
    # scratch output once it's been pooled into `result`, so a multi-day run
    # doesn't accumulate hundreds of thousands of tiny files on disk.
    if not keep_tool_output and out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)

    return result


def _row_key_tuple(row):
    return (row["repo_id"], row["track"], row["target_date"], row["commit_sha"])


def _load_done_keys(tag):
    """Rows already recorded as `ok` in ANY prior real-output CSV matching
    this tag (results/analysis/*-<tag>-*.csv, excluding -errors.csv) - not
    just this invocation's own output file. This is what makes running
    several `--repo`-scoped processes in parallel safe: each one sees every
    other's completed rows immediately at startup and skips them, rather
    than only knowing about its own scope's file. Only successes count as
    done; a previously-errored row is retried, since some errors (a
    subprocess timeout, a transient file lock) aren't guaranteed to repeat."""
    done = set()
    key_cols = ["repo_id", "track", "target_date", "commit_sha"]
    for path in OUT_DIR.glob(f"*-{tag}-*.csv"):
        if path.name.endswith("-errors.csv"):
            continue
        df = pd.read_csv(path)
        done.update(df[key_cols].itertuples(index=False, name=None))
    return done


def _clear_stale_errors(tag, key):
    """A row that just succeeded may have a stale error record sitting in
    ANY errors CSV for this tag - not just this process's own - e.g. from
    an earlier scoped run, or a transient block (today's Smart App Control
    incident) that's since been resolved. Clear it everywhere so the errors
    CSVs stay an accurate picture of what's still actually broken, rather
    than accumulating entries for things that were retried and fixed."""
    key_cols = ["repo_id", "track", "target_date", "commit_sha"]
    for path in OUT_DIR.glob(f"*-{tag}-*-errors.csv"):
        df = pd.read_csv(path)
        if df.empty:
            continue
        mask = df[key_cols].apply(tuple, axis=1) == key
        if mask.any():
            df[~mask].to_csv(path, index=False)


def _append_row(path, row_dict):
    """Append one row to a CSV immediately, writing the header only if the
    file doesn't exist yet - so a crash mid-run loses at most the one row
    in flight, not everything done so far."""
    write_header = not path.exists()
    pd.DataFrame([row_dict]).to_csv(path, mode="a", header=write_header, index=False)


def _write_progress(progress_path, started_at, total, done, ok, failed, current_label):
    elapsed = time.time() - started_at
    rate = done / elapsed if elapsed > 0 else 0
    eta_seconds = (total - done) / rate if rate > 0 else None
    progress_path.write_text(json.dumps({
        "started_at": datetime.fromtimestamp(started_at, tz=timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "done": done,
        "ok": ok,
        "failed": failed,
        "elapsed_seconds": round(elapsed, 1),
        "eta_seconds": round(eta_seconds, 1) if eta_seconds is not None else None,
        "current": current_label,
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=None,
        help="snapshot manifest csv (default: latest in results/snapshots/)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="look up each materialized snapshot and record bookkeeping "
             "only - skip the actual DPy/Designite call",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="only process the first N eligible rows (smoke testing)",
    )
    parser.add_argument(
        "--repo", type=str, default=None,
        help="only process rows whose full_name contains this substring "
             "(e.g. --repo Dock, to smoke-test on a small repo)",
    )
    parser.add_argument(
        "--keep-tool-output", action="store_true",
        help="keep each row's raw per-chunk DPy/Designite CSVs in "
             "data/tool_output/ instead of deleting them once pooled "
             "(default: delete, since a full run can produce hundreds of "
             "thousands of small chunk files)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="print per-chunk progress within each row (index/total, LOC, "
             "timing, running ETA for the rest of that row) - a single row "
             "can be 100-300+ chunks and otherwise prints nothing until the "
             "whole row finishes, which can be 15-20+ minutes of silence",
    )
    args = parser.parse_args()

    manifest_path = args.manifest or latest_manifest()
    manifest = pd.read_csv(manifest_path)
    print(f"manifest: {manifest_path} ({len(manifest)} rows)", flush=True)

    eligible = manifest[
        (~manifest["no_prior_commit"]) & manifest["commit_sha"].notna()
    ].sort_values("full_name")
    if args.repo:
        eligible = eligible[eligible["full_name"].str.contains(args.repo)]
    if args.limit:
        eligible = eligible.head(args.limit)
    total = len(eligible)
    print(f"{total} eligible row(s) (have a resolved commit)", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = "dryrun" if args.dry_run else "smell-metrics"

    # Each process writes to its OWN file, scoped by --repo (falling back to
    # just the row count when unscoped) - this is what lets several --repo
    # processes run concurrently without racing on the same file (pandas
    # to_csv(mode="a") isn't safe for two writers) or fighting over which of
    # them writes the CSV header first.
    scope = re.sub(r"[^a-zA-Z0-9]+", "", args.repo)[:30] if args.repo else None
    scope_suffix = f"{scope}-{total}" if scope else str(total)

    # A multi-day run can restart on a different calendar day than it
    # started - stamping the filename with today's date would silently
    # orphan the prior file and redo all completed rows instead of
    # resuming. Reuse an existing same-scope output file (same tag + repo
    # scope) if one exists; only mint a fresh dated name for a genuinely new
    # run/scope.
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

    # Global, not just this file: sees every row any concurrently-running
    # --repo-scoped process (or a prior run under a different scope) has
    # already completed, so parallel workers never redo each other's work.
    done_keys = _load_done_keys(tag)
    if done_keys:
        print(f"resuming: {len(done_keys)} row(s) already done in {out_path}, skipping", flush=True)

    started_at = time.time()
    ok_count, fail_count = len(done_keys), 0
    for i, (_, row) in enumerate(eligible.iterrows(), start=1):
        label = (
            f"{row['full_name']} {row['track']} {row['target_date'][:10]} "
            f"@{row['commit_sha'][:8]}"
        )
        if _row_key_tuple(row) in done_keys:
            continue

        if args.verbose:
            print(f"  [row] ({i}/{total}) starting {label}", flush=True)

        try:
            result = process_row(
                row, args.dry_run,
                keep_tool_output=args.keep_tool_output, verbose=args.verbose,
            )
            _append_row(out_path, result)
            if not args.dry_run:
                _clear_stale_errors(tag, _row_key_tuple(row))
            ok_count += 1
            print(f"  [ok] ({i}/{total}) {label}", flush=True)
        except Exception as e:
            fail_count += 1
            _append_row(err_path, {**_snapshot_key(row), "error": str(e)})
            print(f"  [FAIL] ({i}/{total}) {label}: {e}", flush=True)

        _write_progress(progress_path, started_at, total, ok_count + fail_count, ok_count, fail_count, label)

    print(f"\ndone: {ok_count} ok, {fail_count} failed -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
