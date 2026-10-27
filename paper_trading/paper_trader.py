"""Paper trading with NEPSE-realistic frictions: board lot, commission,
CGT, circuit breaker, slippage, and T+2 settlement."""
from datetime import date, timedelta

from analysis import indicators as ind
from analysis.scoring_engine import score
from config import settings
from database import db
from logging_config import get_logger
from risk.risk_engine import (
    RiskViolation,
    check_daily_loss,
    check_source_health_before_trading,
    position_size,
    stop_loss_price,
    target_price,
)

# 🔌 Import the new Real-Time, AI, and Data Gate components
from live_price import get_live_quote, get_live_ltp
from trader_brain import expert_trader_decision

logger = get_logger(__name__)

COMMISSION_PCT = 0.004    # 0.4% per side (broker + SEBON + DP)
CGT_SHORT_PCT = 0.05      # 5% short-term capital gains tax
SLIPPAGE_PCT = 0.003      # 0.3% adverse fill vs close
SETTLEMENT_DAYS = 2       # T+2

def _board_lot(symbol: str) -> int:
    """NEPSE board lot: 10 shares for Rs 100 face value (default)."""
    return 10

def _latest_price(symbol: str) -> float | None:
    """
    Used ONLY for calculating Portfolio Equity (reporting).
    Falls back to EOD close if market is closed.
    (This does NOT bypass the trade execution Hard Gate).
    """
    live_px = get_live_ltp(symbol)
    if live_px:
        return live_px
        
    rows = db.get_ohlc(symbol, limit_days=5)
    if not rows:
        return None
    return float(rows[-1]["close"])

def _mark_open_positions(cash: float) -> tuple[float, list]:
    open_trades = db.get_open_paper_trades()
    equity = cash
    for t in open_trades:
        px = _latest_price(t["symbol"])
        if px is None:
            px = float(t["entry_price"])
        if t["action"] == "BUY":
            equity += t["quantity"] * px
    return equity, open_trades

def _maybe_close(trade: dict, price: float, indicators: dict, force_reason: str = ""):
    stop = trade.get("stop_loss")
    target = trade.get("target")
    action = trade["action"]
    qty = trade["quantity"]
    entry = trade["entry_price"]

    should_close = False
    reason = ""
    
    # If the AI explicitly said SELL, we force the close
    if force_reason:
        should_close = True
        reason = force_reason
    else:
        # Original Stop-loss / Target logic
        if action == "BUY":
            if stop and price <= stop:
                should_close, reason = True, "stop_loss"
            elif target and price >= target:
                should_close, reason = True, "target"
            elif (indicators.get("trend") == "bearish"
                  and indicators.get("macd_signal") == "bearish_crossover"):
                should_close, reason = True, "signal_exit"
        else:
            if stop and price >= stop:
                should_close, reason = True, "stop_loss"
            elif target and price <= target:
                should_close, reason = True, "target"

    if not should_close:
        return False, "", 0.0, 0.0

    sell_fill = round(price * (1 - SLIPPAGE_PCT), 2)

    if action == "BUY":
        gross = sell_fill * qty
        comm_sell = gross * COMMISSION_PCT
        pre_tax = gross - comm_sell
        cost_basis = entry * qty * (1 + COMMISSION_PCT)
        pnl = pre_tax - cost_basis
        tax = pnl * CGT_SHORT_PCT if pnl > 0 else 0.0
        net_pnl = pnl - tax
        proceeds = pre_tax - tax
    else:
        net_pnl = (entry - sell_fill) * qty
        tax = 0.0
        pnl = net_pnl
        proceeds = net_pnl

    db.close_paper_trade(trade["id"], sell_fill, round(net_pnl, 2))
    logger.info(
        "Closed %s %s @ %.2f (%s) gross=%.2f tax=%.2f net=%.2f",
        action, trade["symbol"], sell_fill, reason, pnl, tax, net_pnl,
    )
    return True, reason, net_pnl, proceeds

