import numpy as np
import pandas as pd

from src.real_forecast import build_panel, mape


def toy():
    q = pd.period_range("2017Q1", "2019Q4", freq="Q")
    sec = pd.DataFrame({
        "company": "Royal Caribbean",
        "quarter_end": q.to_timestamp(how="end").normalize(),
        "revenue_per_pcd": np.linspace(200, 255, len(q)),
        "covid_period": False,
    })
    months = pd.date_range("2015-01-01", "2020-12-01", freq="MS")
    macro = pd.DataFrame({"consumer_sentiment": 90.0, "airfare_cpi": np.linspace(250, 280, len(months)),
                          "unemployment": 4.0}, index=months)
    return sec, macro


def test_lags_line_up_by_quarter():
    p = build_panel(*toy()).set_index("period")
    row = p.loc[pd.Period("2019Q1")]
    assert row["lag4"] == p.loc[pd.Period("2018Q1"), "y"]
    assert row["lag1"] == p.loc[pd.Period("2018Q4"), "y"]


def test_economic_data_is_lagged_one_quarter():
    sec, macro = toy()
    macro["unemployment"] = np.arange(len(macro), dtype=float)   # a value that changes every month
    p = build_panel(sec, macro).set_index("period")
    q = macro["unemployment"].resample("QE").mean()
    q.index = q.index.to_period("Q")
    # The 2019Q1 row must use 2018Q4's unemployment (known before the quarter), not 2019Q1's
    assert p.loc[pd.Period("2019Q1"), "unemployment"] == q[pd.Period("2018Q4")]
    assert p.loc[pd.Period("2019Q1"), "unemployment"] != q[pd.Period("2019Q1")]


def test_covid_quarters_are_excluded():
    sec, macro = toy()
    sec.loc[sec["quarter_end"].dt.year == 2018, "covid_period"] = True
    p = build_panel(sec, macro).set_index("period")
    assert np.isnan(p.loc[pd.Period("2018Q2"), "y"])
    assert np.isnan(p.loc[pd.Period("2019Q2"), "lag4"])   # can't compare against an excluded quarter


def test_mape():
    assert mape([100, 200], [110, 180]) == 10.0
