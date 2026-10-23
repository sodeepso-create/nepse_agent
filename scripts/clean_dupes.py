from database import db

with db.get_conn() as conn:
    dupes = conn.execute("""
        SELECT symbol, date, COUNT(*) as n
        FROM ohlc
        GROUP BY symbol, date
        HAVING n > 1
    """).fetchall()

    print(f'Duplicate (symbol, date) pairs: {len(dupes)}')

    total_removed = 0
    for row in dupes:
        sym = row[0]
        date = row[1]
        ids = conn.execute(
            "SELECT rowid FROM ohlc WHERE symbol = ? AND date = ? ORDER BY rowid",
            (sym, date),
        ).fetchall()
        delete_ids = [i[0] for i in ids[1:]]
        for did in delete_ids:
            conn.execute("DELETE FROM ohlc WHERE rowid = ?", (did,))
            total_removed += 1

    print(f'Removed {total_removed} duplicate rows')
    total = conn.execute("SELECT COUNT(*) FROM ohlc").fetchone()[0]
    print(f'Remaining ohlc rows: {total}')