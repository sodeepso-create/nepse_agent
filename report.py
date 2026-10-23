#!/usr/bin/env python
r"""
report.py - Read-only NEPSE paper-trading report.
...

Place in: D:\MyAi_Assistant\nepse_agent\report.py

Run (from project root, venv activated):
    python report.py                 # activity since last run
    python report.py --all           # full trade history
    python report.py --schema        # dump DB table columns (for verification)
    python report.py --commentary    # optional: add LLM narrative

Safety:
    * Opens SQLite with ?mode=ro  -> DB is read-only at the engine level.
    * Never writes to the DB.
    * Only writes to  reports\  (last_report.md, history.jsonl, _last_report.json)
"""
from __future__ import annotations
import argparse, json, os, sqlite3, sys
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "data", "nepse_agent.db")
REPORT_DIR = os.path.join(ROOT, "reports")
STATE_FILE = os.path.join(REPORT_DIR, "_last_report.json")
HISTORY_FILE = os.path.join(REPORT_DIR, "history.jsonl")
LAST_MD = os.path.join(REPORT_DIR, "last_report.md")
STARTING_CAPITAL = 100000.0


# ---------------------------------------------------------------- helpers
def ro_conn() -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        sys.exit(f"[x] DB not found: {DB_PATH}")
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def table_cols(conn, table):
    try:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    except sqlite3.Error:
        return []


def pick(cols, *names):
    for n in names:
        if n in cols:
            return n
    return None


def money(n):
    return f"{n:,.2f}"


def pct(n):
    return f"{n:+.2f}%"


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_max_trade_id": 0, "last_report_at": None}


def save_state(state):
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------- schema
def dump_schema(conn):
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for t in tables:
        print(f"\n{t}:")
        for c in table_cols(conn, t):
            print(f"  - {c}")


# ---------------------------------------------------------------- data
def load_trades(conn):
    tcols = table_cols(conn, "paper_trades")
    if not tcols:
        return []
    c = {
        "id":          pick(tcols, "id", "trade_id"),
        "symbol":      pick(tcols, "symbol", "ticker"),
        "side":        pick(tcols, "side", "action", "type", "trade_type", "direction"),
        "qty":         pick(tcols, "qty", "quantity", "shares", "units"),
        "entry_price": pick(tcols, "entry_price", "price", "buy_price", "open_price"),
        "entry_date":  pick(tcols, "entry_date", "date", "trade_date", "opened_at", "created_at"),
        "exit_price":  pick(tcols, "exit_price", "sell_price", "close_price"),
        "exit_date":   pick(tcols, "exit_date", "closed_at"),
        "status":      pick(tcols, "status", "state"),
        "pnl":         pick(tcols, "pnl", "profit_loss", "realized_pnl", "profit", "return"),
    }
    sel = list(dict.fromkeys(v for v in c.values() if v))
    if not sel:
        return []
    rows = conn.execute(f"SELECT {', '.join(sel)} FROM paper_trades").fetchall()
    idx = {name: i for i, name in enumerate(sel)}
    out = []
    for r in rows:
        out.append({k: (r[idx[v]] if v and v in idx else None) for k, v in c.items()})
    return out


def is_open(t):
    if t.get("status") is not None:
        return str(t["status"]).lower() in ("open", "opened", "active", "1", "true")
    return t.get("exit_price") is None and t.get("exit_date") is None


def norm_side(s):
    if s is None:
        return None
    s = str(s).lower()
    if s in ("buy", "b", "long", "entry"):
        return "buy"
    if s in ("sell", "s", "short", "exit"):
        return "sell"
    return s


def latest_prices(conn):
    ocols = table_cols(conn, "ohlc")
    if not ocols:
        return {}
    sym   = pick(ocols, "symbol", "ticker")
    dt    = pick(ocols, "date", "trade_date", "timestamp")
    close = pick(ocols, "close", "close_price", "last", "ltp")
    if not (sym and dt and close):
        return {}
    rows = conn.execute(f"""
        SELECT o.{sym}, o.{close}
        FROM ohlc o
        JOIN (SELECT {sym} AS s, MAX({dt}) AS d FROM ohlc GROUP BY {sym}) m
          ON o.{sym} = m.s AND o.{dt} = m.d
    """).fetchall()
    return {r[0]: float(r[1]) for r in rows if r[1] is not None}


