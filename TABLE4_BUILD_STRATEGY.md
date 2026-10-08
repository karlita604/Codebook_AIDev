# Table 4 Build Strategy: Consolidation → Visualization → Analysis

**Focus:** Get data consolidated and visualized quickly. Attribution audits deferred.

---

## Priority 1: Consolidation Strategy

### Question: Single Giant CSV vs. Alternative Formats?

**Decision Framework:**
- Current state: 246M gzipped per-repo entity files (~100 repos)
- Target analysis: Fast queries by (repo, rel_month, entity_id, smell_type)
- End goal: Visualizations + statistical tests on entity metrics across time

---

## Option Analysis: Data Formats

### Option A: Single Giant CSV (~1M rows × 25 cols)

**Pros:**
- ✓ Maximum compatibility (every tool reads CSV)
- ✓ Human-readable for spot-checking
- ✓ Simple append logic during consolidation
- ✓ Git-diffable if stored in repo (metadata/sample rows)
- ✓ No special libraries needed for downstream analysis

**Cons:**
- ✗ Uncompressed size: ~250–500 MB (large but not prohibitive)
- ✗ Query performance: Linear scan for "all entities in repo X with smell Y"
- ✗ Memory overhead: Loading entire table into RAM for large joins
- ✗ Slow on filtering (e.g., "all god_class smells across all repos at month 0")

**Best for:** Initial exploration, simple aggregations, publication

---

### Option B: Parquet Format (Apache Parquet)

**Pros:**
- ✓ Compressed: 30–50% of CSV size (~100–150 MB)
- ✓ Columnar storage: Super fast filtering on single columns (e.g., "all smell='god_class' rows")
- ✓ Native support for data types (int, float, string, timestamp) — no type inference on load
- ✓ Fast random access by partition (load only month 0, or only repo X)
- ✓ Built-in metadata (schema, statistics per column)
- ✓ Libraries: Pandas, Polars, DuckDB, R all have excellent Parquet support
- ✓ Future-proof: Industry standard for data lakes (AWS, GCP, Snowflake all prefer Parquet)

**Cons:**
- ✗ Not human-readable (binary format)
- ✗ Requires Python/R libraries (not plain CSV/Excel)
- ✗ Larger ecosystem (more dependencies)
- ✗ Marginal gain for this size table (benefits scale better at 10GB+)

**Best for:** Analysis pipeline, filtering-heavy queries, dashboards

---

### Option C: Partitioned Parquet (Per-Repo Sub-files)

**Structure:**
```
table4_entities_parquet/
  ├── airbytehq__airbyte.parquet
  ├── dotnet__aspire.parquet
  └── ... (100 files, ~2–5 MB each)
```

**Pros:**
- ✓ Fast: Load only one repo's data at a time (~2–5 MB)
- ✓ Compressed: Same 30–50% reduction as full Parquet
- ✓ Parallelizable: Read 10 repos in parallel
- ✓ Incremental updates: Re-run analyzer for one repo, update only that file
- ✓ Partial analysis: "Analyze Python repos" = load only Python repo files

**Cons:**
- ✗ Complexity: Need to manage 100 separate files, index/catalog them
- ✗ Cross-repo queries: Require union/concat of multiple files (slower than single table)
- ✗ Overkill if most queries are repo-agnostic (e.g., "all god_class instances across all repos")

**Best for:** Very large datasets (>1B rows), streaming ingestion, cloud data lakes

---

### Option D: SQLite Database

**Structure:**
```
table4_entities.db
  └── entities (table with 1M rows, 25 cols + automatic indexes)
```

**Pros:**
- ✓ True random-access queries (SQL: `SELECT * WHERE repo='X' AND smell LIKE 'god%'`)
- ✓ Compact: 100–150 MB with indexes
- ✓ Zero dependencies: Single file, no import libraries needed
- ✓ Fast aggregations: SQL GROUP BY is blazingly fast
- ✓ Excellent for dashboard backends
- ✓ Can attach multiple .db files (modular design)

