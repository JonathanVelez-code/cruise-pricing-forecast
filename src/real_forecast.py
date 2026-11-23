"""Forecast REAL cruise-line revenue per passenger cruise day (PCD) from SEC filings + economic data.

Target: total revenue / passenger cruise days, per quarter, for Royal Caribbean, Carnival and
Norwegian (from src/sec_cruise_data.py). This is close to how cruise lines track yield.

Economic data (public, no API key):
- University of Michigan consumer sentiment (monthly)
- BLS CPI for airline fares (CUSR0000SETG01) and the unemployment rate (LNS14000000)
Each is averaged per calendar quarter and used with a ONE-QUARTER LAG (only what was known
before the quarter started).

Models (all predict next quarter's revenue per PCD):
- Baseline 1, seasonal naive: same quarter last year.
- Baseline 2, seasonal naive + trend: same quarter last year x last quarter's year-over-year growth.
- Model: damped trend + ridge adjustment. Growth = damp x last quarter's growth + a ridge regression on
  seasonality, company and the lagged economic indicators. Pooled across the three cruise lines.
  The ridge strength and damping are chosen by NESTED walk-forward (only on quarters before the one
  being predicted), so the test quarters never influence the settings.

Validation: walk-forward. For each quarter from 2024 on, train only on earlier quarters, predict,
then move one quarter ahead. COVID-19 quarters (Mar 2020 - Dec 2022) are excluded.
"""
import json
import urllib.request

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

from src import config

MACRO_FILE = config.OUTPUTS / "macro_monthly.csv"
SEC_FILE = config.OUTPUTS / "sec_cruise_quarterly.csv"
UA = {"User-Agent": "Mozilla/5.0 (compatible; cruise-pricing-forecast research)"}
BLS = {"CUSR0000SETG01": "airfare_cpi", "LNS14000000": "unemployment"}


def _get(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=60).read()


def fetch_macro() -> pd.DataFrame:
    """Download monthly economic data; fall back to the saved copy if a source is unavailable."""
    try:
        um = pd.read_csv(pd.io.common.BytesIO(_get("https://www.sca.isr.umich.edu/files/tbmics.csv")))
        um["date"] = pd.to_datetime(um["Month"] + " " + um["YYYY"].astype(str), format="%B %Y")
        frames = [um[["date", "ICS_ALL"]].rename(columns={"ICS_ALL": "consumer_sentiment"}).set_index("date")]
        rows = []
        for start, end in (("2015", "2024"), ("2025", str(pd.Timestamp.today().year))):  # BLS v1 allows 10 years per call
            body = json.dumps({"seriesid": list(BLS), "startyear": start, "endyear": end}).encode()
            j = json.loads(_get("https://api.bls.gov/publicAPI/v1/timeseries/data/", body, {"Content-Type": "application/json"}))
            for s in j["Results"]["series"]:
                for d in s["data"]:
                    # "-" marks a month BLS didn't publish (e.g. during a government shutdown)
                    if d["period"].startswith("M") and d["period"] != "M13" and d["value"].replace(".", "", 1).isdigit():
                        rows.append({"date": pd.Timestamp(f"{d['year']}-{d['period'][1:]}-01"),
                                     "series": BLS[s["seriesID"]], "value": float(d["value"])})
        bls = pd.DataFrame(rows).drop_duplicates(["date", "series"]).pivot(index="date", columns="series", values="value")
        frames.append(bls)
        macro = pd.concat(frames, axis=1).sort_index()
        macro = macro[macro.index >= "2014-01-01"]
        macro.to_csv(MACRO_FILE, date_format="%Y-%m-%d")
        return macro
    except Exception as e:  # offline or source down: reuse the committed copy
        if MACRO_FILE.exists():
            print("Using saved economic data:", e)
            return pd.read_csv(MACRO_FILE, parse_dates=["date"], index_col="date")
        raise