def cash_and_equity(conn):
    ecols = table_cols(conn, "paper_equity")
    if not ecols:
        return None, None
    cash = pick(ecols, "cash", "cash_balance")
    eq   = pick(ecols, "equity", "total_equity", "portfolio_value")
    dt   = pick(ecols, "date", "timestamp", "created_at", "id")
    if not cash:
        return None, None
    order = dt or "rowid"
    sel = f"SELECT {cash}" + (f", {eq}" if eq else "") + \
          f" FROM paper_equity ORDER BY {order} DESC LIMIT 1"
    row = conn.execute(sel).fetchone()
    if not row:
        return None, None
    return float(row[0]), (float(row[1]) if eq else None)


def realized_pnl(t):
    if t.get("pnl") is not None:
        try:
            return float(t["pnl"])
        except (TypeError, ValueError):
            pass
    try:
        ep  = float(t.get("entry_price") or 0)
        xp  = float(t.get("exit_price") or 0)
        qty = float(t.get("qty") or 0)
        return (xp - ep) * qty
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------- report
def build_report(conn, since_id, all_flag):
    trades = load_trades(conn)
    prices = latest_prices(conn)
    cash, _ = cash_and_equity(conn)

    # ---- new activity
    new = trades if all_flag else [t for t in trades if (t.get("id") or 0) > since_id]
    buys, sells = [], []
    for t in new:
        side = norm_side(t.get("side"))
        if side == "buy" or (side is None and is_open(t)):
            buys.append(t)
        elif side == "sell" or (side is None and not is_open(t)):
            sells.append(t)
    # closed-before-last-run shouldn't show up as 'sold' unless side says so
    if not all_flag:
        sells = [t for t in sells if (t.get("id") or 0) > since_id or norm_side(t.get("side")) == "sell"]

    # ---- open positions (aggregate per symbol)
    open_pos = {}
    for t in trades:
        if not is_open(t):
            continue
        sym = t.get("symbol")
        if not sym:
            continue
        qty = float(t.get("qty") or 0)
        ep  = float(t.get("entry_price") or 0)
        p = open_pos.setdefault(sym, {"qty": 0.0, "cost": 0.0})
        p["qty"]  += qty
        p["cost"] += qty * ep

    positions = []
    for sym, p in sorted(open_pos.items()):
        qty = p["qty"]
        if qty <= 0:
            continue
        avg   = p["cost"] / qty
        cur   = prices.get(sym, avg)
        value = qty * cur
        upl   = value - p["cost"]
        upct  = (upl / p["cost"] * 100.0) if p["cost"] else 0.0
        positions.append({"symbol": sym, "qty": qty, "avg": avg,
                          "current": cur, "value": value,
                          "unrealized": upl, "unrealized_pct": upct})

    market_value = sum(p["value"] for p in positions)
    open_cost    = sum(p["avg"] * p["qty"] for p in positions)

    # ---- cash fallback if paper_equity missing
    if cash is None:
        buys_cost  = sum((float(t.get("qty") or 0) * float(t.get("entry_price") or 0))
                         for t in trades if norm_side(t.get("side")) == "buy" or is_open(t))
        sells_proc = sum((float(t.get("qty") or 0) * float(t.get("exit_price") or 0))
                         for t in trades if norm_side(t.get("side")) == "sell" or not is_open(t))
        cash = STARTING_CAPITAL - buys_cost + sells_proc

    equity = cash + market_value

    # ---- P/L
    realized_all = sum(realized_pnl(t) for t in trades if not is_open(t))
    realized_new = sum(realized_pnl(t) for t in sells)
    unrealized   = sum(p["unrealized"] for p in positions)
    total_pnl    = realized_all + unrealized
    total_ret    = (equity - STARTING_CAPITAL) / STARTING_CAPITAL * 100.0

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "buys": buys, "sells": sells,
        "positions": positions,
        "cash": cash, "market_value": market_value,
        "open_cost": open_cost, "equity": equity,
        "starting_capital": STARTING_CAPITAL,
        "realized_all": realized_all,
        "realized_new": realized_new,
        "unrealized": unrealized,
        "total_pnl": total_pnl,
        "total_return_pct": total_ret,
        "since_id": since_id,
    }


