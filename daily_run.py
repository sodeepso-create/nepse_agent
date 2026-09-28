"""Daily pipeline: collect → research → paper-trade → alerts.

Runs twice on trading days:
  - Morning window: 11:00-11:45 AM (news + research only, no trades)
  - Afternoon window: 3:30-3:59 PM (post-close, full pipeline with trades)

Trades use today's official close, not stale data.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_LOG_DIR = Path(__file__).resolve().parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FILE = _LOG_DIR / "daily_run.log"

# Only redirect when run via pythonw.exe (no console).
# Manual runs (python daily_run.py) still print to terminal.
if sys.stdout is None or sys.stderr is None:
    _LOG_HANDLE = open(_LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = _LOG_HANDLE
    sys.stderr = _LOG_HANDLE

NEPSE_2026_HOLIDAYS = {
    "2026-01-11": "Prithvi Jayanti",
    "2026-01-15": "Maghe Sankranti",
    "2026-01-19": "Sonam Lhosar",
    "2026-01-30": "Martyrs' Day",
    "2026-02-15": "Maha Shivaratri",
    "2026-02-18": "Gyalpo Lhosar",
    "2026-02-19": "Prajatantra Diwas",
    "2026-03-02": "Fagu Purnima (Holi)",
    "2026-03-04": "Election Holiday",
    "2026-03-05": "Election Holiday",
    "2026-03-06": "Election Holiday",
    "2026-03-08": "Nari Dibas",
    "2026-03-18": "Ghode Jatra",
    "2026-03-27": "Ram Navami",
    "2026-04-14": "Nepali New Year",
    "2026-05-01": "Buddha Jayanti",
    "2026-05-29": "Republic Day",
    "2026-08-28": "Janai Purnima",
    "2026-09-04": "Shree Krishna Janmashtami",
    "2026-09-18": "Constitution Day",
    "2026-10-11": "Ghatasthapana (Dashain)",
    "2026-10-18": "Maha Ashtami",
    "2026-10-19": "Maha Navami",
    "2026-10-20": "Vijaya Dashami",
    "2026-11-08": "Laxmi Puja",
    "2026-11-09": "Gobhardan Pujan",
    "2026-11-10": "Bhai Tika",
    "2026-11-15": "Chhath Parwa",
    "2026-12-25": "Christmas Day",
}

STATE_FILE = Path(__file__).resolve().parent / ".daily_run_state.json"

# (hour, minute_start, minute_end) — local NPT
SLOTS = {
    "morning": (11, 0, 45),      # 11:00 - 11:45 AM (news only)
    "afternoon": (15, 30, 59),   # 3:30 - 3:59 PM (post-close, with trades)
}


def _is_trading_day() -> tuple[bool, str]:
    today = date.today()
    today_iso = today.isoformat()
    if today.weekday() in (5, 6):
        return False, f"Weekend ({today.strftime('%A')})"
    if today_iso in NEPSE_2026_HOLIDAYS:
        return False, f"Holiday: {NEPSE_2026_HOLIDAYS[today_iso]}"
    return True, "Trading day"


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state))


def _current_slot() -> str | None:
    now = datetime.now()
    for name, (hr, m_start, m_end) in SLOTS.items():
        if now.hour == hr and m_start <= now.minute <= m_end:
            return name
    return None


def _slot_already_ran(slot: str) -> bool:
    state = _load_state()
    return state.get(date.today().isoformat(), {}).get(slot) is True


def _mark_slot_done(slot: str):
    state = _load_state()
    today = date.today().isoformat()
    state.setdefault(today, {})[slot] = True
    for k in list(state.keys()):
        if k != today:
            state.pop(k, None)
    _save_state(state)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    is_trading, reason = _is_trading_day()
    if not is_trading and not args.force:
        print(f"=== Skipping run: {reason} ===")
        return

    slot = _current_slot()
    if slot is None and not args.force:
        now = datetime.now().strftime("%H:%M")
        print(f"=== Skipping run: outside time slots ({now}) ===")
        return

    if slot and _slot_already_ran(slot) and not args.force:
        print(f"=== Skipping run: {slot} slot already ran today ===")
        return

    if slot:
        _mark_slot_done(slot)

    tag = f"{reason} | slot={slot or 'forced'}"
    print(f"\n=== NEPSE run started at {datetime.now().isoformat(timespec='seconds')} ({tag}) ===")

    print("\n[1/4] Collecting prices and news...")
    try:
        from main import cmd_collect
        cmd_collect(argparse.Namespace(dry_run=False, symbol=args.symbol, history=True))
    except Exception as e:
        print(f"  Collect failed: {e}")

    print("\n[2/4] Building research digests...")
    try:
        from main import cmd_research
        cmd_research(argparse.Namespace())
    except Exception as e:
        print(f"  Research failed: {e}")

    if slot == "morning":
        print("\n[3/4] Skipping paper trading (morning slot — news only)")
    else:
        print("\n[3/4] Running paper trading...")
        try:
            from main import cmd_paper_trade
            cmd_paper_trade(argparse.Namespace())
        except Exception as e:
            print(f"  Paper trade failed: {e}")

    print("\n[4/4] Sending alerts...")
    try:
        from alerts.runner import run_alerts
        run_alerts()
    except Exception as e:
        print(f"  Alerts failed: {e}")

    print(f"\n=== Done at {datetime.now().isoformat(timespec='seconds')} ===")


if __name__ == "__main__":
    main()