**Cons:**
- ✗ Not human-editable
- ✗ Requires SQL knowledge downstream
- ✗ Overkill if you'll mostly use Pandas anyway
- ✗ Publishing/version control: Binary blob, hard to diff

**Best for:** Dashboards, repeated ad-hoc queries, production systems

---

### Option E: Zip of Per-Repo CSVs (Keep Current + Index)

**Structure:**
```
table4_entities.zip
  ├── airbytehq__airbyte.csv
  ├── dotnet__aspire.csv
  └── ...
+ table4_entities_index.csv (one row per repo with metadata)
```

**Pros:**
- ✓ Preserves current structure (already gzipped per-repo)
- ✓ Easy to add new repo: Just add new CSV
- ✓ Human-readable inside the zip
- ✓ Minimal consolidation effort
- ✓ File size: ~250 MB (slightly larger than single CSV due to repetition)

**Cons:**
- ✗ Query friction: Must unzip + load all repos to filter across repos
- ✗ No performance gain over single CSV
- ✗ Analysis tools need extra step to iterate over multiple files

**Best for:** Archival, distribution, when repo-level partitioning is intentional

---

## RECOMMENDATION FOR YOUR PIPELINE

**Primary format: Single CSV (with Parquet as secondary)**

**Why:**
1. You want visualizations NOW — CSV loads instantly in any tool
2. 1M rows × 25 cols (~300 MB) is not "giant" by 2026 standards
3. Downstream: Pandas/Polars handle CSV ↔ Parquet conversion trivially
4. Visualization tools (Plotly, Matplotlib) work directly with CSV via Pandas

**Build order:**
```
Phase 1: Consolidate → table4_entities.csv
Phase 2: Convert to Parquet → table4_entities.parquet (optional, for future scale)
Phase 3: Build index → table4_coverage.csv (repo metadata + coverage %)
Phase 4: Visualizations from CSV
```

**Index file (table4_coverage.csv):**
```
repo | language | total_rows | snapshots_found | coverage_pct | flags
airbytehq/airbyte | Python | 145,000 | 96 | 100% | OK
dotnet/aspire | C# | 89,000 | 85 | 88% | LOW_COVERAGE
...
```

---

## Priority 2: Coverage Flagging (Not Filtering)

### Decision: Include ALL repos, flag low-coverage ones

**Coverage threshold: 50% (—flag those below)**

**Rationale:**
- All repos should appear in Table 4 (analysis can handle sparse data)
- Repos with <50% coverage get a flag: `coverage_pct < 50` in index
- Downstream: "If analysis removes flagged repos, document which ones and why"

**Implementation:**
```python
coverage_pct = snapshots_found / 24  # 24 = expected snapshots per repo (-12 to +12)
flag = 'LOW_COVERAGE' if coverage_pct < 0.5 else 'OK'
```

**TODO:** Later data collection to fill gaps in flagged repos (separate ticket)

---

## Priority 3: Aggregates (Raw + Summary)

### Question: What are "pre-computed summaries"?

I meant summary statistics like Table 3 has:

**Table 3 (snapshot_summary.csv):** One row per repo × month
```
repo | rel_month | design_smell_count | impl_smell_count | avg_loc_per_entity | median_cc | ...
```

**Table 4 (entity-level):** One row per entity × month
```
repo | rel_month | entity_id | loc | cc | nesting | flags | ...
```

### Decision: Include BOTH

**Table 4 structure:**
- **Raw entity rows** (every entity at every snapshot) — for detailed analysis
- **Pre-computed aggregates** (one row per repo × month) — for trends/visualizations

**Why both:**
- Raw: Drill-down ("Show me which methods had god_class smell in repo X month 0")
- Agg: Trend ("Did smell count increase post-intervention?")
- Agg rows compute fast from raw (no extra computation, just GROUP BY)

