"""Upload normalized traffic CSVs to HDFS segmented by policy/distribution."""
from __future__ import annotations

import argparse
import json
import pathlib
import posixpath
import subprocess
from typing import Dict, Iterable, List, Tuple

HDFS_EXEC = "/opt/hdfs_exec.sh"
POLICY_KEY = "policy"
DISTRIBUTION_KEY = "distribution"


def load_manifest(path: pathlib.Path) -> List[Dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "runs" in data:
        return data["runs"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported manifest format in {path}")


def normalized_path(base_dir: pathlib.Path, policy: str, distribution: str) -> pathlib.Path:
    return base_dir / policy / distribution / f"traffic_{policy}_{distribution}.csv"


def compose_cmd(compose_file: str, *args: str) -> List[str]:
    return ["docker", "compose", "-f", compose_file, *args]


def run(cmd: Iterable[str]) -> None:
    subprocess.run(list(cmd), check=True)


def upload_file(
    compose_file: str,
    local_path: pathlib.Path,
    hdfs_path: str,
    namenode: str = "namenode",
) -> None:
    tmp_path = f"/tmp/{local_path.name}"
    hdfs_dir = posixpath.dirname(hdfs_path)
    run(compose_cmd(compose_file, "cp", str(local_path), f"{namenode}:{tmp_path}"))
    run(
        compose_cmd(
            compose_file,
            "exec",
            "-T",
            namenode,
            "sh",
            "-c",
            f"{HDFS_EXEC} dfs -mkdir -p {hdfs_dir} && {HDFS_EXEC} dfs -put -f {tmp_path} {hdfs_path} && rm -f {tmp_path}",
        )
    )


def publish(manifest: List[Dict[str, object]], base_dir: pathlib.Path, compose_file: str) -> List[Tuple[str, str]]:
    seen: Dict[Tuple[str, str], bool] = {}
    uploaded: List[Tuple[str, str]] = []
    for entry in manifest:
        policy = str(entry.get(POLICY_KEY))
        distribution = str(entry.get(DISTRIBUTION_KEY))
        if not policy or not distribution:
            raise ValueError(f"Manifest entry missing policy/distribution: {entry}")
        key = (policy, distribution)
        if key in seen:
            continue
        seen[key] = True
        local = normalized_path(base_dir, policy, distribution)
        if not local.exists():
            raise FileNotFoundError(f"Normalized file not found: {local}. Run normalize_traffic_csv.py first.")
        hdfs_target_dir = f"/data/in/traffic/{policy}/{distribution}"
        hdfs_target = f"{hdfs_target_dir}/{local.name}"
        upload_file(compose_file, local, hdfs_target)
        uploaded.append((policy, distribution))
    return uploaded


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upload normalized traffic CSVs to HDFS.")
    parser.add_argument("--manifest", default="data_collected/traffic_manifest.json", type=pathlib.Path)
    parser.add_argument("--normalized-dir", default=pathlib.Path("data_normalized/traffic"), type=pathlib.Path)
    parser.add_argument("--compose-file", default="distributed-batch-ling/deploy/docker-compose.yml")
    args = parser.parse_args(list(argv) if argv is not None else None)

    manifest = load_manifest(args.manifest)
    uploaded = publish(manifest, args.normalized_dir, args.compose_file)
    for policy, distribution in uploaded:
        print(f"Uploaded {policy}/{distribution} to HDFS")
    if not uploaded:
        print("No new traffic datasets were uploaded (already processed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
