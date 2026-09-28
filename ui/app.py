"""Dipen's NEPSE Analysis Agent — Streamlit dashboard."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from analysis import indicators as ind
from analysis.scoring_engine import score
from alerts.runner import run_alerts
from alerts.prefs import get_holdings, set_holdings, get_price_alerts, set_price_alerts
from config import settings
from database import db

st.set_page_config(
    page_title="Dipen's NEPSE Analysis Agent",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .main .block-container { padding-top: 1.5rem; }
    h1, h2, h3 { color: #e8eaf0; }
    .metric-card {
        background: linear-gradient(135deg, #1a1d28 0%, #232734 100%);
        border: 1px solid #2e3242;
        border-radius: 12px;
        padding: 18px 20px;
        margin: 4px 0;
    }
    .metric-label { color: #8b90a0; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-value { color: #e8eaf0; font-size: 26px; font-weight: 600; margin-top: 4px; }
    .metric-delta-pos { color: #4ade80; font-size: 14px; margin-top: 2px; }
    .metric-delta-neg { color: #f87171; font-size: 14px; margin-top: 2px; }
    .badge-buy {
        background: #16a34a22; color: #4ade80; border: 1px solid #16a34a55;
        padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 13px;
    }
    .badge-sell {
        background: #dc262622; color: #f87171; border: 1px solid #dc262655;
        padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 13px;
    }
    .badge-hold {
        background: #64748b22; color: #94a3b8; border: 1px solid #64748b55;
        padding: 2px 10px; border-radius: 12px; font-weight: 600; font-size: 13px;
    }
    .headline-item { padding: 6px 0; border-bottom: 1px solid #2a2e3a; }
    .headline-positive { color: #4ade80; }
    .headline-negative { color: #f87171; }
    .headline-neutral { color: #94a3b8; }
    .stTabs [data-baseweb="tab-list"] { gap: 6px; }
    .stTabs [data-baseweb="tab"] {
        background: #1a1d28; border-radius: 8px; padding: 8px 18px; color: #8b90a0;
    }
    .stTabs [aria-selected="true"] { background: #2e3242 !important; color: #e8eaf0 !important; }
</style>
""", unsafe_allow_html=True)


try:
    db.init_db()
except Exception:
    pass


def card(label: str, value: str, delta: str | None = None, positive: bool | None = None):
    delta_html = ""
    if delta:
        cls = "metric-delta-pos" if positive else "metric-delta-neg"
        delta_html = f'<div class="{cls}">{delta}</div>'
    st.markdown(
        f'<div class="metric-card">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>'
        f'{delta_html}</div>',
        unsafe_allow_html=True,
    )


def rec_badge(rec: str) -> str:
    r = (rec or "").upper()
    if r == "BUY":
        return '<span class="badge-buy">BUY</span>'
    if r == "SELL":
        return '<span class="badge-sell">SELL</span>'
    return '<span class="badge-hold">HOLD</span>'


st.markdown("# 📈 Dipen's NEPSE Analysis Agent")
st.caption("Paper trading only · Not financial advice · Real data from NEPSE / ShareSansar / Google News")

tab_overview, tab_analyze, tab_portfolio, tab_news, tab_alerts, tab_watch, tab_profit = st.tabs(
    ["📊 Overview", "🔍 Analyze", "💼 Portfolio", "📰 News", "🔔 Alerts", "📋 Watchlist", "✅ Profitable"]
)


