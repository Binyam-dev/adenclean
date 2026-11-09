"""Job lifecycle as one transition table.

draft -> open -> booked -> in_progress -> awaiting_confirmation -> completed,
with cancelled, expired and disputed as exits. Each transition lists who may trigger it.
"""

CUSTOMER, CLEANER, ADMIN, SYSTEM = "customer", "cleaner", "admin", "system"

STATES = frozenset({
    "draft", "open", "booked", "in_progress", "awaiting_confirmation",
    "completed", "cancelled", "expired", "disputed",
})
TERMINAL = frozenset({"completed", "cancelled"})

# (from_state, to_state) -> actors allowed to make that change
TRANSITIONS = {
    ("draft", "open"): {CUSTOMER},
    ("draft", "cancelled"): {CUSTOMER},
    ("open", "booked"): {CUSTOMER},  # only by accepting an offer
    ("open", "cancelled"): {CUSTOMER, ADMIN},
    ("open", "expired"): {SYSTEM},
    ("expired", "open"): {CUSTOMER},  # repost
    ("expired", "cancelled"): {CUSTOMER, SYSTEM},
    ("booked", "in_progress"): {CLEANER},  # check-in
    ("booked", "cancelled"): {CUSTOMER, CLEANER, ADMIN},
    ("booked", "disputed"): {CUSTOMER, CLEANER},  # e.g. no-show
    ("in_progress", "awaiting_confirmation"): {CLEANER},  # check-out
    ("in_progress", "disputed"): {CUSTOMER, CLEANER},
    ("awaiting_confirmation", "completed"): {CUSTOMER, SYSTEM},  # confirm or auto-confirm
    ("awaiting_confirmation", "disputed"): {CUSTOMER, CLEANER},
    ("disputed", "completed"): {ADMIN},
    ("disputed", "cancelled"): {ADMIN},
}


class TransitionError(ValueError):
    pass


def can_transition(current, target, actor):
    return actor in TRANSITIONS.get((current, target), ())


def transition(current, target, actor):
    """Return the new state, or raise TransitionError explaining why not."""
    if current not in STATES or target not in STATES:
        raise TransitionError(f"Unknown job state: {current!r} -> {target!r}")
    if current in TERMINAL:
        raise TransitionError(f"A {current} job cannot change")
    allowed = TRANSITIONS.get((current, target))
    if allowed is None:
        raise TransitionError(f"A job cannot go from {current} to {target}")
    if actor not in allowed:
        raise TransitionError(f"{actor} cannot move a job from {current} to {target}")
    return target


def next_states(current, actor):
    return sorted(t for (f, t), actors in TRANSITIONS.items() if f == current and actor in actors)
