"""Booking money flow: charge, hold, release to the cleaner, refunds, tips.

Charge type: Stripe "separate charges and transfers". The customer is charged when they
pay for the booking, funds wait in the platform balance, and the cleaner is paid only
after the customer confirms (or 48 h after check-out with no dispute). Card holds expire
after 7 days and jobs can be 30 days out, so we capture at payment instead of holding an
authorization. Refunds do not reverse transfers in Stripe, which is why nothing is
transferred before completion.

Every money movement writes one append-only ledger entry with a unique idempotency key and
passes the same key to Stripe, so retries and webhook replays never move money twice.
"""

import uuid
from datetime import datetime, time, timezone

from store import Conflict, NotFound

from . import jobs, money

# Cancellation timing is measured from noon UTC on the booked start date (before 8 a.m. in
# Maryland), so a "24 hours ahead" cancellation is never judged later than it really was.
START_TIME = time(12, 0, tzinfo=timezone.utc)


class BookingError(ValueError):
    pass


def _iso(now):
    return now.isoformat()


def _ledger(market, booking_id, entry_type, amount, direction, ref, key, now):
    """Append a ledger entry; return False if this key was already recorded (a replay)."""
    try:
        market.add_ledger_entry({"id": uuid.uuid4().hex, "booking_id": booking_id, "entry_type": entry_type,
                                 "amount_cents": amount, "direction": direction, "stripe_ref": ref,
                                 "idempotency_key": key, "created_at": _iso(now)})
        return True
    except Conflict:
        return False


def create_booking(market, job, offer, cfg, now):
    booking = {
        "id": uuid.uuid4().hex, "job_id": job["id"], "offer_id": offer.id, "customer_id": job["customer_id"],
        "cleaner_id": offer.cleaner_id, "price_cents": offer.price_cents, "fee_bps": cfg.platform_fee_bps,
        "tip_cents": 0, "payment_status": "unpaid", "payment_intent_id": None, "charge_id": None,
        "payout_status": "none", "starts_on": job["date_from"], "checked_in_at": None,
        "checked_out_at": None, "confirmed_at": None, "cancelled_by": None,
        "created_at": _iso(now), "updated_at": _iso(now),
    }
    market.create_booking(booking)
    return booking


def get_booking(market, job_id):
    booking = market.booking_for_job(job_id)
    if not booking:
        raise NotFound("booking")
    return booking


def start_payment(market, gateway, booking, now):
    """Return a PaymentIntent client secret for the booking (same intent on every retry)."""
    if booking["payment_status"] != "unpaid":
        raise BookingError("This booking is already paid.")
    intent = gateway.create_payment_intent(
        booking["price_cents"], f"booking_{booking['id']}",
        {"booking_id": booking["id"], "kind": "booking"}, f"pi:booking:{booking['id']}")
    market.update_booking(booking["id"], {"payment_intent_id": intent["id"], "updated_at": _iso(now)})
    return intent["client_secret"]


def start_tip(market, gateway, booking, tip_cents, cfg, now):
    if booking["payment_status"] != "paid" or not booking["checked_out_at"]:
        raise BookingError("You can tip after the cleaning is done.")
    if booking["tip_cents"]:
        raise BookingError("You already left a tip for this booking.")
    if not isinstance(tip_cents, int) or isinstance(tip_cents, bool) or not 100 <= tip_cents <= cfg.max_price_cents:
        raise BookingError("Choose a tip of at least $1.00.")
    intent = gateway.create_payment_intent(
        tip_cents, f"booking_{booking['id']}", {"booking_id": booking["id"], "kind": "tip"},
        f"pi:tip:{booking['id']}")
    return intent["client_secret"]


def _transfer_tips(market, gateway, booking, account, now):
    for entry in market.ledger_for(booking["id"]):
        if entry["entry_type"] != "tip_charge":
            continue
        key = f"transfer:tip:{entry['stripe_ref']}"
        if any(e["idempotency_key"] == key for e in market.ledger_for(booking["id"])):
            continue
        transfer = gateway.create_transfer(entry["amount_cents"], account["stripe_account_id"],
                                           f"booking_{booking['id']}", entry["stripe_ref"], key)
        _ledger(market, booking["id"], "transfer", entry["amount_cents"], "out", transfer["id"], key, now)


def handle_event(market, gateway, event, now):
    """Apply one verified Stripe event. Safe to call again with the same event."""
    event_id, kind, obj = event["id"], event["type"], event["data"]["object"]
    if market.has_webhook_event(event_id):
        return "duplicate"
    if kind == "payment_intent.succeeded":
        meta = obj.get("metadata") or {}
        booking = market.get_booking(meta.get("booking_id", ""))
        amount, charge = obj.get("amount_received") or obj["amount"], obj.get("latest_charge")
        if meta.get("kind") == "tip":
            if _ledger(market, booking["id"], "tip_charge", amount, "in", charge, f"charge:{obj['id']}", now):
                market.update_booking(booking["id"], {"tip_cents": booking["tip_cents"] + amount, "updated_at": _iso(now)})
            account = market.payout_account(booking["cleaner_id"])
            if booking["payout_status"] == "sent" and account and account["payouts_enabled"]:
                _transfer_tips(market, gateway, booking, account, now)
        else:
            _ledger(market, booking["id"], "charge", amount, "in", charge, f"charge:{obj['id']}", now)
            market.update_booking(booking["id"], {"payment_status": "paid", "payment_intent_id": obj["id"],
                                                  "charge_id": charge, "updated_at": _iso(now)})
    elif kind == "account.updated":
        account = market.payout_account_by_stripe_id(obj["id"])
        if account:
            market.save_payout_account({"user_id": account["user_id"], "stripe_account_id": obj["id"],
                                        "payouts_enabled": 1 if obj.get("payouts_enabled") else 0,
                                        "updated_at": _iso(now)})
    try:
        market.record_webhook_event(event_id, kind, _iso(now))
    except Conflict:
        return "duplicate"
    return "processed"