def build_panel(sec: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    q = macro.resample("QE").mean()
    q.index = q.index.to_period("Q")
    q["airfare_yoy"] = q["airfare_cpi"].pct_change(4)
    q["sentiment_yoy"] = q["consumer_sentiment"].pct_change(4)
    lagged = q[["consumer_sentiment", "airfare_yoy", "sentiment_yoy", "unemployment"]].shift(1)  # known before the quarter

    d = sec.copy()
    d["quarter_end"] = pd.to_datetime(d["quarter_end"])
    d["period"] = d["quarter_end"].dt.to_period("Q")
    d = d.sort_values(["company", "period"])
    d["y"] = d["revenue_per_pcd"]
    d.loc[d["covid_period"], "y"] = np.nan
    g = d.groupby("company")["y"]
    # Lags by calendar quarter (rows are consecutive quarters per company)
    d = d.set_index(["company", "period"])
    full = []
    for comp, part in d.groupby(level=0):
        part = part.droplevel(0)
        idx = pd.period_range(part.index.min(), part.index.max(), freq="Q")
        part = part.reindex(idx)
        part["company"] = comp
        part["lag1"], part["lag4"], part["lag5"] = part["y"].shift(1), part["y"].shift(4), part["y"].shift(5)
        full.append(part)
    p = pd.concat(full)
    p.index.name = "period"
    p = p.reset_index().join(lagged, on="period")
    p["growth"] = np.log(p["y"] / p["lag4"])                 # target: year-over-year growth
    p["trail_growth"] = np.log(p["lag1"] / p["lag5"])        # last quarter's year-over-year growth
    p["qtr"] = p["period"].dt.quarter
    return p


FEATURES_NUM = ["trail_growth", "consumer_sentiment", "airfare_yoy", "sentiment_yoy", "unemployment"]


def design(df: pd.DataFrame, mu=None, sd=None):
    x = df[FEATURES_NUM].astype(float)
    if mu is None:
        mu, sd = x.mean(), x.std().replace(0, 1)
    x = (x - mu) / sd
    for qn in (2, 3, 4):
        x[f"q{qn}"] = (df["qtr"] == qn).astype(float)
    for comp in ("Carnival", "Norwegian"):
        x[comp] = (df["company"] == comp).astype(float)
    return x.fillna(0), mu, sd


GRID = [(a, d) for a in (3, 10, 30, 100) for d in (0.5, 0.75, 1.0)]


def fit_predict(train, test, alpha, damp):
    """Predict year-over-year growth = damp x last quarter's growth + a ridge adjustment from economic data."""
    xtr, mu, sd = design(train)
    xte, _, _ = design(test, mu, sd)
    m = Ridge(alpha=alpha).fit(xtr, train["growth"] - damp * train["trail_growth"])
    return damp * test["trail_growth"].values + m.predict(xte)


def select_params(train, n_inner=4):
    """Nested walk-forward: score each setting on the last few quarters of the TRAINING data only."""
    periods = sorted(train["period"].unique())[-n_inner:]
    best, best_err = GRID[0], np.inf
    for alpha, damp in GRID:
        errs = []
        for vp in periods:
            tr, va = train[train["period"] < vp], train[train["period"] == vp]
            if len(tr) < 12 or va.empty:
                continue
            f = va["lag4"].values * np.exp(fit_predict(tr, va, alpha, damp))
            errs += list(np.abs(f - va["y"].values) / va["y"].values)
        if errs and np.mean(errs) < best_err:
            best, best_err = (alpha, damp), float(np.mean(errs))
    return best


def mape(a, f):
    a, f = np.asarray(a, float), np.asarray(f, float)
    return float(np.mean(np.abs(f - a) / a) * 100)


def run() -> dict | None:
    if not SEC_FILE.exists():
        return None
    sec = pd.read_csv(SEC_FILE)
    panel = build_panel(sec, fetch_macro())
    usable = panel.dropna(subset=["y", "lag4", "lag1", "lag5"]).copy()
    test_periods = sorted(p for p in usable["period"].unique() if p >= pd.Period("2024Q1"))

    usable["resid"] = usable["growth"] - usable["trail_growth"]
    preds, chosen = [], []
    for tp in test_periods:
        train = usable[usable["period"] < tp]
        test = usable[usable["period"] == tp]
        if len(train) < 15 or test.empty:
            continue
        alpha, damp = select_params(train)                       # chosen using ONLY data before tp
        chosen.append({"quarter": str(tp), "alpha": alpha, "damp": damp})
        g_hat = fit_predict(train, test, alpha, damp)
        for (_, r), gh in zip(test.iterrows(), g_hat):
            preds.append({"company": r["company"], "quarter": str(r["period"]), "actual": r["y"],
                          "seasonal_naive": r["lag4"], "naive_plus_trend": r["lag4"] * np.exp(r["trail_growth"]),
                          "model": r["lag4"] * np.exp(gh)})
    bt = pd.DataFrame(preds)
    rcl = bt[bt["company"] == "Royal Caribbean"]
    res = {
        "test_quarters": f"{bt['quarter'].min()} to {bt['quarter'].max()}",
        "test_rows_all_lines": len(bt), "test_rows_royal_caribbean": len(rcl),
        "mape_all_lines": {k: round(mape(bt["actual"], bt[k]), 2) for k in ("seasonal_naive", "naive_plus_trend", "model")},
        "mape_royal_caribbean": {k: round(mape(rcl["actual"], rcl[k]), 2) for k in ("seasonal_naive", "naive_plus_trend", "model")},
    }

    # Forecast the next, not-yet-reported Royal Caribbean quarter
    r_all = panel[panel["company"] == "Royal Caribbean"].sort_values("period")
    last = r_all.dropna(subset=["y"]).iloc[-1]
    nxt_p = last["period"] + 1
    row = {"company": "Royal Caribbean", "period": nxt_p, "qtr": nxt_p.quarter,
           "lag4": r_all.set_index("period")["y"].get(nxt_p - 4), "lag1": last["y"],
           "lag5": r_all.set_index("period")["y"].get(nxt_p - 5)}
    q = fetch_macro().resample("QE").mean()
    q.index = q.index.to_period("Q")
    q["airfare_yoy"] = q["airfare_cpi"].pct_change(4)
    q["sentiment_yoy"] = q["consumer_sentiment"].pct_change(4)
    for c in ("consumer_sentiment", "airfare_yoy", "sentiment_yoy", "unemployment"):
        row[c] = q[c].get(nxt_p - 1, np.nan)
    row["trail_growth"] = np.log(row["lag1"] / row["lag5"])
    nxt = pd.DataFrame([row])
    alpha, damp = select_params(usable)
    point = float(row["lag4"] * np.exp(fit_predict(usable, nxt, alpha, damp)[0]))
    xtr, mu, sd = design(usable)
    m = Ridge(alpha=alpha).fit(xtr, usable["growth"] - damp * usable["trail_growth"])
    err = (rcl["model"] / rcl["actual"] - 1).std() if len(rcl) > 2 else 0.03
    res["royal_caribbean_next_quarter"] = {
        "quarter": str(nxt_p), "forecast_revenue_per_pcd": round(point, 2),
        "range_80pct": [round(point * (1 - 1.28 * err), 2), round(point * (1 + 1.28 * err), 2)],
        "same_quarter_last_year": round(float(row["lag4"]), 2),
        "note": "Check against Royal Caribbean's next earnings release.",
    }
    coefs = dict(zip(xtr.columns, np.round(m.coef_, 4)))
    res["model_coefficients_standardized"] = {k: float(v) for k, v in coefs.items()}
    res["final_settings"] = {"ridge_alpha": alpha, "trend_damping": damp}
    res["settings_chosen_per_test_quarter"] = chosen

    bt.to_csv(config.OUTPUTS / "real_forecast_backtest.csv", index=False)
    (config.OUTPUTS / "real_forecast_results.json").write_text(json.dumps(res, indent=2))
    return {"results": res, "backtest": bt, "panel": panel}


if __name__ == "__main__":
    out = run()
    print(json.dumps(out["results"], indent=2))
    print(out["backtest"].round(1).to_string())
