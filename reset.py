import sqlite3
from config import settings

c = sqlite3.connect(settings.DB_PATH)
c.execute("DELETE FROM paper_trades")
c.execute("DELETE FROM paper_equity")
c.execute("INSERT INTO paper_equity (cash, equity, note) VALUES (100000, 100000, 'reset 100k')")
c.commit()
c.close()
print("reset done — capital: 100,000 NPR, 0 positions")