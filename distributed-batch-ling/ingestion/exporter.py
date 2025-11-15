"""Batch ingestion utility to export responses into Hadoop-ready CSV files."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import sys
import time
from dataclasses import dataclass
from typing import Iterable, Iterator, List, MutableMapping, Optional

HDFS_PATH_EXPORT = "PATH=$PATH:/opt/hadoop/bin:/opt/hadoop-3.2.1/bin"

try:
    from pymongo import MongoClient
except ImportError:  # pragma: no cover - optional dependency
    MongoClient = None  # type: ignore

REQUIRED_COLUMNS = {"id_pregunta", "respuesta_texto", "origen", "ts_creacion"}
VALID_ORIGINS = {"yahoo", "llm"}
DEFAULT_CHUNK_SIZE = 10_000

Record = MutableMapping[str, str]
Chunk = List[Record]


@dataclass
class ExportStats:
    total_records: int = 0
    yahoo_records: int = 0
    llm_records: int = 0
    start_time: float = time.perf_counter()

    def as_dict(self) -> dict:
        elapsed = time.perf_counter() - self.start_time
        throughput = self.total_records / elapsed if elapsed else 0
        return {
            "total_records": self.total_records,
            "yahoo_records": self.yahoo_records,
            "llm_records": self.llm_records,
            "elapsed_seconds": round(elapsed, 3),
            "records_per_second": round(throughput, 2),
        }


class ValidationError(Exception):
    """Raised when the dataset does not comply with the expected schema."""


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export responses from a CSV/Parquet dump or MongoDB into Hadoop-ingestable CSVs",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--input",
        help="Path to an input CSV or Parquet file containing the responses.",
    )
    source.add_argument(
        "--mongo-uri",
        help="MongoDB connection string to export from the live database.",
    )
    parser.add_argument(
        "--mongo-db",
        help="MongoDB database name (required when --mongo-uri is provided).",
    )
    parser.add_argument(
        "--mongo-collection",
        help="MongoDB collection containing the responses (required when --mongo-uri is provided).",
    )
    parser.add_argument(
        "--output-dir",
        default="distributed-batch-ling/ingestion/output",
        help="Directory where the partitioned CSV files will be stored.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Number of records processed per chunk (for CSV inputs).",
    )
    parser.add_argument(
        "--hdfs-base",
        help=(
            "Optional HDFS base path. When provided the generated files will be pushed to the cluster using "
            "hdfs dfs -put."
        ),
    )
    parser.add_argument(
        "--namenode-container",
        default="namenode",
        help="Name of the namenode container to target when pushing to HDFS via docker compose exec.",
    )
    parser.add_argument(
        "--compose-file",
        default="distributed-batch-ling/deploy/docker-compose.yml",
        help="Docker compose file used to locate the namenode container.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the exporter without writing files. Useful for schema validation only.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress information while exporting.",
    )
    return parser.parse_args(argv)


def _sniff_dialect(path: pathlib.Path) -> csv.Dialect:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            return csv.Sniffer().sniff(sample, delimiters=",;|\t")
    except (csv.Error, OSError):
        return csv.get_dialect("excel")


def iter_records_from_csv(path: pathlib.Path, chunk_size: int) -> Iterator[Chunk]:
    dialect = _sniff_dialect(path)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, dialect=dialect)
        if reader.fieldnames is None:
            raise ValidationError("Input CSV must include a header row with column names")

        normalized_headers = [header.strip() for header in reader.fieldnames]
        missing = REQUIRED_COLUMNS - set(normalized_headers)
        if missing:
            raise ValidationError(
                "Input is missing required columns: " + ", ".join(sorted(missing))
            )

        batch: Chunk = []
        for raw_row in reader:
            row: Record = {key.strip(): (value or "") for key, value in raw_row.items()}
            batch.append(row)
            if len(batch) >= chunk_size:
                yield batch
                batch = []
        if batch:
            yield batch


def iter_records_from_parquet(path: pathlib.Path) -> Iterator[Chunk]:
    try:
        import pandas as pd  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Reading Parquet files requires pandas to be installed."
        ) from exc

    df = pd.read_parquet(path)
    yield [dict(row) for row in df.to_dict(orient="records")]


def iter_records_from_mongo(args: argparse.Namespace) -> Iterator[Chunk]:
    if MongoClient is None:
        raise RuntimeError("pymongo must be installed to export from MongoDB.")
    if not args.mongo_db or not args.mongo_collection:
        raise ValidationError("--mongo-db and --mongo-collection are required with --mongo-uri")

    client = MongoClient(args.mongo_uri)
    collection = client[args.mongo_db][args.mongo_collection]
    cursor = collection.find({}, projection={"_id": 0})
    batch: Chunk = []
    for document in cursor:
        batch.append({key: str(value) if value is not None else "" for key, value in document.items()})
        if len(batch) >= args.chunk_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _normalize_timestamp(raw_value: str) -> str:
    raw_value = raw_value.strip()
    if not raw_value:
        return ""

    candidates = [raw_value]
    if raw_value.endswith("Z"):
        candidates.append(raw_value[:-1])

    for candidate in candidates:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
            try:
                parsed = dt.datetime.strptime(candidate, fmt)
                return parsed.strftime("%Y-%m-%dT%H:%M:%S")
            except ValueError:
                continue
        try:
            parsed = dt.datetime.fromisoformat(candidate)
            return parsed.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return ""


def validate_chunk(chunk: Chunk) -> Chunk:
    if not chunk:
        return chunk

    missing = REQUIRED_COLUMNS - set(chunk[0].keys())
    if missing:
        raise ValidationError(f"Input is missing required columns: {', '.join(sorted(missing))}")

    cleaned: Chunk = []
    invalid_origins: set[str] = set()
    for row in chunk:
        origin = str(row.get("origen", "")).strip().lower()
        text = str(row.get("respuesta_texto", "")).strip()
        if not text or not origin:
            continue
        if origin not in VALID_ORIGINS:
            invalid_origins.add(origin)
            continue
        normalized: Record = {
            "id_pregunta": str(row.get("id_pregunta", "")).strip(),
            "respuesta_texto": _clean_text(text),
            "origen": origin,
            "ts_creacion": _normalize_timestamp(str(row.get("ts_creacion", ""))),
        }
        cleaned.append(normalized)

    if invalid_origins:
        raise ValidationError(
            "Found rows with invalid 'origen' values: " + ", ".join(sorted(invalid_origins))
        )

    return cleaned


def _clean_text(value: str) -> str:
    """Normalize text for newline-safe exports."""

    value = value.replace("\r", " ").replace("\n", " ")
    # Collapse repeated whitespace to keep one space between tokens
    return " ".join(value.split())


def write_partitioned_outputs(
    chunks: Iterable[Chunk],
    output_dir: pathlib.Path,
    dry_run: bool = False,
    verbose: bool = False,
) -> ExportStats:
    output_dir.mkdir(parents=True, exist_ok=True)
    yahoo_csv_path = output_dir / "yahoo_respuestas.csv"
    llm_csv_path = output_dir / "llm_respuestas.csv"
    yahoo_txt_path = output_dir / "yahoo_respuestas.txt"
    llm_txt_path = output_dir / "llm_respuestas.txt"

    yahoo_file = open(yahoo_csv_path, "w", newline="", encoding="utf-8") if not dry_run else None
    llm_file = open(llm_csv_path, "w", newline="", encoding="utf-8") if not dry_run else None
    yahoo_txt = open(yahoo_txt_path, "w", encoding="utf-8") if not dry_run else None
    llm_txt = open(llm_txt_path, "w", encoding="utf-8") if not dry_run else None
    yahoo_writer = csv.DictWriter(yahoo_file, fieldnames=sorted(REQUIRED_COLUMNS)) if yahoo_file else None
    llm_writer = csv.DictWriter(llm_file, fieldnames=sorted(REQUIRED_COLUMNS)) if llm_file else None

    if yahoo_writer:
        yahoo_writer.writeheader()
    if llm_writer:
        llm_writer.writeheader()

    stats = ExportStats()

    for chunk in chunks:
        chunk = validate_chunk(chunk)
        if not chunk:
            continue
        stats.total_records += len(chunk)
        yahoo_rows = [row for row in chunk if row["origen"] == "yahoo"]
        llm_rows = [row for row in chunk if row["origen"] == "llm"]
        stats.yahoo_records += len(yahoo_rows)
        stats.llm_records += len(llm_rows)

        if yahoo_writer:
            for row in yahoo_rows:
                yahoo_writer.writerow(row)
                if yahoo_txt:
                    yahoo_txt.write(_clean_text(row["respuesta_texto"]) + "\n")
        elif yahoo_txt:
            for row in yahoo_rows:
                yahoo_txt.write(_clean_text(row["respuesta_texto"]) + "\n")

        if llm_writer:
            for row in llm_rows:
                llm_writer.writerow(row)
                if llm_txt:
                    llm_txt.write(_clean_text(row["respuesta_texto"]) + "\n")
        elif llm_txt:
            for row in llm_rows:
                llm_txt.write(_clean_text(row["respuesta_texto"]) + "\n")

        if verbose:
            print(
                json.dumps(
                    {
                        "total_written": stats.total_records,
                        "yahoo_written": stats.yahoo_records,
                        "llm_written": stats.llm_records,
                    }
                )
            )

    for handler in (yahoo_file, llm_file, yahoo_txt, llm_txt):
        if handler:
            handler.close()

    return stats


def push_to_hdfs(
    output_dir: pathlib.Path,
    hdfs_base: str,
    compose_file: str,
    namenode_container: str,
    verbose: bool = False,
) -> None:
    import subprocess

    local_files = {
        "yahoo": output_dir / "yahoo_respuestas.txt",
        "llm": output_dir / "llm_respuestas.txt",
    }
    for origin, path in local_files.items():
        if not path.exists():
            raise FileNotFoundError(f"Expected output file {path} does not exist")
        tmp_path = f"/tmp/{path.name}"
        copy_cmd = [
            "docker",
            "compose",
            "-f",
            compose_file,
            "cp",
            str(path),
            f"{namenode_container}:{tmp_path}",
        ]
        if verbose:
            print("Running:", " ".join(copy_cmd))
        subprocess.run(copy_cmd, check=True)

        hdfs_target = f"{hdfs_base.rstrip('/')}/{origin}/"
        exec_cmd = [
            "docker",
            "compose",
            "-f",
            compose_file,
            "exec",
            "-T",
            namenode_container,
            "sh",
            "-lc",
            f"{HDFS_PATH_EXPORT} hdfs dfs -mkdir -p {hdfs_target} && {HDFS_PATH_EXPORT} hdfs dfs -put -f {tmp_path} {hdfs_target}",
        ]
        if verbose:
            print("Running:", " ".join(exec_cmd))
        subprocess.run(exec_cmd, check=True)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if args.input:
        input_path = pathlib.Path(args.input)
        if not input_path.exists():
            raise SystemExit(f"Input file {input_path} not found")
        suffix = input_path.suffix.lower()
        if suffix == ".csv":
            iterator = iter_records_from_csv(input_path, args.chunk_size)
        elif suffix in {".parquet", ".pq"}:
            iterator = iter_records_from_parquet(input_path)
        else:
            raise SystemExit("Unsupported input format. Use CSV or Parquet.")
    else:
        iterator = iter_records_from_mongo(args)

    output_dir = pathlib.Path(args.output_dir)
    stats = write_partitioned_outputs(iterator, output_dir, dry_run=args.dry_run, verbose=args.verbose)

    summary = stats.as_dict()
    print(json.dumps({"status": "completed", **summary}, indent=2))

    if args.hdfs_base and not args.dry_run:
        push_to_hdfs(
            output_dir=output_dir,
            hdfs_base=args.hdfs_base,
            compose_file=args.compose_file,
            namenode_container=args.namenode_container,
            verbose=args.verbose,
        )
        print(json.dumps({"status": "uploaded", "hdfs_base": args.hdfs_base}, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
