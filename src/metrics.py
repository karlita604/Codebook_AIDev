"""
Calculate and return various metrics for the codebase.
Given a csv where each row is a PR, calculate metrics for each PR and return a dataframe with the metrics.
Dataframe is returned as a csv file metrics_[inputfilename]_[date].csv in the same directory as the input csv.
"""


# ------------------------------------------------------------------------------- # 
# rejected
# ------------------------------------------------------------------------------- # 
# Description: 
# Boolean metric indicating whether the PR was rejected or not. 
# Closed but not merged PRs are considered rejected. 
#
# Columns used: closed_at, merged_at
# ------------------------------------------------------------------------------- # 





# ------------------------------------------------------------------------------- # 
# num_diffhunks
# ------------------------------------------------------------------------------- # 
# Description: 
# Number of diff hunks in the PR.
# total number of @@ blocks across ...
#
# Columns used: 
# ------------------------------------------------------------------------------- # 
 
 

 
# ------------------------------------------------------------------------------- # 
# ave_diffhunk_size
# ------------------------------------------------------------------------------- # 
# Description: 
# Columns used: 
# ------------------------------------------------------------------------------- # 
 






# ------------------------------------------------------------------------------- # 
#  ngrams
# ------------------------------------------------------------------------------- # 
# Description: 
# Columns used: 
# ------------------------------------------------------------------------------- # 


# ------------------------------------------------------------------------------- # 
#  keyword_density
# ------------------------------------------------------------------------------- # 
# Description: 
# Columns used: 
# ------------------------------------------------------------------------------- # 



# ------------------------------------------------------------------------------- # 
#  duplicate_code
# ------------------------------------------------------------------------------- # 
# Description: 
# Columns used: 
# ------------------------------------------------------------------------------- # 
 
# ------------------------------------------------------------------------------- # 
# unused_vars
# ------------------------------------------------------------------------------- # 
# Description: 
# Columns used: 
# ------------------------------------------------------------------------------- # 
 unused_vars
Design and Architecture
 large_class
 long_method
 god_object
Social and Collaboration
 interaction_count
 num_participants
 conflict
Code Size and Complexity
 cyclomatic_complexity
 loc
 halstead_volume
 nesting_depth
Process
 prev_pr
 linked_issues
 codechurn
 author_experience
