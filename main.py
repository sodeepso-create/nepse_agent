"""
CLI entry point for the NEPSE analysis agent.

Usage:
    python main.py init-db
    python main.py collect [--dry-run] [--symbol NABIL] [--history]
    python main.py analyze SYMBOL [--strategy default|conservative]
    python main.py analyze-all
    python main.py backtest SYMBOL [--strategy default|conservative]
    python main.py paper-trade
    python main.py status
    python main.py schedule
    python main.py research
    python main.py ui
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python main.py` from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tabulate import tabulate

from analysis import indicators as ind
from analysis.scoring_engine import score
from analysis.research import build_all_digests, build_market_digest, build_symbol_digest
from backtest.backtester import run_backtest
from collectors.nepse_price_collector import NepsePriceCollector
from collectors.news_collector import NewsCollector
from config import settings
from database import db
from logging_config import get_logger
from paper_trading.paper_trader import run_paper_trading_pass
from strategy.rules import STRATEGIES
from alerts.runner import run_alerts
logger = get_logger(__name__)


def cmd_init_db(_args):
    db.init_db()
    cash = settings.PAPER_STARTING_CAPITAL
    db.record_paper_equity(cash, cash, note="initial")
    print(f"Database initialized at {settings.DB_PATH}")


def cmd_collect(args):
    price = NepsePriceCollector()
    news = NewsCollector()

    if args.history or args.symbol:
        symbols = [args.symbol.upper()] if args.symbol else settings.WATCHLIST
        print(f"Fetching history for: {', '.join(symbols)}")
        try:
            price.collect_watchlist_history(symbols, dry_run=args.dry_run)
        except Exception as e:
            logger.error("History collection failed: %s", e)
    else:
        try:
            price.collect_today_prices(dry_run=args.dry_run, symbol=args.symbol)
        except Exception as e:
            logger.error("Live price collection failed: %s", e)
        # Also refresh history for watchlist so analysis has enough bars
        try:
            price.collect_watchlist_history(settings.WATCHLIST, dry_run=args.dry_run)
        except Exception as e:
            logger.error("Watchlist history failed: %s", e)

    try:
        news.collect_all(dry_run=args.dry_run)
    except Exception as e:
        logger.error("News collection failed: %s", e)

    if not args.dry_run:
        print("Collection finished. Symbols with data:")
        for row in db.list_symbols_with_data():
            print(f"  {row['symbol']}: {row['n']} bars (last {row['last_date']})")


def cmd_analyze(args):
    symbol = args.symbol.upper()
    rows = db.get_ohlc(symbol, limit_days=250)
    if not rows:
        print(f"No OHLC for {symbol}. Run: python main.py collect --history --symbol {symbol}")
        return
    computed = ind.compute_all(rows)
    if computed is None:
        print(f"Not enough history for {symbol} (have {len(rows)} days, need 30+).")
        return
    news = db.get_recent_news(symbol, limit=15)
    market_r = db.get_latest_research("MARKET")
    sym_r = db.get_latest_research(symbol)
    research = {
        "market": (market_r or {}).get("payload") or {},
        "symbol": (sym_r or {}).get("payload") or {},
    }
    # Refresh digests if missing so first analyze still benefits from news in DB
    if not research["market"] or not research["symbol"]:
        try:
            research["market"] = build_market_digest()
            research["symbol"] = build_symbol_digest(symbol)
        except Exception:
            pass
    strategy_fn = STRATEGIES.get(args.strategy, STRATEGIES["default"])
    # strategies accept news_items; pass research via score for default path
    if args.strategy == "default":
        result = score(computed, news_items=news, research=research)
    else:
        result = strategy_fn(computed, news_items=news)
    db.save_score(
        symbol,
        result["as_of_date"],
        computed,
        result["composite_score"],
        result["recommendation"],
        result["reasons"],
    )
    print(f"\n{symbol} — {result['as_of_date']}  [{args.strategy}]")
    print(
        tabulate(
            [
                ["Price", computed["price"]],
                ["Trend", computed["trend"]],
                ["RSI", computed["rsi"]],
                ["Stochastic %K", computed.get("stochastic_k")],
                ["ATR", computed.get("atr")],
                ["MACD signal", computed["macd_signal"]],
                ["Price vs EMA20", computed["price_vs_ema20"]],
                ["Price vs EMA50", computed["price_vs_ema50"]],
                ["Volume vs avg", computed["volume_vs_avg"]],
                ["Support", computed["support"]],
                ["Resistance", computed["resistance"]],
                ["Composite score", result["composite_score"]],
                ["Recommendation", result["recommendation"]],
            ]
        )
    )
    print("\nReasons:")
    for r in result["reasons"]:
        print(f"  - {r}")
    if result.get("research_summary"):
        print(f"\nResearch: {result['research_summary']}")


def cmd_analyze_all(_args):
    symbols = [r["symbol"] for r in db.list_symbols_with_data()] or settings.WATCHLIST
    rows_out = []
    for sym in symbols:
        ohlc = db.get_ohlc(sym, limit_days=250)
        computed = ind.compute_all(ohlc) if ohlc else None
        if not computed:
            rows_out.append([sym, "-", "-", "SKIP", "insufficient data"])
            continue
        result = score(computed, news_items=db.get_recent_news(sym, limit=3))
        db.save_score(
            sym,
            result["as_of_date"],
            computed,
            result["composite_score"],
            result["recommendation"],
            result["reasons"],
        )
        rows_out.append(
            [sym, computed["price"], result["composite_score"], result["recommendation"], computed["trend"]]
        )
    print(tabulate(rows_out, headers=["Symbol", "Price", "Score", "Rec", "Trend"]))


def cmd_backtest(args):
    result = run_backtest(args.symbol.upper(), strategy_name=args.strategy)
    if result is None:
        print("Not enough historical data to backtest yet. Run collect --history first.")
        return
    print(f"\nBacktest — {args.symbol.upper()} [{args.strategy}]")
    print(
        tabulate(
            [
                ["Total trades", result["total_trades"]],
                ["Win rate", f"{result['win_rate_percent']}%"],
                ["Total return", f"{result['total_return_percent']}%"],
                ["Max drawdown", f"{result['max_drawdown_percent']}%"],
                ["Final capital", result["final_capital"]],
                ["Period", f"{result['start_date']} → {result['end_date']}"],
            ]
        )
    )


def cmd_paper_trade(_args):
    results = run_paper_trading_pass()
    for r in results:
        extra = f" @ {r['price']}" if r.get("price") else ""
        err = f" ({r['error']})" if r.get("error") else ""
        print(f"{r['symbol']}: {r['recommendation']} (score {r['composite_score']}){extra}{err}")
    cash, equity = db.paper_cash_and_equity()
    print(f"\nPaper cash: {cash:,.2f}  |  Equity: {equity:,.2f}")
    open_trades = db.get_open_paper_trades()
    if open_trades:
        print("\nOpen positions:")
        print(
            tabulate(
                [
                    [t["symbol"], t["action"], t["quantity"], t["entry_price"], t["stop_loss"], t["target"]]
                    for t in open_trades
                ],
                headers=["Symbol", "Side", "Qty", "Entry", "Stop", "Target"],
            )
        )


def cmd_status(_args):
    print(f"DB: {settings.DB_PATH}")
    print(f"Watchlist: {', '.join(settings.WATCHLIST)}")
    print("\nSymbols with OHLC:")
    data = db.list_symbols_with_data()
    if not data:
        print("  (none — run collect --history)")
    else:
        print(tabulate([[r["symbol"], r["n"], r["last_date"]] for r in data],
                       headers=["Symbol", "Bars", "Last date"]))
    scores = db.get_latest_scores()
    if scores:
        print("\nLatest scores:")
        print(
            tabulate(
                [
                    [s["symbol"], s["composite_score"], s["recommendation"], s["trend"], s["as_of_date"]]
                    for s in scores
                ],
                headers=["Symbol", "Score", "Rec", "Trend", "As of"],
            )
        )
    cash, equity = db.paper_cash_and_equity()
    print(f"\nPaper cash: {cash:,.2f}  |  Equity: {equity:,.2f}")


def cmd_schedule(_args):
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler()

    def job():
        cmd_collect(argparse.Namespace(dry_run=False, symbol=None, history=False))
        cmd_paper_trade(argparse.Namespace())

    scheduler.add_job(job, "interval", minutes=settings.COLLECTION_INTERVAL_MINUTES)
    print(f"Running every {settings.COLLECTION_INTERVAL_MINUTES} minutes. Ctrl+C to stop.")
    job()
    scheduler.start()



def cmd_research(_args):
    """Collect is separate; this builds digests from whatever news is in the DB,
    and optionally triggers a fresh news+web collect first."""
    print("Building research digests from stored news (run collect first for fresh web coverage)...")
    digests = build_all_digests()
    m = digests["market"]
    print(f"\nMARKET — {m.get('summary')}")
    print(f"  Items: {m.get('item_count')}  Sentiment: {m.get('avg_sentiment')}  Tone: {m.get('tone')}")
    if m.get("themes"):
        print("  Themes:", ", ".join(f"{t['theme']}({t['mentions']})" for t in m["themes"][:5]))
    if m.get("bullish_headlines"):
        print("  Constructive headlines:")
        for h in m["bullish_headlines"][:5]:
            print(f"    + {h['headline'][:100]}")
    if m.get("bearish_headlines"):
        print("  Cautious headlines:")
        for h in m["bearish_headlines"][:5]:
            print(f"    - {h['headline'][:100]}")
    print("\nPer-symbol digests:")
    for sym, d in sorted(digests["symbols"].items()):
        print(f"  {sym}: {d.get('summary')}")

def cmd_alerts(_args):
    run_alerts()
def cmd_ui(_args):
    import subprocess

    ui_path = Path(__file__).parent / "ui" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ui_path)], check=False)


def main():
    parser = argparse.ArgumentParser(description="NEPSE analysis & paper-trading agent")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create SQLite schema")

    p_collect = sub.add_parser("collect", help="Fetch prices and news")
    p_collect.add_argument("--dry-run", action="store_true")
    p_collect.add_argument("--symbol", default=None, help="Limit to one ticker")
    p_collect.add_argument(
        "--history",
        action="store_true",
        help="Fetch Merolagani historical OHLC for watchlist (or --symbol)",
    )

    p_analyze = sub.add_parser("analyze", help="Score one symbol")
    p_analyze.add_argument("symbol")
    p_analyze.add_argument("--strategy", default="default", choices=list(STRATEGIES))

    sub.add_parser("analyze-all", help="Score all symbols that have data")

    p_bt = sub.add_parser("backtest", help="Backtest strategy on stored history")
    p_bt.add_argument("symbol")
    p_bt.add_argument("--strategy", default="default", choices=list(STRATEGIES))

    sub.add_parser("paper-trade", help="Run one paper-trading pass")
    sub.add_parser("status", help="Show DB / scores / paper portfolio")
    sub.add_parser("schedule", help="Loop collect + paper-trade")
    sub.add_parser("research", help="Build market/symbol research digests from news + web")
    sub.add_parser("alerts", help="Send email alerts for corporate actions on your holdings")
    sub.add_parser("ui", help="Launch Streamlit dashboard")

    args = parser.parse_args()
    dispatch = { "alerts": cmd_alerts,
        "init-db": cmd_init_db,
        "collect": cmd_collect,
        "analyze": cmd_analyze,
        "analyze-all": cmd_analyze_all,
        "backtest": cmd_backtest,
        "paper-trade": cmd_paper_trade,
        "status": cmd_status,
        "research": cmd_research,
        "schedule": cmd_schedule,
        "ui": cmd_ui,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
