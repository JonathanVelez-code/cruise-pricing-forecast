import numpy as np
import pandas as pd

from src.etl import clean_bookings


def make_raw():
    sailings = pd.DataFrame({"sailing_id": [1], "sail_date": [pd.Timestamp("2026-06-01")]})
    b = pd.DataFrame({
        "booking_id": [1, 2, 3, 4, 5, 6],
        "guest_id": [10, 10, 11, 12, 13, 14],
        "sailing_id": [1, 1, 1, 1, 1, 1],
        "cabin_category": ["balcony", "balcony", "BALCONY ", "inside", "suite", "balcony"],
        "booking_date": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-02-01", "2026-06-05", "2026-03-01", "2026-03-02"]),
        "guests": [2, 2, 2, 2, 2, 2],
        "price_paid": [1000.0, 1000.0, 1200.0, 800.0, -5.0, np.nan],
        "promo_code": [None] * 6,
        "channel": ["direct"] * 6,
        "source_market": ["US"] * 6,
        "status": ["confirmed"] * 6,
        "cancel_date": pd.NaT,
    })
    return b, sailings


def test_duplicates_removed():
    b, s = make_raw()
    clean, report = clean_bookings(b, s)
    assert report["duplicates_dropped"] == 1
    assert 2 not in clean["booking_id"].tolist()


def test_category_text_standardized():
    b, s = make_raw()
    clean, report = clean_bookings(b, s)
    assert set(clean["cabin_category"]) <= {"inside", "oceanview", "balcony", "suite"}
    assert report["category_text_fixed"] == 1


def test_bad_dates_and_prices_dropped():
    b, s = make_raw()
    clean, report = clean_bookings(b, s)
    assert report["booked_after_sailing_dropped"] == 1      # booking 4
    assert report["nonpositive_price_dropped"] == 1         # booking 5
    assert (clean["price_paid"] > 0).all()


def test_missing_price_imputed_and_flagged():
    b, s = make_raw()
    clean, report = clean_bookings(b, s)
    row = clean[clean["booking_id"] == 6].iloc[0]
    assert report["missing_price_imputed"] == 1
    assert row["price_imputed"]
    assert row["price_paid"] == 1100.0   # median of the other balcony prices (1000, 1200)
