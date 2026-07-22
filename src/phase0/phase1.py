"""
Phase 1: Compile metadata for each PR before calculating metrics.

Given a csv where each row is a PR (one "id" column, e.g. the output of
PRfilter.py), join against the AIDev PR table on PR id to build a metadata
dataframe with one row per input PR id and the following columns:

# id (id)
# title (title)
# body (body)
# agent (agent)
# state (state)
# created_at (created_at)
# closed_at (closed_at)
# merged_at (merged_at)
# repo_id (repo_id)
# repo_url (repo_url)
# html_url (html_url)

The result is written to phase1_[inputfilename].csv in the same directory
as the input csv. (Phase 1.5, in metrics.py, adds the actual metric columns
on top of this metadata and stores the result under data/.)

Our default input csv: results/phase0/07-21-500-pycsharp-1387.csv

Running this file:
- Install deps first: pip install -r requirements.txt (pandas, pyarrow)
- Needs network access - reads all_pull_request.parquet from the hao-li/AIDev
  dataset on Hugging Face via hf:// on every run, nothing is cached locally.
- CLI: python phase1.py [--input path/to/prs.csv]
- Can also be imported: `from phase1 import build_metadata`
"""

import argparse
from pathlib import Path

import pandas as pd

DEFAULT_INPUT = (
    Path(__file__).resolve().parents[2] / "results" / "phase0" / "07-21-500-pycsharp-1387.csv"
)

METADATA_COLUMNS = [
    "id",
    "title",
    "body",
    "agent",
    "state",
    "created_at",
    "closed_at",
    "merged_at",
    "repo_id",
    "repo_url",
    "html_url",
]

all_pr_df = pd.read_parquet("hf://datasets/hao-li/AIDev/all_pull_request.parquet")
# id/repo_id are stored as int64 here; normalize so the merge below (against
# ids parsed from csv, which may come in as float64) doesn't silently drop rows.
all_pr_df["id"] = pd.to_numeric(all_pr_df["id"], errors="coerce")


def build_metadata(input_csv=DEFAULT_INPUT):
    """Given a csv of PR ids, return a dataframe of PR metadata (see METADATA_COLUMNS)."""
    ids_df = pd.read_csv(input_csv)
    id_col = "id" if "id" in ids_df.columns else "pr_id"
    ids_df = ids_df[[id_col]].rename(columns={id_col: "id"})
    ids_df["id"] = pd.to_numeric(ids_df["id"], errors="coerce")

    # Left join so the input csv's row order/count is preserved and any id
    # with no match in the PR table (e.g. since removed/renumbered) is kept
    # with NaN metadata rather than silently dropped.
    metadata_df = ids_df.merge(all_pr_df[METADATA_COLUMNS], on="id", how="left")
    return metadata_df


def _parse_args():
    parser = argparse.ArgumentParser(description="Compile PR metadata for a csv of PR ids.")
    parser.add_argument("--input", type=str, default=str(DEFAULT_INPUT),
                         help="path to a csv with an 'id' column (default: %(default)s)")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    input_path = Path(args.input)

    metadata_df = build_metadata(input_path)

    out_path = input_path.parent / f"phase1_{input_path.name}"
    metadata_df.to_csv(out_path, index=False)
    print(f"wrote {len(metadata_df)} row(s) to {out_path}")
