from database import db

with db.get_conn() as conn:
    rows = conn.execute(
        "SELECT rowid, date, high, low, close FROM ohlc WHERE symbol='NABIL' AND date='2026-09-15'"
    ).fetchall()
    print(f'Rows for 2026-09-15: {len(rows)}')
    for r in rows:
        print(' rowid:', r[0], 'date:', r[1], 'H:', r[2], 'L:', r[3], 'C:', r[4])