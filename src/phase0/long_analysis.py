"""
Phase 1d: run DPy (Python repos) / Designite (C# repos) against every
materialized snapshot from Phase 1e (materialize_snapshots.py), and
consolidate their smell/metric output into one table keyed by
(repo_id, track, target_date, commit_sha).

STATUS (2026-07-28, see Writing/Longitudinal.md S8 for the full history):
- DPy is installed and wired in for real (run_dpy_chunked / parse_tool_output
  below). Its Trial license caps CSV export at <10,000 LOC per invocation -
  every pilot Python snapshot is far over that - so large snapshots are
  split into sub-10K-LOC chunks along real package boundaries and DPy is run
  once per chunk (see run_dpy_chunked's docstring for what that does and
  does NOT make safe to pool across chunks).
- Designite is installed and wired in for real (run_designite_chunked /
  parse_tool_output below), confirmed against wieslawsoltes/Dock only -
  dotnet/aspire is excluded from this pilot phase (see materialize_snapshots.py
  EXCLUDED_REPOS). Its Trial license caps CSV export at <50,000 LOC per
  invocation (a solution-wide total, not per-project) - over-cap solutions are
  split into sub-cap sub-solutions along whole-project boundaries (Designite
  analyzes at the project/solution level, not a raw source directory, so
  chunks can't split a single project's files like run_dpy_chunked does - see
  run_designite_chunked's docstring for what that does and does NOT make safe
  to pool across chunks). Dock commits after 2025-12-25 use `.slnx`
  (unsupported by the installed DesigniteConsole 5.3.0.0 build) and are a
  known, logged gap, not silently skipped.

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
from materialize_snapshots import (  # noqa: E402
    EXCLUDED_REPOS, SNAPSHOT_DIR, _is_materialized, _safe_dirname,
)

ROOT = Path(__file__).resolve().parents[2]
TOOL_OUTPUT_DIR = ROOT / "data" / "tool_output"
MANIFEST_DIR = ROOT / "results" / "snapshots"
OUT_DIR = ROOT / "results" / "analysis"

TOOL_TIMEOUT_SECONDS = 900

# DPy Trial rejects CSV export at >=10,000 LOC (see run_dpy). Cap chunks
# below that with headroom, since our line count (naive readlines()) won't
# exactly match whatever DPy counts internally (blank lines, encoding, etc).
DPY_LOC_CAP = 8000

# Designite Trial rejects CSV export at >=50,000 LOC per invocation - exact
# threshold confirmed directly in its own message text ("lesser than 50000
# lines of code"), unlike DPy's cap which had to be bisected empirically. Cap
# chunks below that with headroom, since our LOC proxy (raw *.cs line count
# per project directory) won't exactly match Designite's own count (confirmed
# close but not exact: a project measured at 7934 by `wc -l` was reported as
# 7884 by Designite).
DESIGNITE_LOC_CAP = 45000

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
    subprocess.run(
        [DPY_EXECUTABLE, "analyze", "-i", str(snapshot_dir), "-o", str(out_dir), "-f", "csv"],
        check=True, capture_output=True, text=True,
        timeout=TOOL_TIMEOUT_SECONDS,
    )
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


def run_dpy_chunked(snapshot_dir, out_dir):
    """
    Works around DPy's Trial license cap (see run_dpy) by splitting
    snapshot_dir into sub-DPY_LOC_CAP chunks along real package boundaries
    (plan_dpy_chunks) and running DPy once per chunk into its own
    out_dir/chunk_NNN/ subfolder - always chunked (even a single-chunk
    snapshot gets chunk_000/), so parse_tool_output() has one consistent
    shape to read.

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
                  f"{[str(c) for c in oversized]}")
        for i, chunk_dir in enumerate(chunks):
            run_dpy(chunk_dir, out_dir / f"chunk_{i:03d}")
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)
    return out_dir


# Solution-folder pseudo-entries (e.g. Dock.sln's "build"/"docs"/"src" groupings)
# use the same `Project(...)` syntax as real projects but point at a directory
# or loose file, not a .csproj - filtered out below by path suffix rather than
# by hardcoding the handful of type GUIDs involved (SDK-style
# {9A19103F-16F7-4668-BE54-9A1E7A4F7556}, legacy {FAE04EC0-301F-11D3-BF4B-...},
# solution folder {2150E333-8FDC-42A3-9474-1A3956D46DE8} - Dock.sln uses all
# three), since "does this line point at a real project file" is the thing we
# actually care about, not which GUID a given repo happens to use.
_SLN_PROJECT_RE = re.compile(
    r'^Project\("\{[0-9A-Fa-f-]+\}"\)\s*=\s*"[^"]+",\s*"([^"]+)",\s*"\{[0-9A-Fa-f-]+\}"',
    re.MULTILINE,
)


