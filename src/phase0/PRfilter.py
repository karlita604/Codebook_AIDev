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
- english_title = default True, only PRs whose title is in English will be returned. Titles may
  contain emoji; a title is rejected only if a large share of its actual letters are non-Latin
  script (e.g. Chinese, Japanese, Korean, Cyrillic, Arabic, Greek), so English titles are never
  penalized for emoji or accented characters.
- require_body = default True, only PRs with a non-empty body will be returned (excludes PRs
  whose body is null or whitespace-only).
- require_live_url = default True, only PRs whose GitHub html_url does not 404 will be
  returned. Checked live via HTTP HEAD requests (concurrently, since the AIDev dataset
  includes PRs from repos that have since been deleted/made private/renamed). Only a
  confirmed 404 excludes a PR - timeouts, rate limiting, and other non-404 responses are
  treated as "keep", since they aren't proof the PR is actually gone. Applied last (after
  every other filter), since it's by far the most expensive check.

Dryrun:

PRfilter.py ==> at least 100 stars, rejected PRs
PRfilter.py(star_minimum=500,language="Python, Csharp,C")

Example (CLI): PRs with 500+ stars in Python, C, or C++
    python PRfilter.py --star-minimum 500 --language "Python, C, C++"

Running this file:
- Install deps first: pip install -r requirements.txt (pandas, pyarrow, huggingface_hub, requests)
- Needs network access - reads directly from the hao-li/AIDev dataset on Hugging Face
  via hf:// paths on every run, nothing is cached locally by this script. Also makes a
  live HTTP request per surviving PR to check require_live_url (see above), so a run
  can take a while once other filters are narrow enough to reach that step.
- Running as a script prints the matching PR ids and also writes them to a CSV in
  results/phase0/ (created if missing), named <MM>-<DD>-<filters>-<count>.csv where
  <filters> is "default" if no filter differs from the function defaults, otherwise
  a short tag built from whichever filters were overridden
  (e.g. 07-20-500-pyccpp-42.csv for star_minimum=500, language="Python, C, C++";
  07-20-default-7312.csv for no overrides).
- Can also be imported: `from PRfilter import filter_prs` (no CSV/printing in that case).
"""

import argparse
import concurrent.futures
import os
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd
import requests
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
# english_title: a title is treated as English unless a large share of its
# letters belong to a non-Latin script. Statistical language-id models (e.g.
# langid) are unreliable on short, jargon-heavy PR titles - spot checks
# misclassified ~20% of genuinely English titles as French/German/etc. A
# script-based check has no such false positives and, checked against the
# full AIDev title set, flags only ~0.9% of titles - all genuinely
# non-English (Russian, Japanese, Korean, Chinese, Arabic, Greek, ...).
# Emoji and accented Latin letters (e.g. e with acute) are not letters in a
# non-Latin script, so they never count against a title.
NON_ENGLISH_LETTER_RATIO_THRESHOLD = 0.3


def _is_english_title(title, threshold=NON_ENGLISH_LETTER_RATIO_THRESHOLD):
    if not isinstance(title, str):
        return True
    letters = [ch for ch in title if ch.isalpha()]
    if not letters:
        return True
    non_latin = sum(1 for ch in letters if "LATIN" not in unicodedata.name(ch, ""))
    return (non_latin / len(letters)) <= threshold


# ------------------------------------------ #
# require_live_url: drop PRs whose html_url is a confirmed 404 (e.g. the repo
# was later deleted, made private, or renamed). Checked concurrently since
# this is a live network call per PR, not a column lookup.
URL_CHECK_WORKERS = 16
URL_CHECK_TIMEOUT = 10  # seconds
URL_CHECK_HEADERS = {"User-Agent": "Codebook-AIDev-PRfilter/1.0"}


def _is_live_url(url, timeout=URL_CHECK_TIMEOUT):
    try:
        resp = requests.head(
            url, headers=URL_CHECK_HEADERS, timeout=timeout, allow_redirects=True
        )
        if resp.status_code == 405:  # some servers don't support HEAD
            resp = requests.get(
                url, headers=URL_CHECK_HEADERS, timeout=timeout,
                allow_redirects=True, stream=True,
            )
        return resp.status_code != 404
    except requests.RequestException:
        # Not proof the PR is gone - keep it rather than risk a false drop.
        return True


def _filter_live_urls(df, workers=URL_CHECK_WORKERS):
    urls = df["html_url"].tolist()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        alive = list(pool.map(_is_live_url, urls))
    return df[alive]


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
    english_title=True,
    require_body=True,
    require_live_url=True,
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

    if english_title:
        df = df[df["title"].apply(_is_english_title)]

    if require_body:
        df = df[df["body"].apply(lambda b: isinstance(b, str) and b.strip() != "")]

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

    if require_live_url:
        df = _filter_live_urls(df)

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
    parser.add_argument("--no-english-title", dest="english_title", action="store_false",
                         help="include non-English titles too (default: English titles only)")
    parser.add_argument("--no-require-body", dest="require_body", action="store_false",
                         help="include empty-body PRs too (default: non-empty body only)")
    parser.add_argument("--no-require-live-url", dest="require_live_url", action="store_false",
                         help="include PRs whose html_url 404s too (default: live urls only)")
    parser.set_defaults(rejected=True, english_title=True, require_body=True, require_live_url=True)
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
    if not args.english_title:
        tokens.append("alllangs")
    if not args.require_body:
        tokens.append("allbodies")
    if not args.require_live_url:
        tokens.append("deadlinks")
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
        english_title=args.english_title,
        require_body=args.require_body,
        require_live_url=args.require_live_url,
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
