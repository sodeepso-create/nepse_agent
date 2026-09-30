"""Append current paper portfolio to paper_history.csv. Run weekly."""
import csv
from datetime import date
from pathlib import Path

from database import db
from config import settings

CSV = Path("paper_history.csv")
cash, equity = db.paper_cash_and_equity()
open_trades = db.get_open_paper_trades()
starting = settings.PAPER_STARTING_CAPITAL
pnl_pct = (equity - starting) / starting * 100

today = date.today().isoformat()
row = [today, f"{cash:.2f}", f"{equity:.2f}", f"{pnl_pct:.2f}", len(open_trades)]

write_header = not CSV.exists()
with CSV.open("a", newline="") as f:
    w = csv.writer(f)
    if write_header:
        w.writerow(["date", "cash", "equity", "pnl_pct", "open_positions"])
    w.writerow(row)

print(f"Logged: {today} | cash {cash:,.0f} | equity {equity:,.0f} | "
      f"pnl {pnl_pct:+.2f}% | open {len(open_trades)}")