"""Inspect a current workflow gate; optionally export a report without overwriting files."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from factory.repositories.connection import Database
from factory.services.quality_gate_service import QualityGateService, canonical_report
from factory.exceptions import FactoryError

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if not args.db.is_file():
            raise ValueError("Database does not exist; run a workflow first")
        report = QualityGateService(Database(args.db)).evaluate(args.workflow)
        payload = canonical_report(report)
        if args.output:
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(payload)
        print(payload)
        return 0 if report["verdict"] == "GO" else 2
    except (FactoryError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
if __name__ == "__main__":
    raise SystemExit(main())
