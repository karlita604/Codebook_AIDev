"""
Based on user input flags, we will filter PRs.

We begin by being able to access the AIDev set:

Based on the different flags that act like filters, given in the user prompt, we will filter the PRs and return a dataframe with the filtered PRs.

PRfilter (star_minimum = 100, language = "Python", agents = True)

"""

import pandas as pd
all_pr_df = pd.read_parquet("hf://datasets/hao-li/AIDev/all_pull_request.parquet")
all_repo_df = pd.read_parquet("hf://datasets/hao-li/AIDev/all_repository.parquet")
all_user_df = pd.read_parquet("hf://datasets/hao-li/AIDev/all_user.parquet")