# ═════════════════════════════════════════════════════════════════
# OVERVIEW
# ═════════════════════════════════════════════════════════════════
with tab_overview:
    cash, equity = db.paper_cash_and_equity()
    open_trades = db.get_open_paper_trades()
    symbols = db.list_symbols_with_data()
    pnl_pct = ((equity - settings.PAPER_STARTING_CAPITAL) / settings.PAPER_STARTING_CAPITAL * 100) if settings.PAPER_STARTING_CAPITAL else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        card("Cash", f"NPR {cash:,.0f}")
    with c2:
        card("Equity", f"NPR {equity:,.0f}", f"{pnl_pct:+.2f}%", positive=pnl_pct >= 0)
    with c3:
        card("Open positions", str(len(open_trades)))
    with c4:
        card("Symbols tracked", str(len(symbols)))

    st.markdown("### 🎯 Recommendation summary")
    scores = db.get_latest_scores(limit=200)
    if scores:
        from collections import Counter
        counts = Counter(s["recommendation"] for s in scores)
        b1, b2, b3 = st.columns(3)
        with b1:
            card("BUY signals", str(counts.get("BUY", 0)))
        with b2:
            card("SELL signals", str(counts.get("SELL", 0)))
        with b3:
            card("HOLD signals", str(counts.get("HOLD", 0)))

    st.markdown("### 📋 Top scores")
    if scores:
        df = pd.DataFrame(scores)[
            ["symbol", "composite_score", "recommendation", "trend", "as_of_date"]
        ].head(15)
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("### 👀 Watchlist")
    st.caption(", ".join(settings.WATCHLIST))


# ═════════════════════════════════════════════════════════════════
# ANALYZE
# ═════════════════════════════════════════════════════════════════
with tab_analyze:
    options = [r["symbol"] for r in db.list_symbols_with_data()] or settings.WATCHLIST
    col_a, col_b = st.columns([3, 1])
    with col_a:
        symbol = st.selectbox("Symbol", options, key="analyze_symbol")
    with col_b:
        st.write("")
        run = st.button("▶ Run analysis", type="primary", use_container_width=True)

    if run:
        rows = db.get_ohlc(symbol, limit_days=250)
        if len(rows) < 30:
            st.warning("Not enough history. Run: python main.py collect --history")
        else:
            computed = ind.compute_all(rows)
            result = score(computed, news_items=db.get_recent_news(symbol, limit=15))
            db.save_score(
                symbol,
                result["as_of_date"],
                computed,
                result["composite_score"],
                result["recommendation"],
                result["reasons"],
            )

            m1, m2, m3, m4 = st.columns(4)
            with m1:
                card("Price", f"{computed['price']:,.2f}")
            with m2:
                card("Score", str(result["composite_score"]))
            with m3:
                st.markdown(
                    f'<div class="metric-card"><div class="metric-label">Recommendation</div>'
                    f'<div style="margin-top:8px">{rec_badge(result["recommendation"])}</div></div>',
                    unsafe_allow_html=True,
                )
            with m4:
                card("Trend", computed["trend"].title())

            st.markdown("### 📉 Price history")
            df = pd.DataFrame(rows)
            if not df.empty and "close" in df.columns:
                st.line_chart(df.set_index("date")["close"], height=280)

            st.markdown("### 📌 Indicator snapshot")
            ind_cols = st.columns(4)
            ind_cols[0].metric("RSI", computed.get("rsi"))
            ind_cols[1].metric("Stoch %K", computed.get("stochastic_k"))
            ind_cols[2].metric("ATR", computed.get("atr"))
            ind_cols[3].metric("Volume vs avg", computed.get("volume_vs_avg"))
            ind_cols2 = st.columns(4)
            ind_cols2[0].metric("EMA20", computed.get("ema20"))
            ind_cols2[1].metric("EMA50", computed.get("ema50"))
            ind_cols2[2].metric("Support", computed.get("support"))
            ind_cols2[3].metric("Resistance", computed.get("resistance"))

            st.markdown("### 💡 Why")
            for r in result["reasons"]:
                st.write(f"- {r}")


