"""Accept-an-offer under one process-wide lock.

Appwrite has no conditional updates or transactions, so double acceptance is prevented by
re-reading state inside this lock. That only works with ONE server instance.
"""

import threading

from . import jobs, offers

BOOKING_LOCK = threading.Lock()


def accept_offer(load_job, load_offer, save, offer_id, actor_id, actor_role):
    """Accept an offer and book its job exactly once.

    load_job(job_id) / load_offer(offer_id) return current records; save(job, offer) persists
    both. Raises offers.OfferError or jobs.TransitionError if anything changed underneath.
    """
    with BOOKING_LOCK:
        offer = load_offer(offer_id)
        job = load_job(offer.job_id)
        if actor_role == jobs.CUSTOMER and job["customer_id"] != actor_id:
            raise offers.OfferError("Only the customer who posted this job can accept")
        if actor_role == jobs.CLEANER and offer.cleaner_id != actor_id:
            raise offers.OfferError("Only the cleaner on this offer can accept a counter")
        if job["status"] != "open":
            raise offers.OfferError("This job already has a booking")
        accepted = offers.accept(offer, actor_role)
        # Booking is always the customer's decision in the job table, even when the cleaner
        # accepts the customer's counter: the customer proposed that price.
        booked = dict(job, status=jobs.transition(job["status"], "booked", jobs.CUSTOMER),
                      booked_offer_id=accepted.id, price_cents=accepted.price_cents)
        save(booked, accepted)
        return booked, accepted
