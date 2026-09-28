"""
STUB ONLY — real TMS/broker order placement is intentionally not implemented.

Automating login and order placement against unofficial TMS endpoints can
violate broker/NEPSE terms. Implement only if you accept that risk yourself.
"""


class TMSNotImplemented(NotImplementedError):
    pass


class TMSInterface:
    def place_order(self, symbol, side, quantity, price=None, order_type="LIMIT"):
        raise TMSNotImplemented(
            "Live TMS execution is a stub. Paper trading only in this codebase."
        )

    def cancel_order(self, order_id):
        raise TMSNotImplemented("Live TMS execution is a stub.")

    def get_positions(self):
        raise TMSNotImplemented("Live TMS execution is a stub.")
