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
    'nesting', 'wmc', 'atfd', 'tcc', 'flags', 'episode',
    'created_sha', 'created_by', 'smell_sha', 'smell_by', 'smell_pr',
    'removed_sha', 'removed_by', 'noav', 'laa', 'fdp', 'class_id', 'x_episode_start_rel_month'
]

entity_dir = Path("results/tables/table4_entities")
errors = []
warnings = []

print(f"Validating schema in {entity_dir}")
print(f"Expected {len(EXPECTED_COLS)} columns\n")

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
    print("[ERROR] SCHEMA VALIDATION FAILED:")
    for err in errors:
        print(f"  {err}")
    sys.exit(1)

if warnings:
    print("[WARNING] Warnings (non-fatal):")
    for warn in warnings:
        print(f"  {warn}")

num_repos = len(list(entity_dir.glob('*.csv.gz')))
print(f"[OK] Schema valid: {num_repos} repos checked")
sys.exit(0)
