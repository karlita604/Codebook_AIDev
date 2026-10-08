# Table 4 Correction: Per-Entity Metrics Build Plan

**Date:** 2026-10-07  
**Status:** Complete entity extraction (311k episodes); awaiting attribution columns and cross-metric aggregation

---

## 1. CRITICAL CORRECTION: What Table 4 Actually Is

**The "Table 4.B" plan in the artifact is WRONG.** It describes process metrics (Mann-Whitney U tests on PR data).

**The ACTUAL Table 4** per the original data_collection_plan is:
- **Per-entity metrics table** — one row per class/method/function per snapshot
- **Structural code quality** — raw OO metrics (LOC, cyclomatic complexity, ATFD, TCC, etc.)
- **Smell tracking** — design/implementation smells flagged per entity with episode numbers
- **Attribution** — commit-level tracking of who created/introduced/fixed each smell
- **Row count** — ~1M+ rows (every entity at every snapshot, all repos)

This is a **Track A output** (structural metrics from DPy/Designite), NOT a Track B output.

---

## 2. What We Have Now ✓

### 2.1 table4_episodes.csv (311,260 rows) ✓ COMPLETE

**Purpose:** Consolidated smell episode summary — one row per entity × smell episode

**Structure:**
```
repo | kind | entity_id | episode | start_rel_month | end_rel_month | end_reason | flags_at_start | last_rel_month_observed
```

