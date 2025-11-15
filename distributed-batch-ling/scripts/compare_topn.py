"""Offline comparison utilities for Pig word frequency outputs."""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Dict, Iterable

import pandas as pd

try:  # pragma: no cover - optional dependency
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover - optional dependency
    plt = None

DEFAULT_OUTPUT_DIR = pathlib.Path("distributed-batch-ling/artifacts")
DEFAULT_INPUT_DIR = DEFAULT_OUTPUT_DIR / "output"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare Yahoo vs LLM word frequencies exported from Pig")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="Directory with HDFS outputs fetched locally")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory where reports will be stored")
    parser.add_argument("--top-n", type=int, default=50, help="Number of tokens to include in the Top-N comparison")
    parser.add_argument(
        "--chart", action="store_true", help="Render a PNG bar chart when matplotlib is available"
    )
    return parser.parse_args()


def _collect_parts(path: pathlib.Path) -> Iterable[pathlib.Path]:
    if not path.exists():
        raise FileNotFoundError(f"Directory {path} not found. Run 'make fetch' first")
    return sorted(p for p in path.glob("part*") if p.is_file())


def load_counts(path: pathlib.Path) -> pd.DataFrame:
    parts = _collect_parts(path)
    if not parts:
        raise FileNotFoundError(f"No part files found under {path}")
    frames = [pd.read_csv(part, sep="\t", names=["token", "freq"], header=None) for part in parts]
    df = pd.concat(frames, ignore_index=True)
    return df.sort_values("freq", ascending=False).reset_index(drop=True)


def save_csv(df: pd.DataFrame, path: pathlib.Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def compute_comparison(full_yahoo: pd.DataFrame, full_llm: pd.DataFrame) -> pd.DataFrame:
    merged = pd.merge(full_yahoo, full_llm, on="token", how="outer", suffixes=("_yahoo", "_llm")).fillna(0)
    merged["freq_yahoo"] = merged["freq_yahoo"].astype(int)
    merged["freq_llm"] = merged["freq_llm"].astype(int)
    merged["diff"] = merged["freq_llm"] - merged["freq_yahoo"]
    merged["ratio_llm_yahoo"] = merged.apply(
        lambda row: row["freq_llm"] / row["freq_yahoo"] if row["freq_yahoo"] else float("inf"), axis=1
    )
    return merged.sort_values("diff", ascending=False)


def export_chart(top_yahoo: pd.DataFrame, top_llm: pd.DataFrame, output_path: pathlib.Path, top_n: int) -> None:
    if plt is None:
        raise RuntimeError("matplotlib is required to generate charts")
    merged = compute_comparison(top_yahoo, top_llm)
    merged = merged.head(min(top_n, len(merged)))
    merged = merged.set_index("token")[["freq_yahoo", "freq_llm"]]
    merged.plot(kind="bar", figsize=(14, 7))
    plt.title("Frecuencia Top-N: Yahoo vs LLM")
    plt.xlabel("Token")
    plt.ylabel("Frecuencia")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path)
    plt.close()


def main() -> int:
    args = parse_args()
    input_dir = pathlib.Path(args.input_dir)
    output_dir = pathlib.Path(args.output_dir)

    yahoo_full = load_counts(input_dir / "yahoo" / "full")
    llm_full = load_counts(input_dir / "llm" / "full")
    yahoo_top = load_counts(input_dir / "yahoo" / "top").head(args.top_n)
    llm_top = load_counts(input_dir / "llm" / "top").head(args.top_n)

    save_csv(yahoo_top, output_dir / "top_yahoo.csv")
    save_csv(llm_top, output_dir / "top_llm.csv")

    comparison = compute_comparison(yahoo_full, llm_full)
    save_csv(comparison, output_dir / "comparativa.csv")

    top_overlap = set(yahoo_top["token"]).intersection(set(llm_top["token"]))
    top_union = set(yahoo_top["token"]).union(set(llm_top["token"]))
    summary: Dict[str, float] = {
        "top_n": args.top_n,
        "yahoo_vocab": int(yahoo_full["token"].nunique()),
        "llm_vocab": int(llm_full["token"].nunique()),
        "top_overlap": len(top_overlap),
        "top_union": len(top_union),
        "top_jaccard": round(len(top_overlap) / len(top_union), 4) if top_union else 0.0,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.chart:
        export_chart(yahoo_top, llm_top, output_dir / "topn_comparison.png", args.top_n)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
