"""
Phase 1d: run DPy (Python repos) / Designite (C# repos) against every
resolved snapshot in the Phase 1c manifest, and consolidate their
smell/metric output into one table keyed by
(repo_id, track, target_date, commit_sha).

BLOCKED ON TOOL INSTALL (see Writing/ProjectUpdate.md): neither DPy nor
Designite is installed in this environment, and both are commercial tools
from designite-tools.com whose exact CLI invocation and output format I
have not verified. The checkout/orchestration below is real and testable
now via --dry-run; run_dpy() / run_designite() / parse_tool_output() are
stubs marked with TODOs - fill them in once the tools are installed and
you've confirmed the real invocation syntax and output schema against the
actual binaries. Point DPY_EXECUTABLE / DESIGNITE_EXECUTABLE at the
installed executables via env var once that's done.

Pipeline, per eligible manifest row (no_prior_commit == False):
1. Resolve the repo's cached clone (data/repo_cache/<owner>__<repo>/, built
   by repo_snapshot_pipeline.py / Phase 1c).
2. `git checkout --detach <commit_sha>` in that clone. The clone is a
   blob:none partial clone, so this can trigger a lazy blob fetch from
   origin the first time a given commit's files are touched.
3. Route by the row's `language`: Python -> run_dpy(), C# -> run_designite().
   Each tool's raw output lands in data/tool_output/<repo>__<track>__<date>/
   (gitignored scratch space) and gets flattened by parse_tool_output().
4. Append the parsed row (tagged with repo_id/track/target_date/commit_sha)
   to the consolidated output CSV. A row that fails (checkout error, tool
   crash, parse error) is logged to a separate errors CSV rather than
   aborting the whole run.

Use --dry-run to smoke-test steps 1-2 and the row bookkeeping without
needing the tools installed at all. Use --limit to test on a handful of
rows before committing to a full run across all 480 manifest rows.
"""

import argparse
import os
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CLONE_CACHE_DIR = ROOT / "data" / "repo_cache"
TOOL_OUTPUT_DIR = ROOT / "data" / "tool_output"
MANIFEST_DIR = ROOT / "results" / "snapshots"
OUT_DIR = ROOT / "results" / "analysis"

CHECKOUT_TIMEOUT_SECONDS = 600
TOOL_TIMEOUT_SECONDS = 900

# Set these once DPy / Designite are installed - see module docstring.
DPY_EXECUTABLE = os.environ.get("DPY_EXECUTABLE")
DESIGNITE_EXECUTABLE = os.environ.get("DESIGNITE_EXECUTABLE")

LANGUAGE_TOOL = {
    "Python": "dpy",
    "C#": "designite",
}


def _safe_dirname(full_name):
    return full_name.replace("/", "__")


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


def checkout(repo_dir, commit_sha):
    # -c core.longpaths=true: airbyte/aspire have test-fixture paths past
    # Windows' 260-char MAX_PATH (same issue clone_repo() in
    # repo_snapshot_pipeline.py hit and worked around at clone time).
    subprocess.run(
        ["git", "-c", "core.longpaths=true", "checkout",
         "--detach", "--quiet", commit_sha],
        cwd=repo_dir, check=True, capture_output=True, text=True,
        timeout=CHECKOUT_TIMEOUT_SECONDS,
    )


def run_dpy(repo_dir, out_dir):
    """
    TODO (blocked on install - see module docstring): confirm DPy's real
    CLI once it's installed. This invocation is an UNCONFIRMED placeholder -
    don't trust the flags or output location until checked against the
    actual binary.
    """
    if not DPY_EXECUTABLE:
        raise RuntimeError(
            "DPY_EXECUTABLE not set - install DPy and set the env var to "
            "its executable path before running without --dry-run."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [DPY_EXECUTABLE, "-i", str(repo_dir), "-o", str(out_dir)],
        check=True, capture_output=True, text=True,
        timeout=TOOL_TIMEOUT_SECONDS,
    )
    return out_dir


