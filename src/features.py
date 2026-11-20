"""Build forecasting features: what was "on the books" N days before each sailing.

One row = one sailing x cabin category x horizon (days before sailing).
"On the books" (OTB) at a cutoff date = bookings made by then that hadn't cancelled by then.
"""
import numpy as np
import pandas as pd

from src import config


def holiday_flag(d: pd.Series) -> pd.Series:
    m, day = d.dt.month, d.dt.day
    return (((m == 12) & (day >= 20)) | ((m == 1) & (day <= 3))
            | ((m == 11) & day.between(22, 30))
            | ((m == 7) & (day <= 7))
            | ((m == 3) & (day >= 7)) | ((m == 4) & (day <= 10))).astype(int)


def on_the_books(bookings: pd.DataFrame, sailings: pd.DataFrame, horizon_days: pd.Series | int,
                 cutoff: pd.Series | None = None) -> pd.DataFrame:
    """Cabins and revenue on the books at a cutoff date, per sailing and category.

    bookings must include sail_date. If cutoff is None, cutoff = sail_date - horizon_days.
    """
    b = bookings
    cut = b["sail_date"] - pd.to_timedelta(horizon_days, unit="D") if cutoff is None else cutoff
    on_books = (b["booking_date"] <= cut) & (b["cancel_date"].isna() | (b["cancel_date"] > cut))
    g = (b[on_books].groupby(["sailing_id", "cabin_category"])
         .agg(otb=("booking_id", "count"), otb_revenue=("price_paid", "sum"), avg_price_otb=("price_paid", "mean"))
         .reset_index())
    return g


def final_bookings(bookings: pd.DataFrame) -> pd.DataFrame:
    """Final confirmed cabins and revenue per sailing and category (only meaningful once departed)."""
    conf = bookings[bookings["status"] == "confirmed"]
    return (conf.groupby(["sailing_id", "cabin_category"])
            .agg(final=("booking_id", "count"), final_revenue=("price_paid", "sum")).reset_index())