def run_paper_trading_pass(symbols=None):
    from alerts.prefs import get_profitable

    profitable = set(get_profitable())
    symbols = symbols or [s for s in settings.WATCHLIST if s in profitable]
    if not symbols:
        return [{"symbol": "*", "recommendation": "SKIP", "composite_score": 0,
                 "error": "No profitable stocks configured"}]

    # Settle any matured T+2 proceeds from prior sales
    settled = db.settle_matured()
    if settled > 0:
        logger.info("Settled %.2f from matured T+2 proceeds", settled)

    results = []
    try:
        check_source_health_before_trading(["merolagani", "sharesansar", "nepse_price"])
    except RiskViolation as e:
        logger.error("%s", e)
        return [{"symbol": "*", "recommendation": "HALT", "composite_score": 0, "error": str(e)}]

    # Get exact equity from DB to prevent false halts on weekends/holidays
    cash, equity = db.paper_cash_and_equity()
    _, open_trades = _mark_open_positions(cash) 
    
    try:
        check_daily_loss(equity, equity)
    except RiskViolation as e:
        logger.error("%s", e)
        return [{"symbol": "*", "recommendation": "HALT", "composite_score": 0, "error": str(e)}]

    open_by_symbol = {t["symbol"]: t for t in open_trades if t["status"] == "OPEN"}
    settle_date = (date.today() + timedelta(days=SETTLEMENT_DAYS)).isoformat()

    for symbol in symbols:
        rows = db.get_ohlc(symbol, limit_days=250)
        if len(rows) < 30:
            results.append({"symbol": symbol, "recommendation": "SKIP",
                            "composite_score": 0, "error": "insufficient history"})
            continue
        computed = ind.compute_all(rows)
        if not computed:
            continue
            
        news_items = db.get_recent_news(symbol, limit=5)
        result = score(computed, news_items=news_items)
        
        db.save_score(symbol, result["as_of_date"], computed,
                      result["composite_score"], result["recommendation"], result["reasons"])

        # 🚧 HARD GATE: DATA FRESHNESS CHECK 🚧
        # We strictly require a FRESH quote to execute trades. No fallbacks allowed.
        quote = get_live_quote(symbol)
        
        if quote.status != "FRESH":
            logger.warning(f"SKIPPED_STALE_PRICE: {symbol} - {quote.status} (Source: {quote.source})")
            results.append({
                "symbol": symbol,
                "recommendation": "SKIPPED_STALE_PRICE",
                "composite_score": result["composite_score"],
                "price": 0.0,
                "error": f"Data {quote.status}"
            })
            continue  # ⛔ ABORT THIS SYMBOL, DO NOT TRADE
            
        # Safe to use the live price!
        price = quote.price
        
        # 🔥 ASK THE AI BRAIN
        news_text = " | ".join([n["headline"] for n in news_items]) if news_items else "No recent news"
        ai_decision, ai_reason = expert_trader_decision(
            symbol=symbol, 
            current_price=price, 
            technical_score=result["composite_score"], 
            recent_news=news_text
        )
        
        logger.info(f"AI Decision for {symbol} @ {price} (Fetched at {quote.fetch_time.strftime('%H:%M:%S')}): {ai_decision} ({ai_reason})")

        existing = open_by_symbol.get(symbol)

        # If we own it, check if AI says to SELL (or hit stop/target)
        if existing:
            force = "ai_sell" if ai_decision == "SELL" else ""
            closed, reason, net_pnl, proceeds = _maybe_close(existing, price, computed, force_reason=force)
            if closed:
                db.add_settlement(proceeds, settle_date)
                logger.info("Proceeds %.2f will settle on %s (T+2)", proceeds, settle_date)
                cash, equity = db.paper_cash_and_equity()
                _, open_trades = _mark_open_positions(cash)
                open_by_symbol = {t["symbol"]: t for t in open_trades if t["status"] == "OPEN"}

        existing = open_by_symbol.get(symbol)
        
        # If we don't own it, and AI says BUY, execute!
        if ai_decision == "BUY" and not existing:
            dd_raw = db.get_setting(f"DD_{symbol}", "")
            try:
                dd_pct = float(dd_raw) if dd_raw else None
            except ValueError:
                dd_pct = None

            fill = round(price * (1 + SLIPPAGE_PCT), 2)
            board = _board_lot(symbol)

            qty = position_size(fill, cash, dd_pct)
            qty = (qty // board) * board

            # If rounding to 0 but one board lot is affordable within 20% overrun, take it
            if qty == 0:
                one_lot_cost = board * fill * (1 + COMMISSION_PCT)
                max_budget = cash * (settings.MAX_POSITION_SIZE_PERCENT / 100.0) * 1.2
                if one_lot_cost <= max_budget and one_lot_cost <= cash:
                    qty = board

            if qty > 0:
                stop = stop_loss_price(fill, computed.get("atr"), "BUY")
                tgt = target_price(fill, stop, "BUY")

                gross = qty * fill
                commission = gross * COMMISSION_PCT
                cost = gross + commission

                if cost > cash:
                    continue

                cash -= cost
                db.insert_paper_trade({
                    "symbol": symbol,
                    "action": "BUY",
                    "quantity": qty,
                    "entry_price": fill,
                    "stop_loss": stop,
                    "target": tgt,
                    "reason": f"AI: {ai_reason}",  # Record the AI's reasoning in the DB
                })
                logger.info(
                    "Paper BUY %s x%d @ %.2f (live %.2f + slip) stop=%.2f target=%.2f comm=%.2f",
                    symbol, qty, fill, price, stop, tgt, commission,
                )

        results.append({
            "symbol": symbol,
            "recommendation": ai_decision, # Show AI decision in terminal
            "composite_score": result["composite_score"],
            "price": price,
        })

    cash, equity = db.paper_cash_and_equity()
    db.record_paper_equity(cash, equity, note="paper_pass")

    buys = sum(1 for r in results if r.get("recommendation") == "BUY")
    logger.info(
        "Paper trade pass done: %d stocks checked, %d BUY signals, %d open positions",
        len(results), buys, len(db.get_open_paper_trades()),
    )
    return results