"""One-time importer: load Kaggle NEPSE CSVs into the SQLite ohlc table."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import db

DATA_DIR = Path("data")
SOURCE = "kaggle"


def import_file(path: Path) -> int:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                sym = (r.get("Symbol") or "").strip().upper()
                date = (r.get("Date") or "").strip()
                if not sym or not date:
                    continue
                rows.append({
                    "symbol": sym,
                    "date": date,
                    "open": float(r["Open"]) if r.get("Open") else None,
                    "high": float(r["High"]) if r.get("High") else None,
                    "low": float(r["Low"]) if r.get("Low") else None,
                    "close": float(r["Close"]) if r.get("Close") else None,
                    "volume": float(r["Volume"]) if r.get("Volume") else 0,
                })
            except (ValueError, KeyError):
                continue
    if rows:
        db.insert_ohlc_rows(rows, source=SOURCE)
        db.upsert_security(rows[0]["symbol"])
    return len(rows)


def main():
    files = sorted(DATA_DIR.glob("*.csv"))
    if not files:
        print(f"No CSV files found in {DATA_DIR.resolve()}")
        return
    print(f"Found {len(files)} CSV files. Importing...")
    total = 0
    for i, path in enumerate(files, 1):
        n = import_file(path)
        total += n
        if i % 20 == 0 or i == len(files):
            print(f"  [{i}/{len(files)}] {path.name}: {n} rows")
    print(f"\nDone. Imported {total} rows from {len(files)} files.")


if __name__ == "__main__":
    main()