import numpy as np
import pandas as pd
import pytest

from src.features import on_the_books
from src.forecast import mape, wape


def test_on_the_books_respects_cancellations():
    sail = pd.Timestamp("2026-06-01")
    b = pd.DataFrame({
        "booking_id": [1, 2, 3, 4],
        "sailing_id": [1, 1, 1, 1],
        "cabin_category": ["inside"] * 4,
        "sail_date": [sail] * 4,
        "booking_date": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-05-25", "2026-01-15"]),
        "cancel_date": pd.to_datetime([None, "2026-03-01", None, "2026-05-20"]),
        "price_paid": [100.0, 200.0, 300.0, 400.0],
    })
    # 30 days out = 2026-05-02:
    #   1 booked, never cancelled              -> on books
    #   2 cancelled 03-01 (before cutoff)      -> not on books
    #   3 booked 05-25 (after cutoff)          -> not on books
    #   4 cancels 05-20 (after cutoff)         -> still on books at the cutoff
    out = on_the_books(b, None, 30)
    assert out["otb"].iloc[0] == 2
    assert out["otb_revenue"].iloc[0] == 500.0


def test_mape_skips_zero_actuals():
    assert mape([100, 0, 50], [110, 5, 45]) == pytest.approx(10.0)


def test_wape():
    assert wape([100, 100], [90, 120]) == pytest.approx(15.0)


def test_perfect_forecast_has_zero_error():
    a = np.array([10, 20, 30])
    assert mape(a, a) == 0 and wape(a, a) == 0
