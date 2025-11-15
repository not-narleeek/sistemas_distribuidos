"""Fetch Pig traffic outputs from HDFS into the local artifacts folder."""
from __future__ import annotations

import argparse
import json
import pathlib
import posixpath
import subprocess
from typing import Dict, Iterable, List, Tuple

HDFS_EXEC = "/opt/hdfs_exec.sh"
ARTIFACT_ROOT = pathlib.Path("distributed-batch-ling/artifacts/traffic")


def load_manifest(path: pathlib.Path) -> List[Dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "runs" in data:
        return data["runs"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Unsupported manifest format in {path}")


def compose_cmd(compose_file: str, *args: str) -> List[str]:
    return ["docker", "compose", "-f", compose_file, *args]


def run(cmd: Iterable[str]) -> None:
    subprocess.run(list(cmd), check=True)


def combos(manifest: List[Dict[str, object]]) -> List[Tuple[str, str]]:
    seen = set()
    ordered: List[Tuple[str, str]] = []
    for entry in manifest:
        policy = entry.get("policy")
        distribution = entry.get("distribution")
        if not policy or not distribution:
            raise ValueError(f"Manifest entry missing policy/distribution: {entry}")
        key = (str(policy), str(distribution))
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def fetch_dataset(compose_file: str, policy: str, distribution: str) -> None:
    outputs = {
        "stats_global": f"/data/out/traffic/{policy}/{distribution}/stats_global_{policy}_{distribution}",
        "stats_by_topic": f"/data/out/traffic/{policy}/{distribution}/stats_by_topic_{policy}_{distribution}",
        "stats_by_status": f"/data/out/traffic/{policy}/{distribution}/stats_by_status_{policy}_{distribution}",
    }
    tmp_root = pathlib.Path("/tmp/traffic_fetch")
    run(
        compose_cmd(
            compose_file,
            "exec",
            "-T",
            "namenode",
            "sh",
            "-c",
            f"rm -rf {tmp_root} && mkdir -p {tmp_root}",
        )
    )
    for label, hdfs_path in outputs.items():
        local_name = f"{label}_{policy}_{distribution}.tsv"
        tmp_target = posixpath.join(str(tmp_root), local_name)
        cmd = compose_cmd(
            compose_file,
            "exec",
            "-T",
            "namenode",
            "sh",
            "-c",
            f"if {HDFS_EXEC} dfs -test -e {hdfs_path}; then {HDFS_EXEC} dfs -cat {hdfs_path}/* > {tmp_target}; fi",
        )
        run(cmd)
        try:
            run(compose_cmd(compose_file, "exec", "-T", "namenode", "test", "-f", tmp_target))
        except subprocess.CalledProcessError:
            # Nothing to copy for this dataset.
            continue
        run(compose_cmd(compose_file, "cp", f"namenode:{tmp_target}", str(ARTIFACT_ROOT / local_name)))
    run(compose_cmd(compose_file, "exec", "-T", "namenode", "rm", "-rf", str(tmp_root)))


def main(argv: Iterable[str] | None = None) -> int:
    global ARTIFACT_ROOT

    parser = argparse.ArgumentParser(description="Fetch traffic Pig outputs from HDFS.")
    parser.add_argument("--manifest", default="data_collected/traffic_manifest.json", type=pathlib.Path)
    parser.add_argument("--compose-file", default="distributed-batch-ling/deploy/docker-compose.yml")
    parser.add_argument("--output-dir", default=ARTIFACT_ROOT, type=pathlib.Path)
    args = parser.parse_args(list(argv) if argv is not None else None)

    manifest = load_manifest(args.manifest)
    targets = combos(manifest)
    if not targets:
        raise SystemExit("Manifest did not contain any policy/distribution combinations.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ARTIFACT_ROOT = args.output_dir

    for policy, distribution in targets:
        print(f"Fetching outputs for {policy}/{distribution}")
        fetch_dataset(args.compose_file, policy, distribution)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