**Coverage:** ~100 repos, all languages (Python + C#)

**What it tells us:**
- When each smell instance started and ended (in relative months: -12 to +12)
- Why it ended: "flag turned off", "entity deleted", "smell threshold changed", etc.
- Which smells were present when the episode began

**Gap:** No raw metrics (LOC, CC, etc.) — only flags and episode metadata

---

### 2.2 table4_entities/<owner__repo>.csv.gz (246M total) ✓ MOSTLY COMPLETE

**Purpose:** Per-repo entity metrics at each snapshot

**Columns Present:**
- **Dimensions:** repo, rel_month, sha, kind, entity_id, file, class_id
- **Raw metrics:** loc, cc, nesting, wmc, atfd, tcc, laa, fdp, noav
- **Smell tracking:** flags, episode, x_episode_start_rel_month
- **Attribution (PARTIALLY):** created_sha, created_by, smell_sha, smell_by, smell_pr, removed_sha, removed_by

**Coverage:**
- 246M total compressed
- Per-repo gzipped files (e.g., `airbytehq__airbyte.csv.gz`)
- Files exist for ~100 repos

**Why it's not "Table 4" yet:**
1. ❌ **Missing attribution columns** — several `*_by` fields have blanks (how/why?)
2. ❌ **Not aggregated** — raw per-repo CSVs, not consolidated into a single queryable table
3. ❌ **No per-repo summaries** — Table 3 (snapshot_summary.csv) exists, but Table 4 aggregates need building
4. ⚠️ **Coverage unknown** — need to verify which repos have complete data, which are partial

---

### 2.3 table3_snapshot_summary.csv (3,574 rows) ✓ REFERENCE

**Purpose:** Snapshot-level aggregates (one row per repo × rel_month)

**What it contains:**
- Per-snapshot smell counts, LOC total, metric distributions
- Repo coverage: which snapshots have usable analyzer output

**Use:** Reference for understanding snapshot completeness before aggregating Table 4

---

## 3. What Still Needs to Be Done

### 3.1 Attribution Columns — INVESTIGATE

Per the original plan, each entity row should have:

| Column | Definition | Current Status |
|--------|---|---|
| `created_sha` | Commit where entity first appeared | ⚠️ Present but some blanks |
| `created_by` | Author of creation commit | ⚠️ Blanks need investigation |
| `smell_sha` | Commit where smell first appeared | ⚠️ Present but incomplete |
| `smell_by` | Author of smell-introducing commit | ⚠️ Blanks need investigation |
| `smell_pr` | PR number that introduced smell | ⚠️ Blanks need investigation |
| `removed_sha` | Commit where smell was fixed | ⚠️ Likely incomplete |
| `removed_by` | Author of fix commit | ⚠️ Likely blanks |

**Action:** Audit sample repos to understand:
- Why certain `*_by` fields are blank (data not collected? not applicable?)
- Whether `removed_*` columns are populated at all
- If blanks are expected (e.g., removed_sha blank when `end_reason != "smell removed"`)

**Tool to check:**
```bash
zcat results/tables/table4_entities/airbytehq__airbyte.csv.gz \
  | cut -d',' -f15-21 | head -100 | sort | uniq -c
# Shows: created_sha, created_by, smell_sha, smell_by, smell_pr, removed_sha, removed_by
```

### 3.2 Table 4 Consolidated (NEW OUTPUT)

**What to build:** A unified, queryable Table 4 CSV combining all repos

**Structure:**
```
repo | rel_month | sha | kind | entity_id | file | loc | cc | nesting | wmc | atfd | tcc | laa | fdp | noav | flags | episode | created_sha | created_by | smell_sha | smell_by | smell_pr | removed_sha | removed_by | class_id | x_episode_start_rel_month
```

**Build process:**
```python
# Pseudocode
1. For each repo in table4_entities/:
   a. Read the gzipped CSV
   b. Validate column presence
   c. Check for missing attribution data
   d. Concatenate with running dataframe
2. Write unified CSV (or keep per-repo for size: ~1M rows × 25 cols ≈ 200-500MB uncompressed)
3. Index by (repo, rel_month, entity_id) for fast lookups
```

**Expected rows:** ~1M+ (one entity × one snapshot), comparable to table4_episodes size

### 3.3 Smell Episode Matching

**Purpose:** Cross-check table4_entities against table4_episodes

**Action:**
- For each episode in table4_episodes:
  - Find the entity in table4_entities at start_rel_month
  - Verify the flags match `flags_at_start`
  - Verify the episode number matches

**Why:** Ensures consistency between two derived outputs (episodes are a summary of entity rows)

### 3.4 Per-Repo Coverage Summary

**What to compute:**
```
repo | total_entities | snapshots_with_data | rel_months_covered | language
```

**Purpose:** Identify incomplete repos before analysis (repos with <50% coverage get flagged)

**Tool:** Scan table4_entities/ and aggregate

---

## 4. Build Plan (Step-by-Step)

### Phase 1: Audit (1-2 hours)

```bash
# 1a. Check attribution completeness
for repo in results/tables/table4_entities/*.csv.gz; do
  echo "=== $repo ==="
  zcat "$repo" | awk -F',' '{print NF}' | sort | uniq -c | head -1  # column count
  zcat "$repo" | awk -F',' '{print $16}' | grep -c "^$"  # blank created_by count
done

# 1b. Verify episode-to-entity cross-reference
python src/analysis/verify_table4_consistency.py
```

**Output:** Audit report identifying:
- Which `*_by` columns are consistently blank
- Whether pattern matches expected behavior
- Repos with anomalies

### Phase 2: Consolidate (30 min)

```python
# src/tables/consolidate_table4_entities.py
# Concatenate all per-repo entity files into single Table 4 CSV
# Validate columns, check for duplicates, write with proper indexing
```

**Output:** `results/tables/table4_entities.csv` (or `.gz` if size matters)

### Phase 3: Cross-Check (30 min)

```python
# src/analysis/check_table4_episodes_consistency.py
# Verify episode summaries against entity-level data
```

**Output:** Consistency report + any anomalies flagged

### Phase 4: Coverage Report (30 min)

```python
# src/analysis/table4_repo_coverage.py
# One row per repo: entity count, snapshot coverage, data quality flags
```

**Output:** `results/analysis/table4_coverage_by_repo.csv`

---

## 5. Original Plan Requirements (From data_collection_report.md)

| Requirement | Status | Notes |
|---|---|---|
| One row per class/method/function per snapshot | ✓ Done | table4_entities has this structure |
| Dimensions: repo, rel_month, sha, kind, entity_id, file | ✓ Done | Present in all entity files |
| Raw metrics: loc, cc, nesting, wmc, atfd, tcc, laa, fdp, noav | ✓ Done | All present |
| Smell flags + episode tracking | ✓ Done | `flags` and `episode` columns present |
| Commit attribution (created/removed by/via PR) | ⚠️ Partial | Present but need to verify completeness |
| Consolidated Table 4 CSV | ❌ Missing | Need to build from per-repo files |
| Per-repo summary (Table 4 → Table 3 style) | ❌ Missing | Need aggregation pipeline |
| Audit columns (class_id, lineno, tcc_sampled) | ✓ Done | Present as `class_id` and `x_episode_start_rel_month` |

---

## 6. Key Questions to Resolve Before Building

1. **Attribution blanks:** Are they "not applicable" (e.g., remove_sha blank when never removed) or "not collected" (data gap)?
   
2. **Consolidation strategy:** Single giant CSV (~1M rows × 25 cols) or keep per-repo + build index?

3. **Coverage threshold:** What's the minimum snapshot coverage to include a repo in analysis? (default: 50%?)

4. **Per-snapshot aggregates:** Should Table 4 have pre-computed summaries like Table 3, or just raw entity data?

---

## 7. Timeline

- **Audit Phase:** Today (2-3 hours)
- **Consolidation:** Tomorrow (1 hour)
- **Cross-checks:** Tomorrow (1 hour)
- **Ready for analysis:** By end of week

---

## 8. Files to Check/Create

| File | Action | Priority |
|---|---|---|
| `results/tables/table4_entities/*.csv.gz` | Read + audit | HIGH |
| `results/tables/table4_episodes.csv` | Reference | HIGH |
| `src/analysis/verify_table4_consistency.py` | Create | HIGH |
| `src/tables/consolidate_table4_entities.py` | Create | HIGH |
| `results/analysis/table4_coverage_by_repo.csv` | Create | MEDIUM |
| `results/tables/table4_entities.csv` (consolidated) | Create | HIGH |

