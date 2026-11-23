"""Compare the synthetic data with real cruise-line numbers from SEC filings.

Load factor (industry "occupancy") = passenger cruise days / (2 x cabins x nights).
It can exceed 100% because some cabins hold 3-4 guests.

Real values: Royal Caribbean, Carnival and Norwegian quarterly filings, excluding the COVID-19
period (Mar 2020 - Dec 2022). See src/sec_cruise_data.py.
"""
import pandas as pd

from src import config

SEC_FILE = config.OUTPUTS / "sec_cruise_quarterly.csv"


def synthetic_load_factor(bookings: pd.DataFrame, sailings: pd.DataFrame, inventory: pd.DataFrame,
                          as_of=config.AS_OF) -> pd.DataFrame:
    s = sailings[sailings["sail_date"] <= as_of]
    conf = bookings[bookings["status"] == "confirmed"].merge(s[["sailing_id", "nights"]], on="sailing_id")
    pcd = (conf["guests"] * conf["nights"]).groupby(conf["sailing_id"]).sum()
    cabins = inventory.groupby("sailing_id")["cabins_available"].sum()
    s = s.assign(pcd=s["sailing_id"].map(pcd).fillna(0),
                 apcd=s["sailing_id"].map(cabins) * 2 * s["nights"],
                 quarter="Q" + s["sail_date"].dt.quarter.astype(str))
    q = s.groupby("quarter")[["pcd", "apcd"]].sum()
    return (q["pcd"] / q["apcd"] * 100).round(1).rename("synthetic").to_frame()


def run(tables: dict, as_of=config.AS_OF) -> pd.DataFrame | None:
    if not SEC_FILE.exists():
        return None
    sec = pd.read_csv(SEC_FILE)
    sec = sec[~sec["covid_period"]]
    real = sec.pivot_table(index="calendar_quarter", columns="company", values="occupancy_pct", aggfunc="mean").round(1)
    real.index.name = "quarter"
    out = synthetic_load_factor(tables["bookings"], tables["sailings"], tables["cabin_inventory"], as_of).join(real)
    out.loc["Year"] = out.mean().round(1)
    out.to_csv(config.OUTPUTS / "calibration_vs_sec.csv")
    return out


if __name__ == "__main__":
    t = {n: pd.read_parquet(config.DATA_CLEAN / f"{n}.parquet") for n in ("bookings", "sailings", "cabin_inventory")}
    print(run(t).to_string())
