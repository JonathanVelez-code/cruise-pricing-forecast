"""Export a star schema of CSVs for the Power BI dashboard (powerbi/CruiseRevenue.pbip)."""
import shutil

import numpy as np
import pandas as pd

from src import config


def date_dim(start, end) -> pd.DataFrame:
    d = pd.DataFrame({"date": pd.date_range(start, end, freq="D")})
    d["year"] = d["date"].dt.year
    d["quarter"] = "Q" + d["date"].dt.quarter.astype(str)
    d["month"] = d["date"].dt.month
    d["month_name"] = d["date"].dt.strftime("%b")
    d["year_month"] = d["date"].dt.strftime("%Y-%m")
    d["week_of_year"] = d["date"].dt.isocalendar().week.astype(int)
    return d


def pace_curves(bookings: pd.DataFrame, sailings: pd.DataFrame, inventory: pd.DataFrame) -> pd.DataFrame:
    """Cumulative confirmed cabins by weeks before sailing, per sailing (for the pace chart)."""
    conf = bookings[bookings["status"] == "confirmed"].copy()
    conf["weeks_out"] = (conf["days_out"] // 7).clip(upper=52)
    g = conf.groupby(["sailing_id", "weeks_out"]).size().rename("cabins").reset_index()
    full = pd.MultiIndex.from_product([sailings["sailing_id"], range(0, 53)], names=["sailing_id", "weeks_out"])
    g = g.set_index(["sailing_id", "weeks_out"]).reindex(full, fill_value=0).reset_index()
    g = g.sort_values(["sailing_id", "weeks_out"], ascending=[True, False])
    g["cumulative_cabins"] = g.groupby("sailing_id")["cabins"].cumsum()
    cap = inventory.groupby("sailing_id")["cabins_available"].sum()
    g["cumulative_occupancy"] = g["cumulative_cabins"] / g["sailing_id"].map(cap)
    return g


def run(tables: dict, as_of=config.AS_OF) -> None:
    out = config.POWERBI
    b, s, inv, ships = tables["bookings"], tables["sailings"], tables["cabin_inventory"], tables["ships"]

    fact = b[["booking_id", "guest_id", "sailing_id", "cabin_category", "booking_date", "days_out", "guests",
              "price_paid", "price_imputed", "promo_code", "channel", "source_market", "status", "cancel_date"]]
    fact.to_csv(out / "fact_bookings.csv", index=False, date_format="%Y-%m-%d")

    dim_s = s.merge(ships, on=["ship_id", "itinerary"], how="left")
    dim_s["departed"] = dim_s["sail_date"] <= as_of
    dim_s["sail_year"] = dim_s["sail_date"].dt.year
    dim_s["sail_month"] = dim_s["sail_date"].dt.month
    dim_s.to_csv(out / "dim_sailing.csv", index=False, date_format="%Y-%m-%d")
    ships.to_csv(out / "dim_ship.csv", index=False)
    inv.to_csv(out / "fact_cabin_inventory.csv", index=False)
    date_dim(min(b["booking_date"].min(), s["sail_date"].min()), s["sail_date"].max()).to_csv(
        out / "dim_date.csv", index=False, date_format="%Y-%m-%d")
    pace_curves(b, s, inv).to_csv(out / "pace_curves.csv", index=False)

    for f in ("forecast_open_sailings.csv", "feature_importance.csv", "experiment_sailings.csv",
              "sec_cruise_quarterly.csv", "calibration_vs_sec.csv", "real_forecast_backtest.csv"):
        if (config.OUTPUTS / f).exists():
            shutil.copy(config.OUTPUTS / f, out / f)
    bt = pd.read_json(config.OUTPUTS / "forecast_backtest.json", typ="series")
    pd.DataFrame(bt["by_horizon"]).to_csv(out / "backtest_by_horizon.csv", index=False)
    pred = pd.read_csv(config.OUTPUTS / "backtest_predictions.csv", parse_dates=["sail_date"])
    pred[["sailing_id", "sail_date", "cabin_category", "horizon", "cabins_available", "otb", "final",
          "pred_baseline", "pred_model"]].to_csv(out / "backtest_predictions.csv", index=False, date_format="%Y-%m-%d")


if __name__ == "__main__":
    t = {n: pd.read_parquet(config.DATA_CLEAN / f"{n}.parquet") for n in ("bookings", "sailings", "cabin_inventory", "ships")}
    run(t)
    print(sorted(p.name for p in config.POWERBI.iterdir()))
