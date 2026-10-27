import sqlite3
import os
from datetime import datetime, timedelta
from analysis import indicators as ind
from analysis.scoring_engine import score
from database import db

# --- NEPSE REALITIES ---
COMMISSION_PCT = 0.0036
SEBON_FEE_PCT = 0.00015
DP_FEE_PCT = 0.00015
TOTAL_BUY_FEE = COMMISSION_PCT + SEBON_FEE_PCT + DP_FEE_PCT
CGT_SHORT_PCT = 0.075
SLIPPAGE_PCT = 0.003
SETTLEMENT_DAYS = 2

def run_backtest(symbol: str, initial_capital: float = 100000.0):
    print(f"\n--- Starting Backtest for {symbol} ---")
    
    rows = db.get_ohlc(symbol, limit_days=1000)
    if len(rows) < 50:
        print(f"Not enough data for {symbol} (found {len(rows)} days).")
        return

    cash = initial_capital
    unsettled_cash = 0.0
    settlement_date = None
    
    position = None
    trades = []
    max_score_seen = -999
    
    # Walk-forward loop
    for i in range(30, len(rows)):
        today_data = rows[i]
        
        if any(today_data[k] is None for k in ['open', 'high', 'low', 'close']): continue
        if rows[i-1]['close'] is None: continue
            
        today_date = datetime.strptime(today_data['date'], "%Y-%m-%d").date()
        
        # --- Process Settlements (T+2) ---
        if settlement_date and today_date >= settlement_date:
            cash += unsettled_cash
            unsettled_cash = 0.0
            settlement_date = None

        # --- Check for Open Position Exit ---
        if position:
            high = float(today_data['high'])
            low = float(today_data['low'])
            
            prev_close = float(rows[i-1]['close'])
            if high > prev_close * 1.10: high = prev_close * 1.10
            if low < prev_close * 0.90: low = prev_close * 0.90
            
            exit_price = None
            exit_reason = ""
            
            if low <= position['stop']:
                exit_price = position['stop']
                exit_reason = "STOP_LOSS"
            elif high >= position['target']:
                exit_price = position['target']
                exit_reason = "TARGET"
            
            if exit_price:
                exit_fill = exit_price * (1 - SLIPPAGE_PCT)
                gross = exit_fill * position['qty']
                fees = gross * TOTAL_BUY_FEE
                proceeds_before_tax = gross - fees
                
                cost_basis = position['entry_price'] * position['qty'] * (1 + TOTAL_BUY_FEE)
                pnl = proceeds_before_tax - cost_basis
                
                tax = pnl * CGT_SHORT_PCT if pnl > 0 else 0.0
                net_proceeds = proceeds_before_tax - tax
                
                unsettled_cash += net_proceeds
                settlement_date = today_date + timedelta(days=SETTLEMENT_DAYS)
                
                trades.append({
                    "symbol": symbol, "entry": position['entry_price'], "exit": exit_fill,
                    "pnl": pnl, "reason": exit_reason, "date": today_date
                })
                position = None
                continue 

        # --- Check for New Entry ---
        if not position and cash > 10000:
            past_data = rows[:i]
            computed = ind.compute_all(past_data)
            
            if computed:
                result = score(computed, news_items=[])
                current_score = result.get("composite_score", 0)
                
                if current_score > max_score_seen:
                    max_score_seen = current_score
                
                # LOWERED THRESHOLD to 15
                if current_score >= 15:
                    prev_close = float(rows[i-1]['close'])
                    open_price = float(today_data['open'])
                    
                    if open_price > prev_close * 1.10 or open_price < prev_close * 0.90:
                        continue 
                    
                    entry_fill = open_price * (1 + SLIPPAGE_PCT)
                    
                    max_rupees = cash * 0.20
                    qty = int(max_rupees // entry_fill)
                    qty = (qty // 10) * 10
                    
                    if qty >= 10:
                        cost = (qty * entry_fill) * (1 + TOTAL_BUY_FEE)
                        if cost <= cash:
                            cash -= cost
                            
                            atr = computed.get("atr", entry_fill * 0.03)
                            if not atr: atr = entry_fill * 0.03
                            
                            stop = entry_fill - (1.5 * atr)
                            if stop < entry_fill * 0.90: stop = entry_fill * 0.90
                            
                            target = entry_fill + (3.0 * atr)
                            if target > entry_fill * 1.10: target = entry_fill * 1.10
                            
                            position = {
                                "entry_price": entry_fill, "qty": qty, 
                                "stop": stop, "target": target,
                                "entry_date": today_date
                            }

    # --- FORCE CLOSE AT END OF BACKTEST ---
    if position:
        last_price = float(rows[-1]['close'])
        exit_fill = last_price * (1 - SLIPPAGE_PCT)
        gross = exit_fill * position['qty']
        fees = gross * TOTAL_BUY_FEE
        proceeds_before_tax = gross - fees
        
        cost_basis = position['entry_price'] * position['qty'] * (1 + TOTAL_BUY_FEE)
        pnl = proceeds_before_tax - cost_basis
        
        tax = pnl * CGT_SHORT_PCT if pnl > 0 else 0.0
        net_proceeds = proceeds_before_tax - tax
        
        unsettled_cash += net_proceeds
        trades.append({
            "symbol": symbol, "entry": position['entry_price'], "exit": exit_fill,
            "pnl": pnl, "reason": "END_OF_BACKTEST", "date": datetime.strptime(rows[-1]['date'], "%Y-%m-%d").date()
        })
        position = None

    # --- Generate Report ---
    total_wins = sum(1 for t in trades if t['pnl'] > 0)
    total_losses = sum(1 for t in trades if t['pnl'] <= 0)
    win_rate = (total_wins / len(trades)) * 100 if trades else 0
    total_pnl = sum(t['pnl'] for t in trades)
    
    print(f"Max Score Seen: {max_score_seen:.2f}")
    print(f"Total Trades: {len(trades)}")
    print(f"Win Rate:     {win_rate:.2f}% ({total_wins} W / {total_losses} L)")
    print(f"Total P&L:    {total_pnl:.2f} NPR")
    print(f"Final Cash:   {cash:.2f} NPR (Includes unsettled: {unsettled_cash:.2f})")
    
    if trades:
        avg_win = sum(t['pnl'] for t in trades if t['pnl'] > 0) / max(1, total_wins)
        avg_loss = sum(t['pnl'] for t in trades if t['pnl'] <= 0) / max(1, total_losses)
        print(f"Avg Win:      {avg_win:.2f} NPR")
        print(f"Avg Loss:     {avg_loss:.2f} NPR")

if __name__ == "__main__":
    for test_symbol in ["NABIL", "NICA", "SCB", "HIDCL", "PCBL", "SHPC"]:
        run_backtest(test_symbol)