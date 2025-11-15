"""Utility to compute throughput metrics from Pig logs and HDFS outputs."""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

LOG_DIR = pathlib.Path("distributed-batch-ling/logs")
DEFAULT_LOGS = {
    "yahoo": LOG_DIR / "pig_yahoo.log",
    "llm": LOG_DIR / "pig_llm.log",
    "compare": LOG_DIR / "pig_compare.log",
}


@dataclass
class JobMetrics:
    dataset: str
    elapsed_seconds: Optional[float]
    input_records: Optional[int]
    input_size: Optional[int]
    output_records: Optional[int]
    output_size: Optional[int]

    def throughput(self) -> Optional[float]:
        if self.elapsed_seconds and self.input_records:
            return round(self.input_records / self.elapsed_seconds, 2)
        return None

    def to_dict(self) -> Dict[str, Optional[float]]:
        payload = {
            "dataset": self.dataset,
            "elapsed_seconds": self.elapsed_seconds,
            "input_records": self.input_records,
            "input_size_bytes": self.input_size,
            "output_records": self.output_records,
            "output_size_bytes": self.output_size,
            "throughput_records_per_second": self.throughput(),
        }
        return payload


def parse_log(path: pathlib.Path) -> Optional[float]:
    if not path.exists():
        return None
    pattern = re.compile(r"Time taken: ([0-9.]+) seconds")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.search(line)
        if match:
            return float(match.group(1))
    return None


HDFS_EXEC = "/opt/hdfs_exec.sh"


def hdfs_count_lines(compose_file: str, path: str, namenode: str = "namenode") -> int:
    cmd = [
        "docker",
        "compose",
        "-f",
        compose_file,
        "exec",
        "-T",
        namenode,
        "sh",
        "-lc",
        f"{HDFS_EXEC} dfs -cat {path}/* | wc -l"
    ]
    try:
        output = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        return 0
    return int(output.strip()) if output.strip() else 0


def hdfs_stats(compose_file: str, path: str, namenode: str = "namenode") -> Dict[str, int]:
    cmd = [
        "docker",
        "compose",
        "-f",
        compose_file,
        "exec",
        "-T",
        namenode,
        "sh",
        "-lc",
        f"{HDFS_EXEC} dfs -count -q {path}"
    ]
    try:
        output = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        return {"dirs": 0, "files": 0, "size": 0}
    parts = output.strip().split()
    if len(parts) < 8:
        raise RuntimeError(f"Unexpected output from hdfs dfs -count: {output}")
    # Format: QUOTA REM_QUOTA SPACE_QUOTA REM_SPACE_QUOTA DIR_COUNT FILE_COUNT CONTENT_SIZE PATHNAME
    return {
        "dirs": int(parts[4]),
        "files": int(parts[5]),
        "size": int(parts[6]),
    }


def calculate_metrics(compose_file: str) -> Iterable[JobMetrics]:
    datasets = {
        "yahoo": {
            "input": "/data/input/yahoo",
            "output": "/data/output/yahoo/full",
            "log": DEFAULT_LOGS["yahoo"],
        },
        "llm": {
            "input": "/data/input/llm",
            "output": "/data/output/llm/full",
            "log": DEFAULT_LOGS["llm"],
        },
    }

    for name, conf in datasets.items():
        elapsed = parse_log(conf["log"])
        input_stats = hdfs_stats(compose_file, conf["input"])
        output_stats = hdfs_stats(compose_file, conf["output"])
        input_lines = hdfs_count_lines(compose_file, conf["input"])
        output_lines = hdfs_count_lines(compose_file, conf["output"])
        input_records = max(input_lines, 0)
        output_records = max(output_lines, 0)
        yield JobMetrics(
            dataset=name,
            elapsed_seconds=elapsed,
            input_records=input_records,
            input_size=input_stats["size"],
            output_records=output_records,
            output_size=output_stats["size"],
        )


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Calculate batch analysis metrics from HDFS and Pig logs.")
    parser.add_argument("--compose-file", default="distributed-batch-ling/deploy/docker-compose.yml")
    args = parser.parse_args(list(argv) if argv is not None else None)

    metrics = [metric.to_dict() for metric in calculate_metrics(args.compose_file)]
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
