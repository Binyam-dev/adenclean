"""Money math in integer cents. No floats anywhere."""

from datetime import timedelta


def _bps(amount_cents, bps):
    """Basis points of an amount, rounded half up, in whole cents."""
    if amount_cents < 0:
        raise ValueError("Amounts must not be negative")
    return (amount_cents * bps + 5_000) // 10_000


def split_payment(price_cents, config, tip_cents=0):
    """Return what the customer pays, the platform fee, and the cleaner payout."""
    if tip_cents < 0:
        raise ValueError("Tips must not be negative")
    fee = _bps(price_cents, config.platform_fee_bps)
    return {
        "customer_pays_cents": price_cents + tip_cents,
        "platform_fee_cents": fee,
        "cleaner_payout_cents": price_cents - fee + tip_cents,  # tips go 100% to the cleaner
        "fee_bps": config.platform_fee_bps,  # stored per booking
    }


def cancellation(price_cents, who, cancelled_at, starts_at, config, waived=False):
    """Who owes what when a booking is cancelled.

    Cleaner cancellations never carry a money penalty; they are a reliability signal only.
    A late customer cancellation pays the cleaner a fee, which the cleaner can waive.
    """
    late = starts_at - cancelled_at < timedelta(hours=config.late_cancel_window_hours)
    if who == "customer" and late and not waived:
        fee = _bps(price_cents, config.late_cancel_fee_bps)
        return {"refund_cents": price_cents - fee, "cleaner_fee_cents": fee, "late": True}
    return {"refund_cents": price_cents, "cleaner_fee_cents": 0, "late": late}


def auto_confirm_due(checked_out_at, now, config):
    return now - checked_out_at >= timedelta(hours=config.auto_confirm_hours)