def _move_job(market, job_id, target, actor, now):
    job = market.get_job(job_id)
    jobs.transition(job["status"], target, actor)
    market.update_job(job_id, {"status": target, "status_updated_at": _iso(now)})


def check_in(market, booking, cleaner_id, now):
    if booking["cleaner_id"] != cleaner_id:
        raise BookingError("Only the booked cleaner can check in.")
    if booking["payment_status"] != "paid":
        raise BookingError("The customer has not paid yet, so the job cannot start.")
    _move_job(market, booking["job_id"], "in_progress", jobs.CLEANER, now)
    market.update_booking(booking["id"], {"checked_in_at": _iso(now), "updated_at": _iso(now)})


def check_out(market, booking, cleaner_id, now):
    if booking["cleaner_id"] != cleaner_id:
        raise BookingError("Only the booked cleaner can check out.")
    _move_job(market, booking["job_id"], "awaiting_confirmation", jobs.CLEANER, now)
    market.update_booking(booking["id"], {"checked_out_at": _iso(now), "updated_at": _iso(now)})


def release(market, gateway, booking, actor, cfg, now):
    """Complete the job and pay the cleaner (price minus fee, plus any tips)."""
    if actor == jobs.SYSTEM and not money.auto_confirm_due(datetime.fromisoformat(booking["checked_out_at"]), now, cfg):
        raise BookingError("Not due for automatic confirmation yet.")
    _move_job(market, booking["job_id"], "completed", actor, now)
    market.update_booking(booking["id"], {"confirmed_at": _iso(now), "updated_at": _iso(now)})
    booking = market.get_booking(booking["id"])
    pay_out(market, gateway, booking, now)


def pay_out(market, gateway, booking, now):
    """Send the cleaner's share. Waits (no error) if their payout account is not ready yet."""
    account = market.payout_account(booking["cleaner_id"])
    if not account or not account["payouts_enabled"] or booking["payout_status"] == "sent":
        return False
    fee_split = money.split_payment(booking["price_cents"], _rate(booking))
    key = f"transfer:{booking['id']}"
    transfer = gateway.create_transfer(fee_split["cleaner_payout_cents"], account["stripe_account_id"],
                                       f"booking_{booking['id']}", booking["charge_id"], key)
    _ledger(market, booking["id"], "transfer", fee_split["cleaner_payout_cents"], "out", transfer["id"], key, now)
    market.update_booking(booking["id"], {"payout_status": "sent", "updated_at": _iso(now)})
    _transfer_tips(market, gateway, booking, account, now)
    return True


class _Rate:
    def __init__(self, bps):
        self.platform_fee_bps = bps


def _rate(booking):
    return _Rate(booking["fee_bps"])  # the rate agreed at booking, not today's config


def cancel(market, gateway, booking, who, cfg, now, waived=False):
    """Cancel a booked job. Customer cancels late: the cleaner gets the late fee."""
    actor = jobs.CUSTOMER if who == "customer" else jobs.CLEANER
    _move_job(market, booking["job_id"], "cancelled", actor, now)
    result = {"refund_cents": 0, "cleaner_fee_cents": 0}
    if booking["payment_status"] == "paid":
        starts = datetime.combine(datetime.fromisoformat(booking["starts_on"]).date(), START_TIME)
        result = money.cancellation(booking["price_cents"], who, now, starts, cfg, waived=waived)
        if result["refund_cents"]:
            key = f"refund:{booking['id']}"
            refund = gateway.create_refund(booking["payment_intent_id"], result["refund_cents"], key)
            _ledger(market, booking["id"], "refund", result["refund_cents"], "out", refund["id"], key, now)
        account = market.payout_account(booking["cleaner_id"])
        if result["cleaner_fee_cents"] and account and account["payouts_enabled"]:
            key = f"transfer:cancel:{booking['id']}"
            transfer = gateway.create_transfer(result["cleaner_fee_cents"], account["stripe_account_id"],
                                               f"booking_{booking['id']}", booking["charge_id"], key)
            _ledger(market, booking["id"], "transfer", result["cleaner_fee_cents"], "out", transfer["id"], key, now)
    market.update_booking(booking["id"], {"cancelled_by": who, "updated_at": _iso(now),
                                          "payment_status": "refunded" if result["refund_cents"] else booking["payment_status"]})
    return result


def reconcile(entries):
    """Totals from the ledger. Platform balance = money in minus money out."""
    totals = {"in": 0, "refunds": 0, "transfers": 0}
    for e in entries:
        if e["direction"] == "in":
            totals["in"] += e["amount_cents"]
        elif e["entry_type"] == "refund":
            totals["refunds"] += e["amount_cents"]
        else:
            totals["transfers"] += e["amount_cents"]
    totals["platform_balance"] = totals["in"] - totals["refunds"] - totals["transfers"]
    return totals
