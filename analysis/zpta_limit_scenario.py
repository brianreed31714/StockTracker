"""Conservative daily-bar next-session limit-entry scenario classifier.

This is a research *bound*, not evidence of actual OTC execution. In particular,
a low-price touch is ambiguous, not a verified fill. No same-day low is used to
choose the limit: the caller must commit the limit from signal-day data.
"""


def classify_buy_limit(*, prior_close, next_open, next_low, next_high,
                       limit_fraction=0.98):
    if prior_close <= 0 or next_open <= 0 or next_low <= 0 or next_high <= 0:
        raise ValueError("Prices must be positive")
    if not next_low <= next_open <= next_high:
        raise ValueError("Inconsistent next-session OHLC")
    if not 0 < limit_fraction <= 1:
        raise ValueError("Invalid precommitted limit fraction")
    limit = prior_close * limit_fraction
    if next_open <= limit:
        return {"limit": limit, "classification": "open_marketable_unverified",
                "fill_verified": False}
    if next_low > limit:
        return {"limit": limit, "classification": "not_touched",
                "fill_verified": False}
    return {"limit": limit, "classification": "intraday_touch_fill_unknown",
            "fill_verified": False}
