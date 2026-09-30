"""Delete symbols with fewer than 100 bars — noise from live snapshot."""
from database import db

with db.get_conn() as conn:
    rows = conn.execute(
        "SELECT symbol, COUNT(*) AS n FROM ohlc GROUP BY symbol HAVING n < 100"
    ).fetchall()
    print(f"Found {len(rows)} symbols with <100 bars")
    for r in rows:
        conn.execute("DELETE FROM ohlc WHERE symbol = ?", (r["symbol"],))
        conn.execute("DELETE FROM securities WHERE symbol = ?", (r["symbol"],))
    print(f"Deleted {len(rows)} symbols and their rows")

    total = conn.execute("SELECT COUNT(*) FROM ohlc").fetchone()[0]
    print(f"Remaining ohlc rows: {total}")

    kept = conn.execute(
        "SELECT symbol, COUNT(*) AS n FROM ohlc GROUP BY symbol ORDER BY n DESC"
    ).fetchall()
    print(f"Remaining symbols: {len(kept)}")
    for r in kept[:10]:
        print(f"  {r['symbol']}: {r['n']}")