import sqlite3
from config import settings

c = sqlite3.connect(settings.DB_PATH)
n = c.execute("DELETE FROM sent_alerts WHERE url LIKE 'market-action:%'").rowcount
c.commit()
c.close()
print(f"Cleared {n} market-action markers")