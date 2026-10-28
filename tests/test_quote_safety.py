from datetime import datetime, timedelta, timezone
import unittest

from quote_safety import (
    MarketQuote,
    QuoteStatus,
    validate_intraday_quote,
)


class QuoteValidationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 28, 6, 0, tzinfo=timezone.utc)

    def quote(self, **overrides):
        values = {
            "symbol": "NABIL",
            "price": 500.0,
            "observed_at": self.now - timedelta(seconds=30),
            "fetched_at": self.now - timedelta(seconds=5),
            "source": "test-feed",
            "status": QuoteStatus.LIVE,
        }
        values.update(overrides)
        return MarketQuote(**values)

    def test_accepts_fresh_live_quote(self):
        result = validate_intraday_quote(self.quote(), "NABIL", now=self.now)
        self.assertTrue(result.accepted)
        self.assertEqual(result.reason, "accepted")

    def test_rejects_missing_quote(self):
        self.assertEqual(
            validate_intraday_quote(None, "NABIL", now=self.now).reason,
            "quote_missing",
        )

    def test_rejects_missing_observation_timestamp(self):
        result = validate_intraday_quote(
            self.quote(observed_at=None), "NABIL", now=self.now
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "observation_timestamp_missing")

    def test_rejects_unverified_scraped_quote(self):
        result = validate_intraday_quote(
            self.quote(status=QuoteStatus.UNVERIFIED, observed_at=None),
            "NABIL",
            now=self.now,
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "quote_status_unverified")

    def test_rejects_stale_observation(self):
        result = validate_intraday_quote(
            self.quote(observed_at=self.now - timedelta(seconds=121)),
            "NABIL",
            now=self.now,
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "quote_stale")

    def test_rejects_old_fetch_even_if_observation_is_fresh(self):
        result = validate_intraday_quote(
            self.quote(fetched_at=self.now - timedelta(seconds=31)),
            "NABIL",
            now=self.now,
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "fetch_too_old")

    def test_rejects_wrong_symbol(self):
        result = validate_intraday_quote(self.quote(), "NICA", now=self.now)
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "symbol_mismatch")

    def test_rejects_bad_prices(self):
        for price in (0, -1, float("nan"), float("inf")):
            with self.subTest(price=price):
                result = validate_intraday_quote(
                    self.quote(price=price), "NABIL", now=self.now
                )
                self.assertFalse(result.accepted)
                self.assertEqual(result.reason, "price_not_positive_finite")

    def test_rejects_naive_timestamp(self):
        result = validate_intraday_quote(
            self.quote(observed_at=datetime(2026, 10, 28, 5, 59)),
            "NABIL",
            now=self.now,
        )
        self.assertFalse(result.accepted)
        self.assertEqual(
            result.reason,
            "observation_timestamp_missing_or_timezone_naive",
        )

    def test_rejects_wrong_source_when_allowlist_is_configured(self):
        from quote_safety import QuotePolicy

        result = validate_intraday_quote(
            self.quote(),
            "NABIL",
            now=self.now,
            policy=QuotePolicy(allowed_sources=frozenset({"approved-feed"})),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "source_not_allowed")


if __name__ == "__main__":
    unittest.main()
