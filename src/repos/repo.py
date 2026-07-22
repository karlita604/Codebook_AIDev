"""
Given a csv of PR ids (as produced by PRfilter.py), find the unique repos
those PRs come from and write a csv with basic repo information.

Since the AIDev dataset is read live from Hugging Face and can change between
runs, this script also logs the dataset version (commit sha + last-modified)
it used to logs/phase0/<date>_<inputcsvname>.log.

Default input: results/phase0/07-21-500-pycsharp-1398.csv

Output: repos_[inputcsvname].csv written next to the input csv, one row per
unique repo, with columns: id, full_name, language, stars, forks, url,
license.

Running this file:
- Install deps first: pip install -r requirements.txt
  (pandas, pyarrow, huggingface_hub)
- Needs network access - reads directly from the hao-li/AIDev dataset
  on Hugging Face.
    python repo.py
    python repo.py --input results/phase0/07-20-default-7312.csv
"""

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results" / "phase0"
LOGS_DIR = ROOT / "logs" / "phase0"
DEFAULT_INPUT = RESULTS_DIR / "07-21-500-pycsharp-1398.csv"

DATASET_REPO = "hao-li/AIDev"


def _log_dataset_version(input_csv: Path) -> Path:
    info = HfApi().dataset_info(DATASET_REPO)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"{date.today().isoformat()}_{input_csv.stem}.log"
    with open(log_path, "w") as f:
        f.write(f"dataset: {DATASET_REPO}\n")
        f.write(f"sha: {info.sha}\n")
        f.write(f"last_modified: {info.lastModified}\n")
        f.write(f"logged_at: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"input_csv: {input_csv}\n")
    return log_path


def extract_repos(input_csv: Path) -> pd.DataFrame:
    pr_ids = pd.read_csv(input_csv)["id"]

    all_pr_df = pd.read_parquet(
        f"hf://datasets/{DATASET_REPO}/all_pull_request.parquet"
    )
    all_repo_df = pd.read_parquet(
        f"hf://datasets/{DATASET_REPO}/all_repository.parquet"
    )

    # repo_id (PR table) and repository.id are stored with mismatched dtypes
    # (int64 vs float64) in the source parquet files; normalize before joining.
    all_pr_df["repo_id"] = pd.to_numeric(all_pr_df["repo_id"], errors="coerce")
    all_repo_df["id"] = pd.to_numeric(all_repo_df["id"], errors="coerce")

    prs = all_pr_df[all_pr_df["id"].isin(pr_ids)]
    repo_ids = prs["repo_id"].dropna().unique()

    repos = all_repo_df[all_repo_df["id"].isin(repo_ids)]
    repos = repos.drop_duplicates(subset="id")
    columns = [
        "id", "full_name", "language", "stars", "forks", "url", "license"
    ]
    return repos[columns].reset_index(drop=True)


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Extract the unique repos referenced by a PR-id csv."
    )
    parser.add_argument(
        "--input", type=Path, default=DEFAULT_INPUT,
        help="csv of PR ids (as produced by PRfilter.py)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    input_csv = args.input

    log_path = _log_dataset_version(input_csv)
    print(f"logged dataset version to {log_path}")

    repos_df = extract_repos(input_csv)

    out_path = input_csv.parent / f"repos_{input_csv.stem}_{len(repos_df)}.csv"
    repos_df.to_csv(out_path, index=False)
    print(f"{len(repos_df)} unique repo(s)")
    print(f"wrote {out_path}")