# ═════════════════════════════════════════════════════════════════
# PORTFOLIO
# ═════════════════════════════════════════════════════════════════
with tab_portfolio:
    open_trades = db.get_open_paper_trades()
    st.markdown("### 📂 Open positions")
    if open_trades:
        df = pd.DataFrame(open_trades)
        cols = ["symbol", "action", "quantity", "entry_price", "stop_loss", "target", "opened_at"]
        cols = [c for c in cols if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)
    else:
        st.info("No open positions. Run: `python main.py paper-trade`")

    st.markdown("### 💰 Holdings (MY_HOLDINGS)")
    holdings = get_holdings()
    if holdings:
        rows = []
        for sym, qty in holdings.items():
            px = None
            ohlc = db.get_ohlc(sym, limit_days=2)
            if ohlc:
                px = float(ohlc[-1]["close"])
            value = (px * qty) if px and qty else 0
            rows.append({"Symbol": sym, "Shares": qty, "Price": px, "Value": value})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("Add holdings in the Alerts tab.")


# ═════════════════════════════════════════════════════════════════
# NEWS
# ═════════════════════════════════════════════════════════════════
with tab_news:
    st.markdown("### 🌍 Market digest")
    market = db.get_latest_research("MARKET")
    if market and market.get("payload"):
        p = market["payload"]
        c1, c2, c3 = st.columns(3)
        with c1:
            card("Items", str(p.get("item_count", 0)))
        with c2:
            card("Avg sentiment", f"{p.get('avg_sentiment', 0):+.2f}")
        with c3:
            card("Tone", (p.get("tone") or "-").title())

        st.caption(p.get("summary", ""))
        if p.get("themes"):
            st.write("**Themes:** " + ", ".join(
                f"{t['theme']} ({t['mentions']})" for t in p["themes"][:6]
            ))

        cols = st.columns(2)
        with cols[0]:
            st.markdown("#### ✅ Constructive")
            for h in (p.get("bullish_headlines") or [])[:8]:
                st.markdown(
                    f'<div class="headline-item headline-positive">+ {h.get("headline","")[:130]}</div>',
                    unsafe_allow_html=True,
                )
        with cols[1]:
            st.markdown("#### ⚠️ Cautious")
            for h in (p.get("bearish_headlines") or [])[:8]:
                st.markdown(
                    f'<div class="headline-item headline-negative">- {h.get("headline","")[:130]}</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.info("No digest yet. Run: `python main.py collect` then `python main.py research`")

    st.markdown("### 📰 Recent headlines")
    news = db.get_recent_news(limit=60)
    if news:
        df = pd.DataFrame(news)
        cols = [c for c in ["headline", "direction", "impact_weight", "source", "symbol"] if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)
    else:
        st.info("No news yet. Run: `python main.py collect`")


# ═════════════════════════════════════════════════════════════════
# ALERTS
# ═════════════════════════════════════════════════════════════════
with tab_alerts:
    st.markdown("### 🔔 Configure alerts")
    st.caption("Saved in database — no need to edit .env anymore.")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 💼 My holdings")
        st.caption("One per line: `SYMBOL:quantity`. Use 0 for watch-only.")
        current_holdings = get_holdings()
        default_text = "\n".join(f"{s}:{q}" for s, q in current_holdings.items())
        holdings_text = st.text_area(
            "Holdings",
            value=default_text,
            height=180,
            label_visibility="collapsed",
            key="holdings_input",
        )
        if st.button("💾 Save holdings", key="save_holdings"):
            parsed = {}
            errors = []
            for line in (holdings_text or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                if ":" not in line:
                    errors.append(f"Bad line: {line}")
                    continue
                sym, _, qty = line.partition(":")
                try:
                    parsed[sym.strip().upper()] = int(qty.strip())
                except ValueError:
                    errors.append(f"Bad quantity: {line}")
            if errors:
                for e in errors:
                    st.error(e)
            else:
                set_holdings(parsed)
                st.success(f"Saved {len(parsed)} holding(s).")
                st.rerun()

    with col2:
        st.markdown("#### 📈 Price alerts")
        st.caption("One per line: `SYMBOL>price`, `SYMBOL<price`, `SYMBOL>+pct`, `SYMBOL<-pct`.")
        current_pa = get_price_alerts()
        pa_lines = [
            f"{t['symbol']}{t['op']}{t['value']}"
            for t in current_pa
        ]
        alerts_text = st.text_area(
            "Price alerts",
            value="\n".join(pa_lines),
            height=180,
            label_visibility="collapsed",
            key="price_alerts_input",
        )
        if st.button("💾 Save price alerts", key="save_price_alerts"):
            parts = [l.strip() for l in (alerts_text or "").splitlines() if l.strip()]
            raw = ",".join(parts)
            set_price_alerts(raw)
            st.success(f"Saved {len(parts)} alert(s).")
            st.rerun()

    st.markdown("---")
    st.markdown("### 🚀 Run alerts now")
    if st.button("▶ Send alert check", type="primary"):
        with st.spinner("Checking..."):
            n = run_alerts()
        st.success(f"Sent {n} alert(s).")

    st.markdown("### 📜 Sent history")
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT url, sent_at FROM sent_alerts ORDER BY id DESC LIMIT 50"
        ).fetchall()
    if rows:
        st.dataframe(
            pd.DataFrame([dict(r) for r in rows]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.caption("No alerts sent yet.")
        # ═════════════════════════════════════════════════════════════════
# WATCHLIST
# ═════════════════════════════════════════════════════════════════
with tab_watch:
    from alerts.prefs import get_watchlist, set_watchlist

    st.markdown("### 📋 Manage watchlist")
    st.caption("Stocks the bot analyses, backtests, and paper-trades. One per line.")

    current = get_watchlist()
    text = st.text_area(
        "Watchlist",
        value="\n".join(current),
        height=300,
        label_visibility="collapsed",
        key="watchlist_input",
    )

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("💾 Save watchlist", type="primary"):
            syms = [l.strip().upper() for l in (text or "").splitlines() if l.strip()]
            # Simple validation: uppercase letters/digits only, 2-15 chars
            bad = [s for s in syms if not s.replace("-", "").isalnum() or not (2 <= len(s) <= 15)]
            if bad:
                st.error(f"Invalid symbols: {', '.join(bad)}")
            else:
                set_watchlist(syms)
                st.success(f"Saved {len(syms)} symbols.")
                st.rerun()
    with col_b:
        st.metric("Currently tracking", f"{len(current)} symbols")

    st.markdown("### 📊 Current data coverage")
    data = db.list_symbols_with_data()
    if data:
        df = pd.DataFrame(data)
        df = df.sort_values("n", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True, height=400)
    else:
        st.info("No price data yet. Run: `python main.py collect --history`")

        # ═════════════════════════════════════════════════════════════════
# PROFITABLE STOCKS
# ═════════════════════════════════════════════════════════════════
with tab_profit:
    from alerts.prefs import get_profitable, set_profitable

    st.markdown("### ✅ Profitable stocks")
    st.caption(
        "Only these stocks are paper-traded. Based on backtest results — "
        "stocks where the strategy historically made money."
    )

    current = get_profitable()
    text = st.text_area(
        "Profitable",
        value="\n".join(current),
        height=300,
        label_visibility="collapsed",
        key="profitable_input",
    )

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("💾 Save profitable list", type="primary"):
            syms = [l.strip().upper() for l in (text or "").splitlines() if l.strip()]
            set_profitable(syms)
            st.success(f"Saved {len(syms)} symbols.")
            st.rerun()
    with col_b:
        st.metric("Currently trading", f"{len(current)} stocks")

    st.markdown("### 📊 Backtest reference")
    st.caption("From your last `python backtest_all.py` run")
    try:
        import pandas as pd
        df = pd.read_csv("backtest_rank.csv")
        df = df.sort_values("return_pct", ascending=False)
        st.dataframe(df.head(20), use_container_width=True, hide_index=True)
    except Exception:
        st.caption("Run `python backtest_all.py` to generate rankings.")