# NEPSE Analysis & Paper-Trading Agent (improved)

Local research tool for NEPSE securities: collect prices/news → technical indicators →
rule-based BUY/SELL/HOLD scores → paper trades → backtests. **No live broker orders.**

## What improved vs the original

| Area | Change |
|------|--------|
| **Scrapers** | Working Merolagani OHLC API + ShareSansar live table (no placeholder selectors) |
| **Indicators** | Added ATR, Stochastic, Bollinger width; more robust NaN handling |
| **Scoring** | Uses stochastic + simple news sentiment keywords |
| **CLI** | Fixed ignored `--symbol`; added `--history`, `analyze-all`, `status`, `ui` |
| **Strategies** | `default` and `conservative` variants |
| **Paper trading** | ATR stops/targets, daily loss halt, equity tracking |
| **UI** | Streamlit dashboard (`python main.py ui`) |
| **DB** | Sentiment column, paper_equity table, better score queries |

## Quick start

```bash
cd nepse_agent
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

python main.py init-db
python main.py collect --history          # ~1 year OHLC for watchlist
python main.py analyze NABIL
python main.py analyze-all
python main.py backtest NABIL
python main.py paper-trade
python main.py status
python main.py ui                         # Streamlit dashboard
```

### Useful collect variants

```bash
python main.py collect --history --symbol NABIL   # one ticker history
python main.py collect                            # live snapshot + watchlist history + news
python main.py collect --dry-run                  # print raw responses, don't write DB
```

## News & web research

```bash
python main.py collect          # site scrapers + DuckDuckGo web search (Nepal/NEPSE/finance)
python main.py research         # build market + per-symbol digests from stored news
python main.py analyze NABIL    # score uses indicators + news + research digests
```

Coverage is **best-effort** across Nepal finance sites and web search queries — not the entire internet.
Digests and headlines are stored in SQLite (your local long-term memory).

## Architecture

1. **collectors/** — Merolagani history, ShareSansar live, news + keyword sentiment  
2. **analysis/** — SMA/EMA, RSI, MACD, Bollinger, ATR, Stochastic, support/resistance  
3. **scoring_engine** — transparent point system with written reasons  
4. **strategy/rules.py** — strategy variants for backtest comparison  
5. **paper_trading/** — hypothetical positions with risk limits  
6. **backtest/** — walk-forward replay on stored OHLC  
7. **execution/tms_interface.py** — **stub only** (no live orders)  
8. **ui/app.py** — Streamlit overview / analyze / portfolio / news  

## Risk notes

- Not financial advice. Backtests ≠ future results.
- Scrapers can break when sites change; failures are logged and can halt paper trading.
- Live TMS automation is intentionally unimplemented.

## Tests

```bash
python -m pytest tests/
# or:
python tests/test_indicators.py
```