def units_frame(sailings: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    u = inventory.merge(sailings, on="sailing_id")
    u["month"] = u["sail_date"].dt.month
    u["week_of_year"] = u["sail_date"].dt.isocalendar().week.astype(int)
    u["is_holiday"] = holiday_flag(u["sail_date"])
    u["category_code"] = u["cabin_category"].map({c: i for i, c in enumerate(config.CATEGORIES)})
    return u


def last_year_map(sailings: pd.DataFrame) -> pd.DataFrame:
    """Match each sailing to the same ship's sailing ~52 weeks earlier with the same length."""
    s = sailings[["sailing_id", "ship_id", "nights", "sail_date"]].copy()
    s["target_date"] = s["sail_date"] - pd.Timedelta(days=364)
    prev = s[["sailing_id", "ship_id", "nights", "sail_date"]].rename(
        columns={"sailing_id": "ly_sailing_id", "sail_date": "ly_sail_date"})
    out = []
    for (ship, nights), grp in s.groupby(["ship_id", "nights"]):
        p = prev[(prev.ship_id == ship) & (prev.nights == nights)].sort_values("ly_sail_date")
        m = pd.merge_asof(grp.sort_values("target_date"), p[["ly_sailing_id", "ly_sail_date"]],
                          left_on="target_date", right_on="ly_sail_date",
                          direction="nearest", tolerance=pd.Timedelta(days=4))
        out.append(m[["sailing_id", "ly_sailing_id"]])
    return pd.concat(out, ignore_index=True)


def build_training_rows(bookings, sailings, inventory, horizons=config.HORIZONS, as_of=config.AS_OF) -> pd.DataFrame:
    """Snapshot rows for departed sailings, with the final outcome as the target."""
    b = bookings.merge(sailings[["sailing_id", "sail_date"]], on="sailing_id")
    units = units_frame(sailings, inventory)
    final = final_bookings(b)
    ly = last_year_map(sailings)

    rows = []
    for h in horizons:
        otb = on_the_books(b, sailings, h)
        r = units.merge(otb, on=["sailing_id", "cabin_category"], how="left")
        r["horizon"] = h
        rows.append(r)
    df = pd.concat(rows, ignore_index=True)
    df[["otb", "otb_revenue"]] = df[["otb", "otb_revenue"]].fillna(0)
    df = df.merge(final, on=["sailing_id", "cabin_category"], how="left")
    df[["final", "final_revenue"]] = df[["final", "final_revenue"]].fillna(0)
    df = add_last_year(df, ly)
    df["departed"] = df["sail_date"] <= as_of
    return add_ratios(df)


def build_open_rows(bookings, sailings, inventory, as_of=config.AS_OF, max_days=180) -> pd.DataFrame:
    """Rows for sailings that haven't departed: what's on the books today."""
    b = bookings.merge(sailings[["sailing_id", "sail_date"]], on="sailing_id")
    units = units_frame(sailings, inventory)
    open_units = units[(units["sail_date"] > as_of) & (units["sail_date"] <= as_of + pd.Timedelta(days=max_days))].copy()
    open_units["horizon"] = (open_units["sail_date"] - as_of).dt.days
    otb = on_the_books(b, sailings, 0, cutoff=pd.Series(as_of, index=b.index))
    df = open_units.merge(otb, on=["sailing_id", "cabin_category"], how="left")
    df[["otb", "otb_revenue"]] = df[["otb", "otb_revenue"]].fillna(0)

    # Last year's OTB at the same horizon, and its final result
    ly = last_year_map(sailings)
    df = df.merge(ly, on="sailing_id", how="left")
    ly_rows = []
    b_ly = b[b["sailing_id"].isin(df["ly_sailing_id"].dropna())]  # only last year's sailings, for speed
    for h in sorted(df["horizon"].unique()):
        o = on_the_books(b_ly, sailings, int(h)).rename(columns={"sailing_id": "ly_sailing_id", "otb": "ly_otb"})
        o["horizon"] = h
        ly_rows.append(o[["ly_sailing_id", "cabin_category", "horizon", "ly_otb"]])
    ly_otb = pd.concat(ly_rows, ignore_index=True)
    df = df.merge(ly_otb, on=["ly_sailing_id", "cabin_category", "horizon"], how="left")
    fin = final_bookings(b).rename(columns={"sailing_id": "ly_sailing_id", "final": "ly_final"})[["ly_sailing_id", "cabin_category", "ly_final"]]
    df = df.merge(fin, on=["ly_sailing_id", "cabin_category"], how="left")
    has_ly = df["ly_sailing_id"].notna()
    df.loc[has_ly, ["ly_otb", "ly_final"]] = df.loc[has_ly, ["ly_otb", "ly_final"]].fillna(0)
    return add_ratios(df)


def add_last_year(df: pd.DataFrame, ly: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(ly, on="sailing_id", how="left")
    ly_vals = df[["sailing_id", "cabin_category", "horizon", "otb", "final"]].rename(
        columns={"sailing_id": "ly_sailing_id", "otb": "ly_otb", "final": "ly_final"})
    return df.merge(ly_vals, on=["ly_sailing_id", "cabin_category", "horizon"], how="left")


def add_ratios(df: pd.DataFrame) -> pd.DataFrame:
    df["otb_pct"] = df["otb"] / df["cabins_available"]
    df["ly_otb_pct"] = df["ly_otb"] / df["cabins_available"]
    df["ly_final_pct"] = df["ly_final"] / df["cabins_available"]
    df["pace_vs_ly"] = np.where(df["ly_otb"] > 0, df["otb"] / df["ly_otb"].where(df["ly_otb"] > 0), np.nan)
    if "final" in df:
        df["final_pct"] = df["final"] / df["cabins_available"]
    return df


FEATURES = ["horizon", "otb_pct", "avg_price_otb", "ly_otb_pct", "ly_final_pct", "pace_vs_ly",
            "cabins_available", "category_code", "ship_id", "nights", "month", "week_of_year", "is_holiday"]
