"""Aggregate Pig traffic outputs into a global summary for the report."""
from __future__ import annotations

import argparse
import csv
import pathlib
from typing import Dict, Iterable, List


def load_tsv(path: pathlib.Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader)


def summarize_global(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    summary: List[Dict[str, str]] = []
    for row in rows:
        summary.append(
            {
                "policy": row.get("policy", ""),
                "distribution": row.get("distribution", ""),
                "total_requests": row.get("total_requests", "0"),
                "total_hits": row.get("total_hits", "0"),
                "total_evictions": row.get("total_evictions", "0"),
                "hit_ratio": row.get("hit_ratio", "0"),
                "avg_latency_seconds": row.get("avg_latency_seconds", "0"),
            }
        )
    return summary


def write_summary(rows: List[Dict[str, str]], output: pathlib.Path) -> None:
    if not rows:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Pig traffic outputs across policies and distributions.")
    parser.add_argument("--input-dir", default="distributed-batch-ling/artifacts/traffic", type=pathlib.Path)
    parser.add_argument("--output", default="distributed-batch-ling/artifacts/traffic/summary_global_policies_distributions.tsv", type=pathlib.Path)
    args = parser.parse_args(list(argv) if argv is not None else None)

    rows: List[Dict[str, str]] = []
    for path in args.input_dir.glob("stats_global_*.tsv"):
        rows.extend(load_tsv(path))
    summary = summarize_global(rows)
    write_summary(summary, args.output)
    print(f"Wrote summary with {len(summary)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