def render_text(r):
    L = []
    a = L.append
    a("=" * 62)
    a(f" NEPSE PAPER PORTFOLIO REPORT — {r['generated_at']}")
    a("=" * 62)

    a("\n[ BOUGHT since last report ]")
    if not r["buys"]:
        a("  (none)")
    for t in r["buys"]:
        qty = float(t.get("qty") or 0)
        ep  = float(t.get("entry_price") or 0)
        a(f"  {t.get('symbol','?'):<8} x {qty:>6g} @ {money(ep):>10}  = {money(qty*ep):>12}   [#{t.get('id')}]")

    a("\n[ SOLD since last report ]")
    if not r["sells"]:
        a("  (none)")
    for t in r["sells"]:
        qty = float(t.get("qty") or 0)
        xp  = float(t.get("exit_price") or 0)
        a(f"  {t.get('symbol','?'):<8} x {qty:>6g} @ {money(xp):>10}  = {money(qty*xp):>12}   P/L {money(realized_pnl(t)):>10}   [#{t.get('id')}]")

    a("\n[ OPEN POSITIONS ]")
    if not r["positions"]:
        a("  (none)")
    else:
        a(f"  {'SYM':<8}{'QTY':>8}{'ENTRY':>11}{'CURRENT':>11}{'VALUE':>13}{'UNREALIZED':>14}{'%':>9}")
        for p in r["positions"]:
            a(f"  {p['symbol']:<8}{p['qty']:>8g}{p['avg']:>11,.2f}{p['current']:>11,.2f}"
              f"{p['value']:>13,.2f}{p['unrealized']:>14,.2f}{p['unrealized_pct']:>8.2f}%")

    a("\n[ PORTFOLIO ]")
    a(f"  Cash              : {money(r['cash']):>14}")
    a(f"  Open market value : {money(r['market_value']):>14}")
    a(f"  Equity            : {money(r['equity']):>14}")
    a(f"  Starting capital  : {money(r['starting_capital']):>14}")
    a(f"  Total return      : {pct(r['total_return_pct']):>14}   ({money(r['equity'] - r['starting_capital'])})")

    a("\n[ P/L BREAKDOWN ]")
    a(f"  Realized (all-time) : {money(r['realized_all']):>14}")
    a(f"  Realized (new)      : {money(r['realized_new']):>14}")
    a(f"  Unrealized          : {money(r['unrealized']):>14}")
    a(f"  TOTAL P/L           : {money(r['total_pnl']):>14}")
    a("")
    return "\n".join(L)


def save_history(r):
    os.makedirs(REPORT_DIR, exist_ok=True)
    snap = {k: v for k, v in r.items() if k not in ("buys", "sells", "positions")}
    snap["open_symbols"] = [p["symbol"] for p in r["positions"]]
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(snap) + "\n")


def write_md(r, text):
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(LAST_MD, "w", encoding="utf-8") as f:
        f.write("```\n" + text + "\n```\n")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Read-only NEPSE paper-trading report")
    ap.add_argument("--all", action="store_true", help="show full history, ignore last-run marker")
    ap.add_argument("--schema", action="store_true", help="dump DB table columns and exit")
    ap.add_argument("--commentary", action="store_true", help="(optional) call LLM for narrative")
    args = ap.parse_args()

    conn = ro_conn()
    if args.schema:
        dump_schema(conn)
        return

    state = load_state()
    since_id = 0 if args.all else int(state.get("last_max_trade_id", 0) or 0)

    # reset detection (e.g. after reset.py)
    trades = load_trades(conn)
    max_id = max((int(t.get("id") or 0) for t in trades), default=0)
    if max_id < since_id:
        print("[i] Trades were reset — showing full history this run.")
        since_id = 0

    report = build_report(conn, since_id, args.all)
    text = render_text(report)
    print(text)

    save_history(report)
    write_md(report, text)

    save_state({
        "last_max_trade_id": max_id,
        "last_report_at": report["generated_at"],
    })

    print(f"Saved -> {LAST_MD}")
    print(f"History -> {HISTORY_FILE}")

    if args.commentary:
        try:
            from llm_commentary import add_commentary  # optional, create later
            print("\n" + add_commentary(report))
        except Exception as e:
            print(f"\n[i] Commentary skipped: {e}")


if __name__ == "__main__":
    main()