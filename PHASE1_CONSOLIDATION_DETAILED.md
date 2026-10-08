# Phase 1: Consolidation — Detailed Step-by-Step

**Goal:** Merge all per-repo entity files (~100 gzipped CSVs) into single `table4_entities.csv`

**Duration:** 1–2 hours (parallel on cluster: 15–30 min)

**Output:** 
- `results/tables/table4_entities.csv` (~1M rows, 300 MB uncompressed)
- `results/tables/table4_entities_metadata.json` (build log + validation stats)

---

## Step 1: Inventory & Pre-flight Check

### 1a. List all entity files and count rows per repo

**Local execution (or submit as quick job):**
```bash
#!/bin/bash
cd results/tables/table4_entities

echo "=== Entity File Inventory ===" > ../../analysis/table4_consolidation_log.txt
echo "Repo | Compressed Size | Estimated Rows | Language" >> ../../analysis/table4_consolidation_log.txt
echo "---|---|---|---" >> ../../analysis/table4_consolidation_log.txt

for repo_file in *.csv.gz; do
  repo_name=${repo_file%.csv.gz}
  size_mb=$(du -m "$repo_file" | cut -f1)
  
  # Sample first 1000 rows to estimate total
  rows=$(zcat "$repo_file" 2>/dev/null | wc -l)
  
  # Infer language from repo name (if follows pattern dotnet/*=C#, else Python)
  if [[ "$repo_name" == dotnet* ]] || [[ "$repo_name" == Azure* ]] || [[ "$repo_name" == Microsoft* ]]; then
    lang="C#"
  else
    lang="Python"
  fi
  
  echo "$repo_name | ${size_mb}M | $((rows-1)) | $lang" >> ../../analysis/table4_consolidation_log.txt
done

echo ""
echo "Total files: $(ls -1 *.csv.gz | wc -l)"
echo "Total size: $(du -sh . | cut -f1)"
```

**Expected output:**
```
Repo | Compressed Size | Estimated Rows | Language
airbytehq__airbyte | 7M | 145,023 | Python
dotnet__aspire | 5M | 89,456 | C#
...
Total files: 98
Total size: 246M
```

**TODO in log file:**
- Any repos with 0 rows → investigate (corrupted gzip?)
- Any repos with <100 rows → mark for QA later

---

### 1b. Validate column schema consistency

**Script:** `src/tables/validate_entity_schema.py`

```python
#!/usr/bin/env python3
"""
Validate that all entity CSVs have consistent columns.
Exit with error if any repo has different schema.
"""
import gzip
import csv
import sys
import os
from pathlib import Path

EXPECTED_COLS = [
    'repo', 'rel_month', 'sha', 'kind', 'entity_id', 'file', 'loc', 'cc', 
    'nesting', 'wmc', 'atfd', 'tcc', 'laa', 'fdp', 'noav', 'flags', 'episode',
    'created_sha', 'created_by', 'smell_sha', 'smell_by', 'smell_pr', 
    'removed_sha', 'removed_by', 'class_id', 'x_episode_start_rel_month'
]

entity_dir = Path("results/tables/table4_entities")
errors = []
warnings = []

for repo_file in sorted(entity_dir.glob("*.csv.gz")):
    repo_name = repo_file.stem.replace('.csv', '')
    
    try:
        with gzip.open(repo_file, 'rt', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)
            
            # Check column count
            if len(header) != len(EXPECTED_COLS):
                errors.append(
                    f"{repo_name}: Expected {len(EXPECTED_COLS)} cols, got {len(header)}"
                )
            
            # Check column names
            missing = set(EXPECTED_COLS) - set(header)
            extra = set(header) - set(EXPECTED_COLS)
            
            if missing:
                errors.append(f"{repo_name}: Missing cols: {missing}")
            if extra:
                warnings.append(f"{repo_name}: Extra cols: {extra}")
            
            # Sample first row for type check
            first_row = next(reader, None)
            if first_row:
                if len(first_row) != len(header):
                    errors.append(
                        f"{repo_name} row 2: Expected {len(header)} fields, got {len(first_row)}"
                    )
    
    except Exception as e:
        errors.append(f"{repo_name}: Failed to read: {e}")

if errors:
    print("❌ SCHEMA VALIDATION FAILED:")
    for err in errors:
        print(f"  {err}")
    sys.exit(1)

if warnings:
    print("⚠️  Warnings (non-fatal):")
    for warn in warnings:
        print(f"  {warn}")

print(f"✓ Schema valid: {len(list(entity_dir.glob('*.csv.gz')))} repos checked")
```

**Run:** `python src/tables/validate_entity_schema.py`

**Expected output:**
```
✓ Schema valid: 98 repos checked
```

**If errors:** Fix corrupted files before consolidation (usually re-run analyzer for that repo)

---

## Step 2: Consolidation

### 2a. Write consolidation script (cluster-ready)

**Script:** `src/tables/consolidate_entities.py`

