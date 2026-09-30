"""Daily DB backup. Keeps last 14 days. Safe to run repeatedly."""
from datetime import date
from pathlib import Path
import shutil

from config import settings

BACKUP_DIR = Path(settings.DB_PATH).parent.parent / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

today = date.today().isoformat()
src = Path(settings.DB_PATH)
dst = BACKUP_DIR / f"nepse_agent_{today}.db"

if dst.exists():
    print(f"Backup already exists for {today}, skipping")
else:
    shutil.copy2(src, dst)
    print(f"Backed up to {dst}")
    backups = sorted(BACKUP_DIR.glob("nepse_agent_*.db"))
    for old in backups[:-14]:
        old.unlink()
        print(f"Removed old backup: {old.name}")