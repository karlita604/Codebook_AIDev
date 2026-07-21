"""
Based on user input flags, we will filter PRs.

Possible filters include:
- rejected = default True, only rejected PRs will be returned
- star_minimum = default 100, only PRs with at least this many stars will be returned
- language = default None (no filter applied), if a language is specified, only PRs in those language will be returned (example: language="Python, Csharp, C")
- agents = default None (no filter applied), if a list of agents is specified, only PRs with those agents will be returned (example: agents=["Claude_Code", "Copilot", "Cursor", "Devin", "OpenAI_Codex"])
- user_minimum = default None (no filter applied), only PRs with at least this many user followers will be returned
- forks_minimum = default None (no filter applied), only PRs with at least this many forks will be returned
- age_minimum = default None (no filter applied), only PRs with at least this many days since creation will be returned
- age_maximum = default None (no filter applied), only PRs with at most this many days since creation will be returned

Dryrun:

PRfilter.py ==> at least 100 stars, rejected PRs
PRfilter.py(star_minimum=500,language="Python, Csharp,C")

Example (CLI): PRs with 500+ stars in Python, C, or C++
    python PRfilter.py --star-minimum 500 --language "Python, C, C++"

Running this file:
- Install deps first: pip install -r requirements.txt (pandas, pyarrow, huggingface_hub)
- Needs network access - reads directly from the hao-li/AIDev dataset on Hugging Face
  via hf:// paths on every run, nothing is cached locally by this script.
- Running as a script prints the matching PR ids and also writes them to a CSV in
  results/phase0/ (created if missing), named <MM>-<DD>-<filters>-<count>.csv where
  <filters> is "default" if no filter differs from the function defaults, otherwise
  a short tag built from whichever filters were overridden
  (e.g. 07-20-500-pyccpp-42.csv for star_minimum=500, language="Python, C, C++";
  07-20-default-7312.csv for no overrides).
- Can also be imported: `from PRfilter import filter_prs` (no CSV/printing in that case).
"""

import argparse
import os
from datetime import date
from pathlib import Path

import pandas as pd
from huggingface_hub import login

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results" / "phase0"

# ------------------------------------------------------------------------------- #
# Hugging Face authentication
# ------------------------------------------------------------------------------- #
# TODO: this dataset currently loads without a token (appears public), so auth
# is not wired up yet. When we do need it: set the HF_TOKEN environment variable
# (do NOT hardcode a token here - this file is tracked by git) and
# _authenticate() will pick it up automatically.
HF_TOKEN = None


def _authenticate():
    token = HF_TOKEN or os.environ.get("HF_TOKEN")
    if token:
        login(token=token)


_authenticate()

all_pr_df = pd.read_parquet("hf://datasets/hao-li/AIDev/all_pull_request.parquet")
# endpoint: GET /repos/{owner}/{repo}/pulls/{pull_number}

# agent: if None then return all agents, otherwise return only those agents specified in the list
# id [id]: after all the filters are applied, return PR ids that match the filters

all_repo_df = pd.read_parquet("hf://datasets/hao-li/AIDev/all_repository.parquet")
# endpoint: GET /repos/{owner}/{repo}/

# stars [stars]
# language [language]
# repo_url [url]
# forks [forks]

all_user_df = pd.read_parquet("hf://datasets/hao-li/AIDev/all_user.parquet")
# endpoint: GET /users/{username}

# followers [followers]

# repo_id (PR table) and user.id / repository.id are stored with mismatched
# dtypes (int64 vs float64) in the source parquet files; normalize before
# joining so the merges below don't silently drop rows.
all_pr_df["repo_id"] = pd.to_numeric(all_pr_df["repo_id"], errors="coerce")
all_repo_df["id"] = pd.to_numeric(all_repo_df["id"], errors="coerce")
all_pr_df["user_id"] = pd.to_numeric(all_pr_df["user_id"], errors="coerce")
all_user_df["id"] = pd.to_numeric(all_user_df["id"], errors="coerce")


# ------------------------------------------ #
# return a filtered list of the PR ids which match the filters.