def run_designite(repo_dir, out_dir):
    """
    TODO (blocked on install - see module docstring): DesigniteJava's public
    OSS variant documents `java -jar DesigniteJava.jar -i <input> -o
    <output>`, but this study needs the commercial C# Designite product,
    whose CLI I have not verified. Confirm against the actual installed
    tool before trusting this.
    """
    if not DESIGNITE_EXECUTABLE:
        raise RuntimeError(
            "DESIGNITE_EXECUTABLE not set - install Designite and set the "
            "env var to its executable path before running without --dry-run."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [DESIGNITE_EXECUTABLE, "-i", str(repo_dir), "-o", str(out_dir)],
        check=True, capture_output=True, text=True,
        timeout=TOOL_TIMEOUT_SECONDS,
    )
    return out_dir


def parse_tool_output(out_dir, language):
    """
    TODO (blocked on install - see module docstring): both tools' actual
    output schema (filenames, columns) is unconfirmed. Once run_dpy() /
    run_designite() produce real output, replace this stub with the real
    parse - read whatever files land in out_dir and flatten them into the
    metric/smell columns described in Writing/Longitudinal.md (design smell
    density, implementation smell density, OO metric distributions, etc.).
    """
    raise NotImplementedError(
        f"parse_tool_output() is a stub - fill in once the {language} "
        "tool's output format is confirmed (see module docstring)."
    )


def process_row(row, dry_run):
    repo_dir = CLONE_CACHE_DIR / _safe_dirname(row["full_name"])
    if not (repo_dir / ".git").exists():
        raise FileNotFoundError(
            f"{row['full_name']} not cloned at {repo_dir} - run "
            "repo_snapshot_pipeline.py (Phase 1c) first"
        )

    checkout(repo_dir, row["commit_sha"])

    if dry_run:
        return {**_snapshot_key(row), "status": "dry_run"}

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
        run_dpy(repo_dir, out_dir)
    else:
        run_designite(repo_dir, out_dir)

    metrics = parse_tool_output(out_dir, row["language"])
    return {**_snapshot_key(row), **metrics, "status": "ok"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=None,
        help="snapshot manifest csv (default: latest in results/snapshots/)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="checkout each commit and record bookkeeping only - "
             "skip the actual DPy/Designite call",
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
    args = parser.parse_args()

    manifest_path = args.manifest or latest_manifest()
    manifest = pd.read_csv(manifest_path)
    print(f"manifest: {manifest_path} ({len(manifest)} rows)")

    eligible = manifest[
        (~manifest["no_prior_commit"]) & manifest["commit_sha"].notna()
    ].sort_values("full_name")
    if args.repo:
        eligible = eligible[eligible["full_name"].str.contains(args.repo)]
    if args.limit:
        eligible = eligible.head(args.limit)
    print(f"{len(eligible)} eligible row(s) (have a resolved commit)")

    results, errors = [], []
    for _, row in eligible.iterrows():
        label = (
            f"{row['full_name']} {row['track']} {row['target_date'][:10]} "
            f"@{row['commit_sha'][:8]}"
        )
        try:
            results.append(process_row(row, args.dry_run))
            print(f"  [ok] {label}")
        except Exception as e:
            print(f"  [FAIL] {label}: {e}")
            errors.append({**_snapshot_key(row), "error": str(e)})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    stem = f"{today.month:02d}-{today.day:02d}-smell-metrics"

    out_path = OUT_DIR / f"{stem}-{len(results)}.csv"
    pd.DataFrame(results).to_csv(out_path, index=False)
    print(f"\n{len(results)} row(s) -> {out_path}")

    if errors:
        err_path = OUT_DIR / f"{stem}-errors-{len(errors)}.csv"
        pd.DataFrame(errors).to_csv(err_path, index=False)
        print(f"{len(errors)} error(s) -> {err_path}")


if __name__ == "__main__":
    main()
