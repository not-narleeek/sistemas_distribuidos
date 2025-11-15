"""Execute the Pig traffic analysis for every (policy, distribution) combination."""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
from typing import Dict, Iterable, List, Tuple

PIG_SCRIPT = "/opt/pig/scripts/traffic_analysis.pig"
PIG_LOG_DIR = "/opt/pig/logs"
HDFS_EXEC = "/opt/hdfs_exec.sh"


def load_manifest(path: pathlib.Path) -> List[Dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "runs" in data:
        return data["runs"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported manifest format in {path}")


def compose_cmd(compose_file: str, *args: str) -> List[str]:
    return ["docker", "compose", "-f", compose_file, *args]


def run(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True)


def combos(manifest: List[Dict[str, object]]) -> List[Tuple[str, str]]:
    seen = set()
    ordered: List[Tuple[str, str]] = []
    for entry in manifest:
        policy_value = entry.get("policy")
        distribution_value = entry.get("distribution")
        if not policy_value or not distribution_value:
            raise ValueError(f"Manifest entry missing policy/distribution: {entry}")
        policy = str(policy_value)
        distribution = str(distribution_value)
        key = (policy, distribution)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def cleanup_hdfs(compose_file: str, policy: str, distribution: str) -> None:
    target = f"/data/out/traffic/{policy}/{distribution}"
    cmd = compose_cmd(
        compose_file,
        "exec",
        "-T",
        "namenode",
        "sh",
        "-c",
        f"{HDFS_EXEC} dfs -rm -r -f {target} >/dev/null 2>&1 || true",
    )
    run(cmd)


def run_pig(compose_file: str, policy: str, distribution: str) -> None:
    input_path = f"/data/in/traffic/{policy}/{distribution}/traffic_{policy}_{distribution}.csv"
    output_path = f"/data/out/traffic/{policy}/{distribution}"
    log_name = f"pig_traffic_{policy}_{distribution}.log"
    pig_cmd = (
        "set -o pipefail && /opt/pig/bin/pig -x mapreduce "
        f"-param POLICY={policy} -param DISTRIBUTION={distribution} "
        f"-param INPUT={input_path} -param OUTPUT={output_path} "
        f"-f {PIG_SCRIPT} 2>&1 | tee {PIG_LOG_DIR}/{log_name}"
    )
    cmd = compose_cmd(
        compose_file,
        "exec",
        "-T",
        "pig",
        "bash",
        "-lc",
        pig_cmd,
    )
    run(cmd)
    logs_dir = pathlib.Path("distributed-batch-ling/logs")
    pig_logs = logs_dir / "pig"
    pig_logs.mkdir(parents=True, exist_ok=True)
    run(
        compose_cmd(
            compose_file,
            "cp",
            f"pig:{PIG_LOG_DIR}/{log_name}",
            str(pig_logs / log_name),
        )
    )
    # Convenience copy mirroring the yahoo/llm behaviour.
    shutil.copy2(pig_logs / log_name, logs_dir / log_name)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Pig traffic analysis for all policy/distribution combos.")
    parser.add_argument("--manifest", default="data_collected/traffic_manifest.json", type=pathlib.Path)
    parser.add_argument("--compose-file", default="distributed-batch-ling/deploy/docker-compose.yml")
    args = parser.parse_args(list(argv) if argv is not None else None)

    manifest = load_manifest(args.manifest)
    targets = combos(manifest)
    if not targets:
        raise SystemExit("Manifest did not contain any policy/distribution combinations.")

    pathlib.Path("distributed-batch-ling/logs").mkdir(parents=True, exist_ok=True)
    for policy, distribution in targets:
        print(f"Running Pig job for {policy}/{distribution}")
        cleanup_hdfs(args.compose_file, policy, distribution)
        run_pig(args.compose_file, policy, distribution)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
