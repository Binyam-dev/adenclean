"""Offers, counter-offers and acceptance.

Contractor-protection rules enforced here: the cleaner names the price (the platform never
does), declining or ignoring a job has no consequence, and the price locks at acceptance.
"""

from dataclasses import dataclass, field, replace

from . import jobs

PENDING, COUNTERED, ACCEPTED, DECLINED, WITHDRAWN, EXPIRED = (
    "pending", "countered", "accepted", "declined", "withdrawn", "expired",
)
OPEN_STATES = frozenset({PENDING, COUNTERED})


class OfferError(ValueError):
    pass


@dataclass(frozen=True)
class Offer:
    id: str
    job_id: str
    cleaner_id: str
    price_cents: int
    status: str = PENDING
    counter_rounds: int = 0
    # Who must answer next: the customer answers a cleaner's offer or counter, the cleaner
    # answers a customer's counter.
    awaiting: str = jobs.CUSTOMER
    history: tuple = field(default_factory=tuple)


def check_price(price_cents, config):
    if not isinstance(price_cents, int) or isinstance(price_cents, bool):
        raise OfferError("Price must be a whole number of cents")
    if not config.min_price_cents <= price_cents <= config.max_price_cents:
        raise OfferError(
            f"Price must be between ${config.min_price_cents / 100:.2f} and ${config.max_price_cents / 100:.2f}"
        )
    return price_cents


def check_not_self_dealing(job_customer_id, cleaner_id, signals=None):
    """Block a cleaner offering on their own job; return soft flags for admin review."""
    if job_customer_id == cleaner_id:
        raise OfferError("You cannot send an offer on your own job")
    signals = signals or {}
    return sorted(name for name in ("same_device", "same_address", "same_payment_method") if signals.get(name))


def make_offer(offer_id, job, cleaner_id, price_cents, config, signals=None):
    if job["status"] != "open":
        raise OfferError("This job is no longer taking offers")
    flags = check_not_self_dealing(job["customer_id"], cleaner_id, signals)
    offer = Offer(
        id=offer_id, job_id=job["id"], cleaner_id=cleaner_id,
        price_cents=check_price(price_cents, config),
        history=(("offer", jobs.CLEANER, price_cents),),
    )
    return offer, flags


def counter(offer, actor, price_cents, config):
    if offer.status not in OPEN_STATES:
        raise OfferError("This offer is closed")
    if actor != offer.awaiting:
        raise OfferError("It is the other person's turn to answer")
    if offer.counter_rounds >= config.max_counter_rounds:
        raise OfferError("No more counter-offers. Accept or decline this price.")
    check_price(price_cents, config)
    return replace(
        offer, price_cents=price_cents, status=COUNTERED, counter_rounds=offer.counter_rounds + 1,
        awaiting=jobs.CLEANER if actor == jobs.CUSTOMER else jobs.CUSTOMER,
        history=offer.history + (("counter", actor, price_cents),),
    )


def accept(offer, actor):
    """Accept the price on the table. The caller must hold the booking lock (see locks.py)."""
    if offer.status not in OPEN_STATES:
        raise OfferError("This offer is closed")
    if actor != offer.awaiting:
        raise OfferError("It is the other person's turn to answer")
    return replace(offer, status=ACCEPTED, history=offer.history + (("accept", actor, offer.price_cents),))


def decline(offer, actor):
    if offer.status not in OPEN_STATES:
        raise OfferError("This offer is closed")
    if actor != offer.awaiting:
        raise OfferError("It is the other person's turn to answer")
    return replace(offer, status=DECLINED, history=offer.history + (("decline", actor, None),))


def withdraw(offer, cleaner_id):
    if offer.cleaner_id != cleaner_id:
        raise OfferError("Only the cleaner who sent this offer can withdraw it")
    if offer.status not in OPEN_STATES:
        raise OfferError("This offer is closed")
    return replace(offer, status=WITHDRAWN, history=offer.history + (("withdraw", jobs.CLEANER, None),))
