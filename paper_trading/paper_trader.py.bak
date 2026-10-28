"""Paper trading with NEPSE-realistic frictions..."""
from datetime import date, timedelta
from analysis import indicators as ind
from analysis.scoring_engine import score
from config import settings
from database import db
from logging_config import get_logger
from risk.risk_engine import (RiskViolation, check_daily_loss, check_source_health_before_trading, position_size, stop_loss_price, target_price)

from live_price import get_live_quote, get_live_ltp
from trader_brain import expert_trader_decision

logger = get_logger(__name__)

# --- REAL NEPSE FRICTIONS ---
COMMISSION_PCT = 0.0036    # Broker commission (0.36%)
SEBON_FEE_PCT = 0.00015    # SEBON fee (0.015%)
DP_FEE_PCT = 0.00015       # DP fee (0.015%)
TOTAL_BUY_FEE_PCT = COMMISSION_PCT + SEBON_FEE_PCT + DP_FEE_PCT  # 0.39%

CGT_SHORT_PCT = 0.075      # 7.5% for individuals < 365 days
SLIPPAGE_PCT = 0.003       # 0.3% simulated slippage
SETTLEMENT_DAYS = 2       
MAX_TRADES_PER_DAY = 2     # HARD LIMIT: Max 2 trades a day

def _board_lot(symbol: str) -> int: 
    return 10

def _latest_price(symbol: str) -> float | None:
    live_px = get_live_ltp(symbol)
    if live_px: return live_px
    rows = db.get_ohlc(symbol, limit_days=5)
    if not rows: return None
    return float(rows[-1]["close"])

def _mark_open_positions(cash: float) -> tuple[float, list]:
    open_trades = db.get_open_paper_trades()
    equity = cash
    for t in open_trades:
        px = _latest_price(t["symbol"]) or float(t["entry_price"])
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
    
    if force_reason: 
        should_close, reason = True, force_reason
    else:
        if action == "BUY":
            if stop and price <= stop: 
                should_close, reason = True, "stop_loss"
            elif target and price >= target: 
                should_close, reason = True, "target"
            elif (indicators.get("trend") == "bearish" and indicators.get("macd_signal") == "bearish_crossover"):
                should_close, reason = True, "signal_exit"
        else:
            if stop and price >= stop: 
                should_close, reason = True, "stop_loss"
            elif target and price <= target: 
                should_close, reason = True, "target"

    if not should_close: 
        return False, "", 0.0, 0.0

    # Simulate sell slippage
    sell_fill = round(price * (1 - SLIPPAGE_PCT), 2)
    
    if action == "BUY":
        gross = sell_fill * qty
        comm_sell = gross * TOTAL_BUY_FEE_PCT
        pre_tax = gross - comm_sell
        
        # Cost basis includes buy fees
        cost_basis = entry * qty * (1 + TOTAL_BUY_FEE_PCT)
        
        pnl = pre_tax - cost_basis
        
        # Real NEPSE Tax: 7.5% on profit
        tax = pnl * CGT_SHORT_PCT if pnl > 0 else 0.0
        net_pnl = pnl - tax
        proceeds = pre_tax - tax
    else:
        # Short selling logic (if you support it)
        net_pnl = (entry - sell_fill) * qty
        tax = 0.0
        pnl = net_pnl
        proceeds = net_pnl

    db.close_paper_trade(trade["id"], sell_fill, round(net_pnl, 2))
    logger.info(f"CLOSED {action} {trade['symbol']} @ {sell_fill} | Reason: {reason} | Net PnL: {net_pnl:.2f}")
    return True, reason, net_pnl, proceeds