def filter_prs(
    rejected=True,
    star_minimum=100,
    language=None,
    agents=None,
    user_minimum=None,
    forks_minimum=None,
    age_minimum=None,
    age_maximum=None,
):
    df = all_pr_df.merge(
        all_repo_df, left_on="repo_id", right_on="id", how="left", suffixes=("", "_repo")
    )
    df = df.merge(
        all_user_df, left_on="user_id", right_on="id", how="left", suffixes=("", "_user")
    )

    if rejected:
        df = df[(df["state"] == "closed") & (df["merged_at"].isna())]

    df = df[df["stars"] >= star_minimum]

    if language is not None:
        langs = [lang.strip() for lang in language.split(",")]
        df = df[df["language"].isin(langs)]

    if agents is not None:
        df = df[df["agent"].isin(agents)]

    if user_minimum is not None:
        df = df[df["followers"] >= user_minimum]

    if forks_minimum is not None:
        df = df[df["forks"] >= forks_minimum]

    if age_minimum is not None or age_maximum is not None:
        created = pd.to_datetime(df["created_at"], utc=True, errors="coerce")
        age_days = (pd.Timestamp.now(tz="UTC") - created).dt.days
        if age_minimum is not None:
            df = df[age_days >= age_minimum]
        if age_maximum is not None:
            df = df[age_days <= age_maximum]

    return df["id"].tolist()


def _parse_args():
    parser = argparse.ArgumentParser(description="Filter AIDev PRs and print matching PR ids.")
    parser.add_argument("--no-rejected", dest="rejected", action="store_false",
                         help="include non-rejected PRs too (default: rejected only)")
    parser.add_argument("--star-minimum", type=int, default=100)
    parser.add_argument("--language", type=str, default=None,
                         help='comma-separated GitHub Linguist names, e.g. "Python, C, C++"')
    parser.add_argument("--agents", type=str, default=None,
                         help='comma-separated, e.g. "Claude_Code, OpenAI_Codex"')
    parser.add_argument("--user-minimum", type=int, default=None)
    parser.add_argument("--forks-minimum", type=int, default=None)
    parser.add_argument("--age-minimum", type=int, default=None)
    parser.add_argument("--age-maximum", type=int, default=None)
    parser.set_defaults(rejected=True)
    return parser.parse_args()


def _lang_tag(language):
    special = {"c++": "cpp", "c#": "csharp", "python": "py"}
    key = language.strip().lower()
    return special.get(key, "".join(ch for ch in key if ch.isalnum()))


def _agent_tag(agent):
    return "".join(ch for ch in agent.strip().lower() if ch.isalnum())


def _build_descriptor(args):
    """Short filename tag for whichever filters differ from filter_prs()'s defaults."""
    tokens = []
    if args.star_minimum != 100:
        tokens.append(str(args.star_minimum))
    if args.language:
        tokens.append("".join(_lang_tag(l) for l in args.language.split(",")))
    if args.agents:
        tokens.append("".join(_agent_tag(a) for a in args.agents.split(",")))
    if args.user_minimum is not None:
        tokens.append(f"u{args.user_minimum}")
    if args.forks_minimum is not None:
        tokens.append(f"f{args.forks_minimum}")
    if args.age_minimum is not None:
        tokens.append(f"amin{args.age_minimum}")
    if args.age_maximum is not None:
        tokens.append(f"amax{args.age_maximum}")
    if not args.rejected:
        tokens.append("allstates")
    return "-".join(tokens) if tokens else "default"


if __name__ == "__main__":
    args = _parse_args()
    agents_list = [a.strip() for a in args.agents.split(",")] if args.agents else None

    ids = filter_prs(
        rejected=args.rejected,
        star_minimum=args.star_minimum,
        language=args.language,
        agents=agents_list,
        user_minimum=args.user_minimum,
        forks_minimum=args.forks_minimum,
        age_minimum=args.age_minimum,
        age_maximum=args.age_maximum,
    )
    print(f"{len(ids)} matching PR(s)")
    for pr_id in ids:
        print(pr_id)

    today = date.today()
    descriptor = _build_descriptor(args)
    filename = f"{today.month:02d}-{today.day:02d}-{descriptor}-{len(ids)}.csv"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / filename
    pd.DataFrame({"id": ids}).to_csv(out_path, index=False)
    print(f"wrote {out_path}")
