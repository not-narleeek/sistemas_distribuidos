"""Discover traffic CSV runs and produce a manifest grouped by policy/distribution."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional

POLICY_MAP = {
    "fifo-data": "fifo",
    "lfu-data": "lfu",
    "lru-data": "lru",
}

DISTRIBUTION_HINTS = {"poisson", "uniform"}

META_TOKEN_PATTERN = re.compile(r"^(?P<key>[a-zA-Z]+)(?P<value>[0-9_\.]+)$")
RUN_ID_PATTERN = re.compile(r"^[0-9]{14,}$")


@dataclass
class TrafficRun:
    policy: str
    distribution: str
    local_path: str
    file_name: str
    size_bytes: int
    n: Optional[int] = None
    lambda_value: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    run_id: Optional[str] = None
    extra_tokens: Optional[List[str]] = None

    def as_serializable(self) -> Dict[str, object]:
        payload = asdict(self)
        # Match the naming expected in the README/spec.
        payload["lambda"] = payload.pop("lambda_value")
        return payload


def detect_distribution(tokens: Iterable[str]) -> Optional[str]:
    for token in tokens:
        lowered = token.lower()
        if lowered in DISTRIBUTION_HINTS:
            return lowered
    return None


def parse_numeric(value: str) -> Optional[float]:
    if not value:
        return None
    normalized = value.replace("_", ".")
    try:
        return float(normalized)
    except ValueError:
        return None


def parse_tokens(tokens: List[str]) -> Dict[str, object]:
    info: Dict[str, object] = {}
    extras: List[str] = []
    for token in tokens:
        lowered = token.lower()
        if lowered in DISTRIBUTION_HINTS or lowered == "traffic":
            continue
        if RUN_ID_PATTERN.match(lowered):
            info["run_id"] = token
            continue
        if lowered.startswith("n") and lowered[1:].isdigit():
            info["n"] = int(lowered[1:])
            continue
        if lowered.startswith("lambda"):
            info["lambda_value"] = parse_numeric(lowered[len("lambda") :])
            continue
        if lowered.startswith("low"):
            info["low"] = parse_numeric(lowered[len("low") :])
            continue
        if lowered.startswith("high"):
            info["high"] = parse_numeric(lowered[len("high") :])
            continue
        match = META_TOKEN_PATTERN.match(token)
        if match:
            info[match.group("key").lower()] = parse_numeric(match.group("value"))
            continue
        extras.append(token)
    if extras:
        info["extra_tokens"] = extras
    return info


def discover_runs(base_dir: pathlib.Path) -> List[TrafficRun]:
    runs: List[TrafficRun] = []
    for policy_dir, policy in POLICY_MAP.items():
        candidate_dir = base_dir / policy_dir
        if not candidate_dir.exists():
            continue
        for csv_path in candidate_dir.glob("*.csv"):
            tokens = csv_path.stem.split("_")
            distribution = detect_distribution(tokens)
            if not distribution:
                # Default to unknown but keep entry for completeness.
                distribution = "unknown"
            token_info = parse_tokens(tokens)
            run = TrafficRun(
                policy=policy,
                distribution=distribution,
                local_path=str(csv_path.as_posix()),
                file_name=csv_path.name,
                size_bytes=csv_path.stat().st_size,
                n=token_info.get("n"),
                lambda_value=token_info.get("lambda_value"),
                low=token_info.get("low"),
                high=token_info.get("high"),
                run_id=token_info.get("run_id"),
                extra_tokens=token_info.get("extra_tokens"),
            )
            runs.append(run)
    runs.sort(key=lambda r: (r.policy, r.distribution, r.file_name))
    return runs


def emit_json(runs: List[TrafficRun], output: pathlib.Path, base_dir: pathlib.Path) -> None:
    payload = {
        "schema": "traffic_manifest/v1",
        "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "base_dir": base_dir.as_posix(),
        "count": len(runs),
        "runs": [run.as_serializable() for run in runs],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def emit_csv(runs: List[TrafficRun], output: pathlib.Path) -> None:
    import csv

    fieldnames = [
        "policy",
        "distribution",
        "local_path",
        "file_name",
        "size_bytes",
        "n",
        "lambda",
        "low",
        "high",
        "run_id",
        "extra_tokens",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for run in runs:
            row = run.as_serializable()
            row["extra_tokens"] = ",".join(row["extra_tokens"]) if row.get("extra_tokens") else ""
            writer.writerow(row)


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Discover traffic CSV runs and produce a manifest.")
    parser.add_argument("--base-dir", default="data_collected/traffic", type=pathlib.Path)
    parser.add_argument("--output", default="data_collected/traffic_manifest.json", type=pathlib.Path)
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    args = parser.parse_args(list(argv) if argv is not None else None)

    runs = discover_runs(args.base_dir)
    if not runs:
        raise SystemExit("No traffic CSV files were found under the provided base directory.")

    if args.format == "json":
        emit_json(runs, args.output, args.base_dir)
    else:
        emit_csv(runs, args.output)

    print(f"Discovered {len(runs)} traffic runs. Manifest stored at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