```python
#!/usr/bin/env python3
"""
Consolidate all per-repo entity CSVs into single unified table.
Handles gzipped input, validates data integrity, writes uncompressed CSV.

Usage:
  python src/tables/consolidate_entities.py \
    --input-dir results/tables/table4_entities \
    --output results/tables/table4_entities.csv \
    --chunk-size 50000 \
    --log results/analysis/consolidation.log
"""
import argparse
import gzip
import csv
import sys
from pathlib import Path
from datetime import datetime
import json

def consolidate_entities(input_dir, output_path, chunk_size=50000, log_path=None):
    """
    Read all entity CSVs from input_dir, merge into single output.
    
    Args:
        input_dir: Path to table4_entities/ folder with *.csv.gz files
        output_path: Output CSV path
        chunk_size: Write rows in chunks for memory efficiency
        log_path: Optional log file for diagnostics
    
    Returns:
        dict with stats (total_rows, repos_processed, errors)
    """
    stats = {
        'start_time': datetime.now().isoformat(),
        'total_rows': 0,
        'repos_processed': 0,
        'repos_skipped': 0,
        'errors': []
    }
    
    input_dir = Path(input_dir)
    output_path = Path(output_path)
    
    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Collect all repo files
    repo_files = sorted(input_dir.glob("*.csv.gz"))
    print(f"Found {len(repo_files)} entity files to consolidate")
    
    if not repo_files:
        print("ERROR: No entity files found!")
        return stats
    
    # Write header from first repo
    first_repo = repo_files[0]
    header = None
    
    with gzip.open(first_repo, 'rt', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
    
    print(f"Schema: {len(header)} columns")
    
    # Open output file once, write all repos
    row_buffer = []
    with open(output_path, 'w', newline='', encoding='utf-8') as out_f:
        writer = csv.writer(out_f)
        writer.writerow(header)  # Write header
        
        for repo_file in repo_files:
            repo_name = repo_file.stem.replace('.csv', '')
            
            try:
                with gzip.open(repo_file, 'rt', encoding='utf-8') as in_f:
                    reader = csv.reader(in_f)
                    next(reader)  # Skip header
                    
                    repo_rows = 0
                    for row in reader:
                        row_buffer.append(row)
                        repo_rows += 1
                        
                        # Flush buffer when it reaches chunk_size
                        if len(row_buffer) >= chunk_size:
                            writer.writerows(row_buffer)
                            row_buffer = []
                    
                    stats['total_rows'] += repo_rows
                    stats['repos_processed'] += 1
                    print(f"  {repo_name}: {repo_rows:,} rows")
            
            except Exception as e:
                stats['errors'].append(f"{repo_name}: {str(e)}")
                stats['repos_skipped'] += 1
                print(f"  ERROR in {repo_name}: {e}")
        
        # Flush remaining buffer
        if row_buffer:
            writer.writerows(row_buffer)
    
    stats['end_time'] = datetime.now().isoformat()
    
    # Log results
    if log_path:
        with open(log_path, 'w') as lf:
            json.dump(stats, lf, indent=2)
    
    return stats

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', default='results/tables/table4_entities')
    parser.add_argument('--output', default='results/tables/table4_entities.csv')
    parser.add_argument('--chunk-size', type=int, default=50000)
    parser.add_argument('--log', default='results/analysis/consolidation.log')
    
    args = parser.parse_args()
    
    print(f"Consolidating entities from {args.input_dir}")
    print(f"Output: {args.output}")
    
    stats = consolidate_entities(
        args.input_dir,
        args.output,
        chunk_size=args.chunk_size,
        log_path=args.log
    )
    
    print(f"\n✓ Consolidation complete:")
    print(f"  Total rows: {stats['total_rows']:,}")
    print(f"  Repos processed: {stats['repos_processed']}")
    print(f"  Repos skipped: {stats['repos_skipped']}")
    
    if stats['errors']:
        print(f"\n⚠️  Errors encountered:")
        for err in stats['errors']:
            print(f"  {err}")
        sys.exit(1)
    
    sys.exit(0)
```

**Run locally first (for testing):**
```bash
time python src/tables/consolidate_entities.py \
  --input-dir results/tables/table4_entities \
  --output results/tables/table4_entities.csv \
  --log results/analysis/consolidation.log
```

**Expected local runtime:** 5–10 minutes (single-threaded on Windows)

**Expected output:**
```
Found 98 entity files to consolidate
Schema: 25 columns
  airbytehq__airbyte: 145,023 rows
  dotnet__aspire: 89,456 rows
  ...
✓ Consolidation complete:
  Total rows: 1,045,234
  Repos processed: 98
  Repos skipped: 0
```

---

### 2b. Cluster SLURM job script

**File:** `jobs/consolidate_table4.slurm`

