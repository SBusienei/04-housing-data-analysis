"""Run SQL-first analysis or transparent segmentation as separate reviewable phases."""

import argparse
import logging
from pathlib import Path
from typing import Sequence

import psycopg

from src.artifacts import new_output_bundle
from src.config import PROJECT_ROOT
from src.database import connect_database, query_to_csv, snapshot_transaction, write_json

LOGGER = logging.getLogger(__name__)


def run_analysis(
    connection: psycopg.Connection, phase: int, output: Path
) -> None:
    if phase not in (2, 3):
        raise ValueError("Analysis runner supports Phase 2 or Phase 3 only.")
    directory = PROJECT_ROOT / "sql" / f"phase{phase}"
    with new_output_bundle(output) as staging:
        with snapshot_transaction(connection) as snapshot:
            if phase == 3:
                connection.execute(
                    (directory / "01_behavior_segments.sql").read_text(encoding="utf-8")
                )
                queries = [directory / "02_segment_summary.sql"]
            else:
                queries = sorted(directory.glob("*.sql"))
            if not queries:
                raise ValueError(f"No analysis SQL files found in {directory}.")
            outputs = {}
            for path in queries:
                filename = path.stem + ".csv"
                outputs[filename] = query_to_csv(
                    connection, path.read_text(encoding="utf-8"), staging / filename
                )
            write_json(staging / "manifest.json", {
                "phase": phase,
                "source_snapshot": snapshot.as_dict(),
                "output_rows": outputs,
                "rates": "Fractions between 0 and 1; counts are booking records.",
            })


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=int, choices=(2, 3), required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    output = args.output or PROJECT_ROOT / "data" / "processed" / f"phase{args.phase}"
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        with connect_database() as connection:
            run_analysis(connection, args.phase, output)
    except (OSError, ValueError, RuntimeError, psycopg.Error) as exc:
        LOGGER.error("Phase %s failed: %s", args.phase, exc)
        return 1
    LOGGER.info("Phase %s saved to %s. Stop and review before continuing.", args.phase, output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