def _parse_sln_projects(sln_path):
    """Real C# projects listed in a .sln, as absolute .csproj paths, in the
    order they appear in the file (kept for deterministic, reproducible chunk
    planning - same reasoning as plan_dpy_chunks() recursing in a fixed
    order)."""
    text = sln_path.read_text(encoding="utf-8-sig", errors="ignore")
    projects = []
    for rel_path in _SLN_PROJECT_RE.findall(text):
        if rel_path.lower().endswith(".csproj"):
            projects.append((sln_path.parent / rel_path.replace("\\", "/")).resolve())
    return projects


def _project_line_count(csproj_path):
    """Naive proxy for a project's own LOC (its *.cs files only, not counting
    anything it references via ProjectReference) - same spirit as DPy's
    _py_line_count. Confirmed empirically (see Writing/Longitudinal.md S8,
    2026-07-28): a sub-solution listing only one project reports ~this many
    LOC to Designite, NOT inflated by projects it references but that aren't
    listed - MSBuildWorkspace only loads what's explicitly in the .sln."""
    return sum(
        _file_line_count(p) for p in csproj_path.parent.rglob("*.cs")
        if "bin" not in p.parts and "obj" not in p.parts
    )


def plan_designite_chunks(sln_path, cap=DESIGNITE_LOC_CAP):
    """Bin-pack a solution's real projects (whole projects only - unlike
    DPy's chunker, this can't split a single project's files, since Designite
    analyzes at project/solution granularity) into groups each under `cap`
    total LOC, greedily in .sln file order. A single project bigger than cap
    alone still comes back as its own oversized chunk (nothing left to split
    it further by) - the caller (run_designite_chunked) logs this rather than
    silently losing data, same as DPy's plan_dpy_chunks().

    Deliberately does NOT try to keep a project's ProjectReference closure
    together in one chunk: confirmed empirically that splitting connected
    projects across chunks doesn't crash or inflate LOC, it just leaves
    cross-chunk references unresolved - meaning Fan-In/Fan-Out and any smell
    that depends on an excluded project's types are NOT valid for that chunk.
    Same shape of tradeoff as DPy's chunk-scoped architecture smells (see
    run_dpy_chunked's docstring) - parse_tool_output() keeps this chunk-scoped
    rather than pooling it as repo-wide."""
    sized = [(p, _project_line_count(p)) for p in _parse_sln_projects(sln_path)]
    chunks, current, current_loc = [], [], 0
    for path, loc in sized:
        if current and current_loc + loc > cap:
            chunks.append(current)
            current, current_loc = [], 0
        current.append(path)
        current_loc += loc
    if current:
        chunks.append(current)
    return chunks