```bash
#!/bin/bash
#SBATCH --job-name=table4_consolidate
#SBATCH --partition=cpu              # ← Change if needed
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00              # 1 hour max
#SBATCH --output=logs/consolidate_%j.log
#SBATCH --error=logs/consolidate_%j.err

# Load environment
module load python/3.11              # ← Adjust module name for your cluster
# OR: source /path/to/venv/bin/activate

# Set working directory
cd /path/to/Codebook_AIDev            # ← Update for cluster path

# Run consolidation
echo "Starting Table 4 consolidation on $(date)"
time python src/tables/consolidate_entities.py \
  --input-dir results/tables/table4_entities \
  --output results/tables/table4_entities.csv \
  --chunk-size 100000 \
  --log results/analysis/consolidation.log

echo "Consolidation finished on $(date)"
ls -lh results/tables/table4_entities.csv
```

**Submit to cluster:**
```bash
sbatch jobs/consolidate_table4.slurm
```

**Monitor:**
```bash
squeue --me
tail -f logs/consolidate_*.log
```

---

## Step 3: Validation

### 3a. Check output file

**Local (after job completes):**
```bash
ls -lh results/tables/table4_entities.csv
wc -l results/tables/table4_entities.csv
head -5 results/tables/table4_entities.csv | cut -d',' -f1-10
```

**Expected:**
```
-rw-r--r-- 1 kvrlv 314M table4_entities.csv
1045235 results/tables/table4_entities.csv
repo,rel_month,sha,kind,entity_id,file,loc,cc,nesting,wmc
```

### 3b. Quick data sanity checks

**Script:** `src/tables/validate_consolidated.py`

```python
#!/usr/bin/env python3
"""Quick validation of consolidated table4_entities.csv"""
import pandas as pd
import sys

print("Loading consolidated table...")
df = pd.read_csv('results/tables/table4_entities.csv', dtype={'rel_month': str})

print(f"✓ Loaded: {len(df):,} rows, {len(df.columns)} columns")
print(f"\nUnique repos: {df['repo'].nunique()}")
print(f"Unique entities: {df['entity_id'].nunique()}")
print(f"Unique months: {sorted(df['rel_month'].unique())}")
print(f"Kinds: {df['kind'].unique().tolist()}")

# Check for nulls
print(f"\nNull counts (top 10):")
nulls = df.isnull().sum().sort_values(ascending=False).head(10)
print(nulls)

# Check numeric columns
print(f"\nMetric ranges:")
for col in ['loc', 'cc', 'nesting', 'wmc']:
    print(f"  {col}: {df[col].min():.0f} - {df[col].max():.0f}")

print("\n✓ Validation complete")
```

**Run:**
```bash
python src/tables/validate_consolidated.py
```

---

## Step 4: Generate Coverage Index

### 4a. Build repo metadata

**Script:** `src/tables/build_coverage_index.py`

```python
#!/usr/bin/env python3
"""Generate table4_coverage.csv with repo stats + flags"""
import pandas as pd
from pathlib import Path

df = pd.read_csv('results/tables/table4_entities.csv', dtype={'rel_month': str})

# Group by repo
coverage = df.groupby('repo').agg(
    total_rows=('entity_id', 'count'),
    unique_entities=('entity_id', 'nunique'),
    unique_snapshots=('sha', 'nunique'),
    kinds=('kind', lambda x: ','.join(sorted(x.unique()))),
    smell_count=('flags', lambda x: (x.notna() & (x != '')).sum())
).reset_index()

# Calculate coverage %
coverage['snapshots_found'] = coverage.groupby('repo')['unique_snapshots'].transform('size')
coverage['coverage_pct'] = (coverage['snapshots_found'] / 24 * 100).round(1)
coverage['flag'] = coverage['coverage_pct'].apply(
    lambda x: 'LOW_COVERAGE' if x < 50 else 'OK'
)

# Infer language
coverage['language'] = coverage['repo'].apply(
    lambda x: 'C#' if any(p in x for p in ['dotnet', 'Azure', 'Microsoft']) else 'Python'
)

# Save
coverage.to_csv('results/tables/table4_coverage.csv', index=False)
print(coverage.to_string())
print(f"\nLow coverage repos (<50%):")
print(coverage[coverage['flag'] == 'LOW_COVERAGE'][['repo', 'coverage_pct', 'flag']])
```

**Run:**
```bash
python src/tables/build_coverage_index.py
```

---

## Summary Checklist

- [ ] Step 1a: Inventory all entity files
- [ ] Step 1b: Validate schema consistency
- [ ] Step 2a: Test consolidation locally
- [ ] Step 2b: Submit to cluster via SLURM
- [ ] Step 3a: Verify output file size + row count
- [ ] Step 3b: Run sanity checks
- [ ] Step 4a: Generate coverage index
- [ ] **Phase 1 complete** ✓

**Deliverables:**
1. `results/tables/table4_entities.csv` (1M rows, 300 MB)
2. `results/tables/table4_coverage.csv` (98 rows, repo metadata)
3. `results/analysis/consolidation.log` (build stats)
4. Validation report (nulls, ranges, etc.)

**Next:** Phase 2 (derive aggregates)

