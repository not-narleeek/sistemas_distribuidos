"""Normalize raw traffic CSV files into a canonical schema grouped by policy/distribution."""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
from collections import defaultdict
from typing import Dict, Iterable, Iterator, List, Optional

CANONICAL_HEADER = [
    "timestamp_iso",
    "operation",
    "message_id",
    "question_id",
    "status",
    "latency_seconds",
    "topic",
    "policy",
    "distribution",
    "is_hit",
    "was_evicted",
]


def load_manifest(path: pathlib.Path) -> List[Dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "runs" in data:
        return data["runs"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported manifest format in {path}")


def sniff_dialect(sample_path: pathlib.Path) -> csv.Dialect:
    sniffer = csv.Sniffer()
    with sample_path.open("r", encoding="utf-8", newline="") as handle:
        sample = handle.read(4096)
    if not sample:
        return csv.get_dialect("excel")
    try:
        dialect = sniffer.sniff(sample, delimiters=",;|\t")
    except csv.Error:
        return csv.get_dialect("excel")
    return dialect


def float_from(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    normalized = value.replace(",", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def infer_flag(value: Optional[str], keywords: Iterable[str]) -> int:
    if not value:
        return 0
    upper = value.strip().upper()
    return int(any(keyword in upper for keyword in keywords))


def iter_rows(path: pathlib.Path, dialect: csv.Dialect) -> Iterator[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, dialect=dialect)
        for row in reader:
            yield row


def normalize_row(row: Dict[str, str], policy: str, distribution: str) -> List[object]:
    timestamp = row.get("timestamp") or row.get("ts") or row.get("time") or ""
    operation = row.get("operation") or row.get("op") or ""
    message_id = row.get("message_id") or row.get("request_id") or ""
    question_id = row.get("question_id") or row.get("object_id") or ""
    status = row.get("status") or row.get("result") or ""
    latency = float_from(row.get("latency") or row.get("latency_seconds") or row.get("duration")) or 0.0
    topic = row.get("topic") or row.get("queue") or row.get("bucket") or ""
    is_hit = infer_flag(status or operation, ["HIT", "CACHE_HIT"]) or infer_flag(row.get("is_hit"), ["1", "TRUE"])
    was_evicted = infer_flag(status, ["EVICT"]) or infer_flag(row.get("was_evicted"), ["1", "TRUE"])
    return [
        timestamp,
        operation,
        message_id,
        question_id,
        status,
        latency,
        topic,
        policy,
        distribution,
        is_hit,
        was_evicted,
    ]


def normalize(manifest: List[Dict[str, object]], output_dir: pathlib.Path, overwrite: bool = False) -> Dict[str, int]:
    groups: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for entry in manifest:
        policy = str(entry.get("policy"))
        distribution = str(entry.get("distribution"))
        if not policy or not distribution:
            raise ValueError(f"Manifest entry is missing policy/distribution: {entry}")
        groups[f"{policy}/{distribution}"].append(entry)

    output_dir.mkdir(parents=True, exist_ok=True)
    summary: Dict[str, int] = {}
    for key, entries in sorted(groups.items()):
        policy, distribution = key.split("/")
        target_dir = output_dir / policy / distribution
        target_dir.mkdir(parents=True, exist_ok=True)
        output_path = target_dir / f"traffic_{policy}_{distribution}.csv"
        if output_path.exists() and not overwrite:
            summary[key] = -1
            continue
        total_rows = 0
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(CANONICAL_HEADER)
            for entry in entries:
                source_path = pathlib.Path(entry["local_path"]).expanduser()
                if not source_path.exists():
                    raise FileNotFoundError(f"Missing source file {source_path}")
                dialect = sniff_dialect(source_path)
                for row in iter_rows(source_path, dialect):
                    writer.writerow(normalize_row(row, policy, distribution))
                    total_rows += 1
        summary[key] = total_rows
    return summary


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize traffic CSV dumps into a canonical schema.")
    parser.add_argument("--manifest", default="data_collected/traffic_manifest.json", type=pathlib.Path)
    parser.add_argument("--output-dir", default=pathlib.Path("data_normalized/traffic"), type=pathlib.Path)
    parser.add_argument("--overwrite", action="store_true", help="Recreate normalized files even if they already exist")
    args = parser.parse_args(list(argv) if argv is not None else None)

    manifest = load_manifest(args.manifest)
    summary = normalize(manifest, args.output_dir, overwrite=args.overwrite)
    for key, rows in summary.items():
        if rows < 0:
            print(f"Skipped {key}: normalized file already exists (use --overwrite to regenerate)")
        else:
            print(f"Normalized {rows} rows for {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
