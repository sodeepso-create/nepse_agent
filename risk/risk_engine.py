from config import settings
from database import db


class RiskViolation(Exception):
    pass


def position_size(price: float, cash: float, dd_pct: float | None = None) -> int:
    if price <= 0 or cash <= 0:
        return 0
    pct = settings.MAX_POSITION_SIZE_PERCENT / 100.0

    # Scale down for risky stocks (high historical drawdown)
    # DD 40% or less -> 1.0x   |   DD 100% -> 0.4x
    if dd_pct is not None:
        scale = max(0.4, 1.0 - max(0.0, dd_pct - 40.0) / 100.0)
        pct *= scale

    max_rupees = cash * pct
    qty = int(max_rupees // price)
    return max(qty, 0)


def check_daily_loss(starting_equity: float, current_equity: float) -> float:
    if starting_equity <= 0:
        return 0.0
    loss_pct = (starting_equity - current_equity) / starting_equity * 100
    if loss_pct >= settings.MAX_DAILY_LOSS_PERCENT:
        raise RiskViolation(
            f"Daily loss limit hit: {loss_pct:.2f}% >= {settings.MAX_DAILY_LOSS_PERCENT}%. "
            "Trading should halt for the day."
        )
    return loss_pct


def check_source_health_before_trading(sources):
    with db.get_conn() as conn:
        for source in sources:
            row = conn.execute(
                "SELECT consecutive_failures FROM source_health WHERE source = ?",
                (source,),
            ).fetchone()
            if row and row["consecutive_failures"] >= 3:
                raise RiskViolation(
                    f"Data source '{source}' has failed {row['consecutive_failures']} times "
                    "in a row. Refusing to trade on stale data."
                )
    return True


def _apply_circuit(entry: float, target: float, side: str = "BUY") -> float:
    """NEPSE circuit breaker: max ±10% per day from entry."""
    if side == "BUY":
        upper = entry * 1.10
        return round(min(target, upper), 2)
    lower = entry * 0.90
    return round(max(target, lower), 2)


def stop_loss_price(entry: float, atr: float | None, side: str = "BUY") -> float:
    """ATR-based stop; falls back to 3% if ATR missing. Capped by circuit."""
    if atr and atr > 0:
        distance = 1.5 * atr
    else:
        distance = entry * 0.03
    if side == "BUY":
        raw = round(entry - distance, 2)
        return max(raw, round(entry * 0.90, 2))  # no lower than -10%
    raw = round(entry + distance, 2)
    return min(raw, round(entry * 1.10, 2))  # no higher than +10%


def target_price(entry: float, stop: float, side: str = "BUY", rr: float = 999.0) -> float:
    """Target from risk-reward ratio. Capped by NEPSE circuit breaker."""
    risk = abs(entry - stop)
    if side == "BUY":
        raw = entry + rr * risk
        return _apply_circuit(entry, raw, "BUY")
    raw = entry - rr * risk
    return _apply_circuit(entry, raw, "SELL")