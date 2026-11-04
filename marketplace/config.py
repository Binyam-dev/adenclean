"""Marketplace settings. Every business number lives here, never in the rules themselves."""

import os
from dataclasses import dataclass


def _int(environ, name, default):
    raw = environ.get(name)
    if raw is None or raw == "":
        return default
    value = int(raw)
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


@dataclass(frozen=True)
class MarketplaceConfig:
    platform_fee_bps: int = 1500  # 15% of the agreed price, charged to the cleaner
    late_cancel_fee_bps: int = 2500  # paid to the cleaner when the customer cancels late
    late_cancel_window_hours: int = 24
    auto_confirm_hours: int = 48
    max_counter_rounds: int = 2
    offer_expiry_hours: int = 24
    job_expiry_hours: int = 72
    damage_cap_cents: int = 100_000
    min_price_cents: int = 2_000
    max_price_cents: int = 200_000
    service_zips: tuple = ("20901", "20902", "20903", "20904", "20905", "20906", "20910",
                           "20912", "20895", "20850", "20852", "20853", "20814", "20815",
                           "20816", "20817")

    def __post_init__(self):
        if self.platform_fee_bps > 10_000 or self.late_cancel_fee_bps > 10_000:
            raise ValueError("Fee basis points must be 10000 or less")
        if self.min_price_cents > self.max_price_cents:
            raise ValueError("min_price_cents must not exceed max_price_cents")


def load(environ=None):
    environ = os.environ if environ is None else environ
    zips = environ.get("SERVICE_ZIPS")
    defaults = MarketplaceConfig()
    return MarketplaceConfig(
        platform_fee_bps=_int(environ, "PLATFORM_FEE_BPS", defaults.platform_fee_bps),
        late_cancel_fee_bps=_int(environ, "LATE_CANCEL_FEE_BPS", defaults.late_cancel_fee_bps),
        late_cancel_window_hours=_int(environ, "LATE_CANCEL_WINDOW_HOURS", defaults.late_cancel_window_hours),
        auto_confirm_hours=_int(environ, "AUTO_CONFIRM_HOURS", defaults.auto_confirm_hours),
        max_counter_rounds=_int(environ, "MAX_COUNTER_ROUNDS", defaults.max_counter_rounds),
        offer_expiry_hours=_int(environ, "OFFER_EXPIRY_HOURS", defaults.offer_expiry_hours),
        job_expiry_hours=_int(environ, "JOB_EXPIRY_HOURS", defaults.job_expiry_hours),
        damage_cap_cents=_int(environ, "DAMAGE_CAP_CENTS", defaults.damage_cap_cents),
        min_price_cents=_int(environ, "MIN_PRICE_CENTS", defaults.min_price_cents),
        max_price_cents=_int(environ, "MAX_PRICE_CENTS", defaults.max_price_cents),
        service_zips=tuple(z.strip() for z in zips.split(",") if z.strip()) if zips else defaults.service_zips,
    )
