"""Parquet build of the core tables.

  python -m tkcore.build --parquet     dist/core/{kurals,adhikarams,divisions}.parquet from data/core/*.jsonl

Without --parquet the tables are read and converted to their Arrow schemas, and nothing is written.
Same input gives byte-identical output (tests/test_build.py).
"""
import argparse
import json
from pathlib import Path

from . import DATA_CORE, ROOT
from .schema import TABLES

DIST = ROOT / "dist" / "core"


def load_tables(core: Path = DATA_CORE) -> dict[str, list[dict]]:
    return {name: [json.loads(line) for line in (core / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
                   if line.strip()] for name in TABLES}


def arrow_tables(tables: dict):
    import pyarrow as pa
    return {name: pa.Table.from_pylist(rows, schema=TABLES[name][1]) for name, rows in tables.items()}


def write_parquet(tables: dict, out: Path = DIST):
    import pyarrow.parquet as pq
    out.mkdir(parents=True, exist_ok=True)
    for name, t in arrow_tables(tables).items():
        pq.write_table(t, out / f"{name}.parquet", compression="zstd", compression_level=19,
                       write_statistics=False, store_schema=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", action="store_true", help="write dist/core/*.parquet")
    args = ap.parse_args(argv)
    tables = load_tables()
    if args.parquet:
        write_parquet(tables)
    else:
        arrow_tables(tables)


if __name__ == "__main__":
    main()