def _write_sub_solution(csproj_paths, dest_dir):
    """Generate a real, valid .sln listing exactly `csproj_paths`, via
    `dotnet sln` rather than hand-rolling the .sln text format (avoids having
    to reproduce VS's per-project-type GUID conventions correctly ourselves -
    `dotnet sln add` picks the right one from each .csproj automatically,
    confirmed against Dock's mix of SDK-style and legacy projects)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    sln_path = dest_dir / "chunk.sln"
    subprocess.run(
        ["dotnet", "new", "sln", "-n", "chunk", "-o", str(dest_dir)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    subprocess.run(
        ["dotnet", "sln", str(sln_path), "add", *[str(p) for p in csproj_paths]],
        check=True, capture_output=True, text=True, timeout=60,
    )
    return sln_path


def _run_designite_once(sln_path, out_dir):
    """One DesigniteConsole invocation. NOTE: DesigniteConsole exits 0
    unconditionally, even when the Trial LOC cap silently blocks CSV export
    (confirmed empirically - `check=True` alone would NOT catch a cap-hit) -
    the caller must verify out_dir actually has CSVs in it afterward."""
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [DESIGNITE_EXECUTABLE, "-i", str(sln_path), "-o", str(out_dir), "-c"],
        check=True, capture_output=True, text=True,
        timeout=TOOL_TIMEOUT_SECONDS,
    )
    if not any(out_dir.glob("*.csv")):
        raise RuntimeError(
            f"DesigniteConsole exited 0 but wrote no CSVs for {sln_path} - "
            f"most likely this chunk is still over the Trial LOC cap despite "
            f"our under-{DESIGNITE_LOC_CAP} plan (our LOC proxy underestimated "
            f"vs Designite's own count), rather than a real crash."
        )
    return out_dir


def run_designite(snapshot_dir, out_dir):
    """
    Resolved 2026-07-27/28 (see Writing/Longitudinal.md S8): DesigniteConsole
    needs a real .sln (Roslyn MSBuildWorkspace) - materialize_snapshots.py's
    C# pathspec now includes .sln/.slnx/.csproj/.props/.targets/packages.config
    (was *.cs-only). Confirmed working end-to-end against wieslawsoltes/Dock.

    Two known gaps, deliberately not papered over:
    - `.slnx`-only snapshots (Dock commits after 2025-12-25) raise
      NotImplementedError - this installed DesigniteConsole build (5.3.0.0)
      confirmed unable to open `.slnx` ("could not find any project to
      analyze"). Not the same as a missing/corrupt snapshot, so distinguished
      from the FileNotFoundError below.
    - Trial license caps CSV export at <50,000 LOC per invocation (a
      solution-wide total, not per-project) - handled by
      plan_designite_chunks()/_write_sub_solution() below, splitting the
      solution into sub-cap groups of whole projects. See
      plan_designite_chunks()'s docstring for what that does and does NOT
      make safe to pool across chunks (Fan-In/Fan-Out and cross-project
      smells are chunk-scoped only, same shape of caveat as DPy's
      run_dpy_chunked()).
    """
    if not DESIGNITE_EXECUTABLE:
        raise RuntimeError(
            "DESIGNITE_EXECUTABLE not set - install Designite and set the "
            "env var to its executable path before running without --dry-run."
        )
    snapshot_dir = Path(snapshot_dir)
    sln_candidates = list(snapshot_dir.glob("*.sln"))
    if not sln_candidates:
        if list(snapshot_dir.glob("*.slnx")):
            raise NotImplementedError(
                f"{snapshot_dir} only has a .slnx solution - unsupported by "
                "the installed DesigniteConsole build (5.3.0.0), confirmed "
                "via direct test (\"could not find any project to analyze\"). "
                "See Writing/Longitudinal.md Open decisions."
            )
        raise FileNotFoundError(f"no .sln found in {snapshot_dir}")
    sln_path = sln_candidates[0]

    chunks = plan_designite_chunks(sln_path)
    if len(chunks) == 1:
        # Whole solution already fits under the cap - analyze the real .sln
        # directly rather than regenerating an equivalent one via dotnet sln.
        return _run_designite_once(sln_path, out_dir / "chunk_000")

    oversized = [c for c in chunks if sum(_project_line_count(p) for p in c) > DESIGNITE_LOC_CAP]
    if oversized:
        print(f"    [designite] WARNING: {len(oversized)} chunk(s) still over "
              f"{DESIGNITE_LOC_CAP} LOC and can't be split further (a single "
              f"project alone exceeds the cap) - Designite will refuse CSV "
              f"export for these: {[[p.stem for p in c] for c in oversized]}")

    stage_root = Path(tempfile.mkdtemp(prefix="designite_chunks_"))
    try:
        for i, chunk_projects in enumerate(chunks):
            chunk_sln = _write_sub_solution(chunk_projects, stage_root / f"chunk_{i:03d}")
            _run_designite_once(chunk_sln, out_dir / f"chunk_{i:03d}")
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)
    return out_dir


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


def _parse_designite_output(out_dir):
    class_metrics = _read_chunked_csv(out_dir, "ClassMetrics.csv")
    method_metrics = _read_chunked_csv(out_dir, "MethodMetrics.csv")
    design_smells = _read_chunked_csv(out_dir, "DesignSmells.csv")
    impl_smells = _read_chunked_csv(out_dir, "ImpSmells.csv")
    testability_smells = _read_chunked_csv(out_dir, "TestabilitySmells.csv")
    test_smells = _read_chunked_csv(out_dir, "TestSmells.csv")
    # Chunk-scoped only - see plan_designite_chunks()'s docstring: a project
    # split into a different chunk from projects it references loses valid
    # Fan-In/Fan-Out and any smell depending on an excluded project's types.
    # Collected for traceability, deliberately NOT folded into the pooled
    # metrics below.
    arch_smells = _read_chunked_csv(out_dir, "ArchSmells.csv")

    total_loc = int(class_metrics["LOC"].sum()) if not class_metrics.empty else 0

    def _pctl(df, col, q):
        return None if df.empty else float(df[col].quantile(q))

    return {
        "total_loc": total_loc,
        "n_chunks": len(list(Path(out_dir).glob("chunk_*"))),
        "n_classes": len(class_metrics),
        "n_methods": len(method_metrics),
        "class_loc_p50": _pctl(class_metrics, "LOC", 0.5),
        "class_loc_p90": _pctl(class_metrics, "LOC", 0.9),
        "method_loc_p50": _pctl(method_metrics, "LOC", 0.5),
        "method_loc_p90": _pctl(method_metrics, "LOC", 0.9),
        "cyclomatic_complexity_p50": _pctl(method_metrics, "CC", 0.5),
        "cyclomatic_complexity_p90": _pctl(method_metrics, "CC", 0.9),
        "design_smell_count": len(design_smells),
        "design_smell_density_per_kloc": (len(design_smells) / total_loc * 1000) if total_loc else None,
        "implementation_smell_count": len(impl_smells),
        "implementation_smell_density_per_kloc": (len(impl_smells) / total_loc * 1000) if total_loc else None,
        # Designite-only categories, no DPy equivalent - kept as their own
        # columns rather than folded into design/implementation counts.
        "testability_smell_count": len(testability_smells),
        "test_smell_count": len(test_smells),
        # Explicitly chunk-scoped, NOT a repo-level measurement - see
        # plan_designite_chunks()'s docstring before using this for anything.
        "arch_smell_count_chunk_scoped": len(arch_smells),
    }


def parse_tool_output(out_dir, language):
    """
    Designite: schema confirmed 2026-07-28 against real DesigniteConsole
    output (wieslawsoltes/Dock, both under- and over-Trial-cap commits). With
    -c it writes <out_dir>/Designite_<project(+TFM)>_<Suffix>.csv - one full
    set of files per project in the solution (or sub-solution, when chunked):
      - ClassMetrics.csv - Project,Namespace,Class,NOF,NOM,NOP,NOPF,NOPM,LOC,
        WMC,NC,DIT,LCOM,Fan-Out,Fan-In,Fan-Out types,Fan-In types,File. One
        row per class.
      - MethodMetrics.csv - Project,Namespace,Class,Method,LOC,CC,PC (CC =
        cyclomatic complexity, PC = param count). One row per method.
      - NamespaceMetrics.csv - Project,Namespace,Ca types,Ce types
        (afferent/efferent coupling at namespace level) - collected but not
        currently pooled into parse_tool_output()'s output.
      - DesignSmells.csv / TestabilitySmells.csv / TestSmells.csv - Smell,
        Project,Namespace,Class,File,Description.
      - ImpSmells.csv - Smell,Project,Namespace,Class,File,Method,Description.
      - ArchSmells.csv - Smell,Project,Namespace,Description,Responsible
        classes,Participating classes. Chunk-scoped only when run via
        run_designite() with more than one chunk - see
        plan_designite_chunks()'s docstring.
    Multi-targeted projects (e.g. a project built for both net8.0 and
    net472) get a separate full set of files per target framework, with the
    TFM suffixed onto the project name (confirmed: "AvaloniaDemo.Debug" /
    "AvaloniaDemo.Perspectives" / "AvaloniaDemo.Xaml" / "AvaloniaDemo" all
    appeared for one project in one test run) - NOT deduplicated here, so a
    multi-targeted project's classes/methods currently get counted once per
    target framework. Needs a decision before this is used for anything where
    that would skew results (see DESIGNITE_TASK.md).

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
        return _parse_designite_output(out_dir)
    return _parse_dpy_output(out_dir)


def process_row(row, dry_run, keep_tool_output=False):
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
        run_dpy_chunked(snapshot_dir, out_dir)
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


def _load_done_keys(out_path):
    """Rows already recorded as `ok` in a prior (possibly crashed) run of
    this exact invocation - resume skips these rather than redoing
    potentially minutes of DPy work per row. Only successes count as done;
    a previously-errored row is retried, since some errors (a subprocess
    timeout, a transient file lock) aren't guaranteed to repeat."""
    if not out_path.exists():
        return set()
    df = pd.read_csv(out_path)
    key_cols = ["repo_id", "track", "target_date", "commit_sha"]
    return set(df[key_cols].itertuples(index=False, name=None))


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
    args = parser.parse_args()

    manifest_path = args.manifest or latest_manifest()
    manifest = pd.read_csv(manifest_path)
    print(f"manifest: {manifest_path} ({len(manifest)} rows)", flush=True)

    eligible = manifest[
        (~manifest["no_prior_commit"]) & manifest["commit_sha"].notna()
        & ~manifest["full_name"].isin(EXCLUDED_REPOS)
    ].sort_values("full_name")
    if args.repo:
        eligible = eligible[eligible["full_name"].str.contains(args.repo)]
    if args.limit:
        eligible = eligible.head(args.limit)
    total = len(eligible)
    print(f"{total} eligible row(s) (have a resolved commit)", flush=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    tag = "dryrun" if args.dry_run else "smell-metrics"
    stem = f"{today.month:02d}-{today.day:02d}-{tag}-{total}"
    out_path = OUT_DIR / f"{stem}.csv"
    err_path = OUT_DIR / f"{stem}-errors.csv"
    progress_path = OUT_DIR / f"{stem}-progress.json"

    done_keys = _load_done_keys(out_path)
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

        try:
            result = process_row(row, args.dry_run, keep_tool_output=args.keep_tool_output)
            _append_row(out_path, result)
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
