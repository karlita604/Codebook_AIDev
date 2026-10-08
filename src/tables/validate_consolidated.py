#!/usr/bin/env python3
"""Quick validation of consolidated table4_entities.csv"""
import pandas as pd
import sys
from pathlib import Path

csv_path = Path('results/tables/table4_entities.csv')

if not csv_path.exists():
    print(f"ERROR: {csv_path} not found")
    sys.exit(1)

print("Loading consolidated table...")
df = pd.read_csv(csv_path, dtype={'rel_month': str}, low_memory=False)

print(f"[OK] Loaded: {len(df):,} rows, {len(df.columns)} columns")
print(f"\nUnique repos: {df['repo'].nunique()}")
print(f"Unique entities: {df['entity_id'].nunique()}")
print(f"Unique months: {sorted(df['rel_month'].unique())}")
print(f"Kinds: {df['kind'].unique().tolist()}")

# Check for nulls
print(f"\nNull counts (all columns):")
nulls = df.isnull().sum().sort_values(ascending=False)
print(nulls[nulls > 0] if (nulls > 0).any() else "No nulls found [OK]")

# Check numeric columns
print(f"\nMetric ranges:")
for col in ['loc', 'cc', 'nesting', 'wmc']:
    if col in df.columns:
        print(f"  {col}: {df[col].min():.0f} - {df[col].max():.0f}")

print("\n[OK] Validation complete")
