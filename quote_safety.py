"""Timestamped market quote model and fail-closed validation.

This module validates data only. It does not place orders or make trade decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import math
from typing import FrozenSet


class QuoteStatus(str, Enum):
    LIVE = "live"
    DELAYED = "delayed"
    END_OF_DAY = "end_of_day"
    UNVERIFIED = "unverified"


@dataclass(frozen=True, slots=True)
class MarketQuote:
    """A quote plus source and timing metadata.

    `observed_at` is when the source says the market observation occurred.
    `fetched_at` is when this application received the response. Both must be
    timezone-aware. An absent observation timestamp is never accepted for an
    intraday decision.
    """

    symbol: str
    price: float
    observed_at: datetime | None
    fetched_at: datetime
    source: str
    status: QuoteStatus = QuoteStatus.UNVERIFIED


@dataclass(frozen=True, slots=True)
class QuoteValidation:
    accepted: bool
    reason: str
    quote_age_seconds: float | None = None
    fetch_age_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class QuotePolicy:
    max_quote_age: timedelta = timedelta(seconds=120)
    max_fetch_age: timedelta = timedelta(seconds=30)
    allowed_future_skew: timedelta = timedelta(seconds=30)
    allowed_sources: FrozenSet[str] | None = None


DEFAULT_QUOTE_POLICY = QuotePolicy()


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def validate_intraday_quote(
    quote: MarketQuote | None,
    expected_symbol: str,
    *,
    now: datetime | None = None,
    policy: QuotePolicy = DEFAULT_QUOTE_POLICY,
) -> QuoteValidation:
    """Accept only a fresh, timestamped, explicitly live quote.

    Missing fields, stale data, unverified/delayed/end-of-day observations,
    source mismatches, and invalid clocks fail closed.
    """
    if quote is None:
        return QuoteValidation(False, "quote_missing")

    expected = (expected_symbol or "").strip().upper()
    actual = (quote.symbol or "").strip().upper()
    if not expected or actual != expected:
        return QuoteValidation(False, "symbol_mismatch")

    try:
        price = float(quote.price)
    except (TypeError, ValueError, OverflowError):
        return QuoteValidation(False, "price_not_numeric")
    if not math.isfinite(price) or price <= 0:
        return QuoteValidation(False, "price_not_positive_finite")

    if not quote.source or not quote.source.strip():
        return QuoteValidation(False, "source_missing")
    if policy.allowed_sources is not None and quote.source not in policy.allowed_sources:
        return QuoteValidation(False, "source_not_allowed")

    try:
        status = QuoteStatus(quote.status)
    except (TypeError, ValueError):
        return QuoteValidation(False, "quote_status_unknown")
    if status is not QuoteStatus.LIVE:
        return QuoteValidation(False, f"quote_status_{status.value}")

    if not isinstance(quote.fetched_at, datetime) or not _is_aware(quote.fetched_at):
        return QuoteValidation(False, "fetch_timestamp_missing_or_timezone_naive")
    if quote.observed_at is None:
        return QuoteValidation(False, "observation_timestamp_missing")
    if not isinstance(quote.observed_at, datetime) or not _is_aware(quote.observed_at):
        return QuoteValidation(False, "observation_timestamp_missing_or_timezone_naive")

    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or not _is_aware(current):
        return QuoteValidation(False, "validation_clock_missing_or_timezone_naive")
    current_utc = current.astimezone(timezone.utc)
    fetched_utc = quote.fetched_at.astimezone(timezone.utc)
    observed_utc = quote.observed_at.astimezone(timezone.utc)

    fetch_age = (current_utc - fetched_utc).total_seconds()
    quote_age = (current_utc - observed_utc).total_seconds()
    future_limit = policy.allowed_future_skew.total_seconds()

    if fetch_age < -future_limit:
        return QuoteValidation(False, "fetch_timestamp_in_future", quote_age, fetch_age)
    if quote_age < -future_limit:
        return QuoteValidation(False, "observation_timestamp_in_future", quote_age, fetch_age)
    if fetch_age > policy.max_fetch_age.total_seconds():
        return QuoteValidation(False, "fetch_too_old", quote_age, fetch_age)
    if quote_age > policy.max_quote_age.total_seconds():
        return QuoteValidation(False, "quote_stale", quote_age, fetch_age)

    return QuoteValidation(True, "accepted", quote_age, fetch_age)