**Build order:**
```python
1. Consolidate raw entities → table4_entities.csv (~1M rows)
2. Derive aggregates → table4_snapshot_summary.csv (~2k rows, like Table 3)
3. Use agg for viz, raw for drill-down
```

---

## Priority 4: Visualization & Report

### Goal: MD Report with Graph Gallery

**Output: results/analysis/table4_visualization_report.md**

**Structure:**
```markdown
# Table 4: Per-Entity Metrics — Visualization Report

## 1. Smell Prevalence Trends
![Fig 1a: Design smell count over time]()
- What: Line chart of design_smell_count per month, colored by repo
- Why: Shows whether smell density increased/decreased post-intervention
- Data source: table4_snapshot_summary.csv (aggregated)

## 2. Metric Distributions (Before/After)
![Fig 2a: LOC per entity, pre vs. post]()
- What: Violin plot of LOC, split pre/post intervention
- Why: Are entities getting larger/smaller?
- Data source: table4_entities.csv (raw)

## 3. Smell Episode Lifespans
![Fig 3a: Episode duration by smell type]()
- What: Histogram of how long each smell persists
- Why: Do some smells go away faster than others?
- Data source: table4_episodes.csv

## 4. Language Differences (Python vs. C#)
![Fig 4a: Smell density by language]()
- What: Boxplot of smell_count_per_kloc, split by language
- Why: Do structural health trends differ?
- Data source: table4_snapshot_summary.csv + repo metadata

## 5. Repo Heterogeneity
![Fig 5a: Coverage heatmap]()
- What: Heatmap of data availability (repo × month, green=data, gray=missing)
- Why: Visual summary of coverage gaps
- Data source: table4_coverage.csv
```

**Graphs to build (in order):**
1. ✓ Smell prevalence trends (design, impl, arch)
2. ✓ Metric distributions pre/post (LOC, CC, nesting)
3. ✓ Episode lifespans by smell type
4. ✓ Language differences
5. ✓ Coverage heatmap
6. → Smell co-occurrence (do certain smells cluster?)
7. → Per-repo heterogeneity (which repos improved vs. worsened?)

---

## Build Timeline

| Phase | Task | Duration | Output |
|-------|------|----------|--------|
| 1 | Consolidate → single CSV | 1h | `table4_entities.csv` |
| 2 | Derive aggregates | 30m | `table4_snapshot_summary.csv` |
| 3 | Cross-check episodes vs. entities | 30m | Validation report |
| 4 | Build coverage index | 30m | `table4_coverage.csv` |
| 5 | Visualization pipeline | 2–3h | MD report + PNG/SVG graphs |
| **Total** | **→ Analysis-ready** | **5–6h** | **Full table4 suite** |

---

## Files to Create/Update

```
results/tables/
├── table4_entities.csv (NEW: consolidated, 1M rows)
├── table4_entities.parquet (FUTURE: optional)
├── table4_snapshot_summary.csv (UPDATE: derived agg)
└── table4_coverage.csv (NEW: repo metadata + flags)

results/analysis/
├── table4_visualization_report.md (NEW)
├── figures/table4/
│   ├── 01_smell_prevalence_trends.png
│   ├── 02_metric_distributions_pre_post.png
│   ├── 03_episode_lifespans.png
│   ├── 04_language_differences.png
│   ├── 05_coverage_heatmap.png
│   └── ...
└── table4_consistency_report.txt (NEW: cross-check results)
```

---

## Next Step

**Approval needed on:**
1. ✅ Consolidation format: **Single CSV** (with Parquet as future option)
2. ✅ Coverage strategy: **Include all repos, flag <50%**
3. ✅ Aggregates: **Both raw + summary rows**
4. ✅ Visualization: **MD report with graph gallery**

**If approved, I'll start Phase 1 (consolidation) immediately.**

