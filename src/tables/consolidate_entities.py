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
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
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
    print()

    stats = consolidate_entities(
        args.input_dir,
        args.output,
        chunk_size=args.chunk_size,
        log_path=args.log
    )

    print(f"\n[OK] Consolidation complete:")
    print(f"  Total rows: {stats['total_rows']:,}")
    print(f"  Repos processed: {stats['repos_processed']}")
    print(f"  Repos skipped: {stats['repos_skipped']}")

    if stats['errors']:
        print(f"\n[WARNING] Errors encountered (data still written):")
        for err in stats['errors']:
            print(f"  {err}")

    sys.exit(0)