def run_paper_trading_pass(symbols=None):
    from alerts.prefs import get_profitable
    profitable = set(get_profitable())
    symbols = symbols or [s for s in settings.WATCHLIST if s in profitable]
    if not symbols: 
        return [{"symbol": "*", "recommendation": "SKIP", "error": "No profitable stocks configured"}]

    # Check how many trades we've done today
    trades_today = db.get_trades_count_today() # We need to add this DB function
    if trades_today >= MAX_TRADES_PER_DAY:
        logger.warning(f"HALTED: Max daily trades ({MAX_TRADES_PER_DAY}) reached.")
        return [{"symbol": "*", "recommendation": "HALT", "error": "Max daily trades reached"}]

    settled = db.settle_matured()
    results = []
    
    try: 
        check_source_health_before_trading(["merolagani", "sharesansar", "nepse_price"])
    except RiskViolation as e: 
        return [{"symbol": "*", "recommendation": "HALT", "error": str(e)}]

    cash, equity = db.paper_cash_and_equity()
    _, open_trades = _mark_open_positions(cash) 
    
    try: 
        check_daily_loss(equity, equity)
    except RiskViolation as e: 
        return [{"symbol": "*", "recommendation": "HALT", "error": str(e)}]

    open_by_symbol = {t["symbol"]: t for t in open_trades if t["status"] == "OPEN"}
    settle_date = (date.today() + timedelta(days=SETTLEMENT_DAYS)).isoformat()

    executed_trades_this_pass = 0

    for symbol in symbols:
        # Break early if we hit our daily limit mid-pass
        if trades_today + executed_trades_this_pass >= MAX_TRADES_PER_DAY:
            logger.info("Max daily trades reached mid-pass. Stopping further evaluations.")
            break

        rows = db.get_ohlc(symbol, limit_days=250)
        if len(rows) < 30:
            results.append({"symbol": symbol, "recommendation": "SKIP", "error": "insufficient history"})
            continue
        
        computed = ind.compute_all(rows)
        if not computed: continue
            
        news_items = db.get_recent_news(symbol, limit=5)
        result = score(computed, news_items=news_items)
        db.save_score(symbol, result["as_of_date"], computed, result["composite_score"], result["recommendation"], result["reasons"])

        # HARD GATE
        quote = get_live_quote(symbol)
        if quote.status != "FRESH":
            logger.warning(f"SKIPPED_STALE_PRICE: {symbol} - {quote.status}")
            results.append({"symbol": symbol, "recommendation": "SKIPPED_STALE_PRICE", "composite_score": result["composite_score"], "error": f"Data {quote.status}"})
            continue
            
        price = quote.price
        news_text = " | ".join([n["headline"] for n in news_items]) if news_items else "No recent news"
        
        ai_decision, ai_reason = expert_trader_decision(symbol=symbol, current_price=price, technical_score=result["composite_score"], recent_news=news_text)
        
        existing = open_by_symbol.get(symbol)
        
        # --- SELL LOGIC ---
        if existing:
            force = "ai_sell" if ai_decision == "SELL" else ""
            closed, reason, net_pnl, proceeds = _maybe_close(existing, price, computed, force_reason=force)
            if closed:
                executed_trades_this_pass += 1
                db.add_settlement(proceeds, settle_date)
                cash, equity = db.paper_cash_and_equity()
                _, open_trades = _mark_open_positions(cash)
                open_by_symbol = {t["symbol"]: t for t in open_trades if t["status"] == "OPEN"}

        # --- BUY LOGIC ---
        existing = open_by_symbol.get(symbol)
        if ai_decision == "BUY" and not existing:
            dd_raw = db.get_setting(f"DD_{symbol}", "")
            dd_pct = float(dd_raw) if dd_raw else None
            
            # Realistic fill: Price + Slippage
            fill = round(price * (1 + SLIPPAGE_PCT), 2)
            board = _board_lot(symbol)
            qty = (position_size(fill, cash, dd_pct) // board) * board

            if qty == 0:
                one_lot_cost = board * fill * (1 + TOTAL_BUY_FEE_PCT)
                if one_lot_cost <= (cash * (settings.MAX_POSITION_SIZE_PERCENT / 100.0) * 1.2) and one_lot_cost <= cash:
                    qty = board

            if qty > 0:
                stop = stop_loss_price(fill, computed.get("atr"), "BUY")
                tgt = target_price(fill, stop, "BUY")
                cost = (qty * fill) * (1 + TOTAL_BUY_FEE_PCT)
                
                if cost <= cash:
                    cash -= cost
                    db.insert_paper_trade({
                        "symbol": symbol, "action": "BUY", "quantity": qty,
                        "entry_price": fill, "stop_loss": stop, "target": tgt,
                        "reason": f"AI: {ai_reason}"
                    })
                    executed_trades_this_pass += 1
                    logger.info(f"OPENED BUY {symbol} @ {fill} | Qty: {qty} | Cost: {cost:.2f}")

        results.append({"symbol": symbol, "recommendation": ai_decision, "composite_score": result["composite_score"], "price": price})

    # Recalculate equity using the UPDATED cash variable
    current_equity, _ = _mark_open_positions(cash)
    db.record_paper_equity(cash, current_equity, note="paper_pass")
    return results