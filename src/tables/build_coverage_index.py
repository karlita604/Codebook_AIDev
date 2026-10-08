#!/usr/bin/env python3
"""Generate table4_coverage.csv with repo stats + flags"""
import pandas as pd
from pathlib import Path
import sys

csv_path = Path('results/tables/table4_entities.csv')

if not csv_path.exists():
    print(f"ERROR: {csv_path} not found")
    print(f"Run consolidate_entities.py first")
    sys.exit(1)

print("Loading consolidated table...")
df = pd.read_csv(csv_path, dtype={'rel_month': str}, low_memory=False)

print("Building coverage index...")

# Group by repo
coverage = df.groupby('repo').agg(
    total_rows=('entity_id', 'count'),
    unique_entities=('entity_id', 'nunique'),
    unique_snapshots=('sha', 'nunique'),
    kinds=('kind', lambda x: ','.join(sorted(x.unique()))),
    smell_count=('flags', lambda x: (x.notna() & (x != '')).sum())
).reset_index()

# Calculate coverage % (expected: 24 snapshots per repo, -12 to +12 months)
coverage['expected_snapshots'] = 24
coverage['coverage_pct'] = (coverage['unique_snapshots'] / coverage['expected_snapshots'] * 100).round(1)
coverage['flag'] = coverage['coverage_pct'].apply(
    lambda x: 'LOW_COVERAGE' if x < 50 else 'OK'
)

# Infer language
coverage['language'] = coverage['repo'].apply(
    lambda x: 'C#' if any(p in x for p in ['dotnet', 'Azure', 'Microsoft']) else 'Python'
)

# Reorder columns
coverage = coverage[['repo', 'language', 'total_rows', 'unique_entities', 'unique_snapshots',
                     'expected_snapshots', 'coverage_pct', 'kinds', 'smell_count', 'flag']]

# Save
output_path = Path('results/tables/table4_coverage.csv')
output_path.parent.mkdir(parents=True, exist_ok=True)
coverage.to_csv(output_path, index=False)

print(f"\n[OK] Coverage index written to {output_path}")
print(f"  Total repos: {len(coverage)}")
print(f"  Low coverage (<50%): {(coverage['flag'] == 'LOW_COVERAGE').sum()}")

print("\nCoverage summary (by language):")
lang_summary = coverage.groupby('language').agg({
    'coverage_pct': ['min', 'mean', 'max'],
    'repo': 'count'
}).round(1)
print(lang_summary)

print("\nLow coverage repos (<50%):")
low_cov = coverage[coverage['flag'] == 'LOW_COVERAGE'][['repo', 'coverage_pct', 'unique_snapshots', 'total_rows']]
if len(low_cov) > 0:
    print(low_cov.to_string(index=False))
else:
    print("  None - all repos have ≥50% coverage ✓")

print("\n[OK] Build complete")
