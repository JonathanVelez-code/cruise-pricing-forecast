"""Generate ~500K synthetic cruise bookings that behave like real cruise demand.

What makes the data realistic:
- Calibrated to real cruise-line SEC filings (see src/calibration.py): ships sail nearly full all
  year, with load factors around 107-112%, and seasonality shows mostly in PRICE and guest mix.
- Seasonal demand (peak in Mar, Jun-Jul, Dec; weak in Sep-Oct) and holiday weeks.
- Year-over-year growth in demand and price.
- A booking curve: most cabins book in the last few months; longer cruises and
  suites book earlier.
- Dynamic pricing: strong sailings get more expensive near departure, weak ones get discounted.
- Promotions (Wave season, Black Friday, past guest), channels, source markets.
- Cancellations (travel agents cancel most), resold cabins.
- A snapshot date (AS_OF): later bookings don't exist yet, so future sailings are partly booked.
- Messy rows on purpose (duplicates, missing prices, bad dates, inconsistent text) for the ETL step.
"""
import numpy as np
import pandas as pd

from src import config

SHIPS = pd.DataFrame([
    # ship_id, ship_name, brand, itinerary, trip_type, capacity by category, price premium
    (1, "Ocean Star", "Royal Caribbean International", "Eastern Caribbean", "long", 200, 118, 282, 41, 1.10),
    (2, "Island Dream", "Celebrity Cruises", "Western Caribbean", "long", 182, 109, 241, 32, 1.00),
    (3, "Sea Breeze", "Royal Caribbean International", "Bahamas", "short", 159, 91, 150, 20, 0.95),
    (4, "Coral Spirit", "Royal Caribbean International", "Bahamas & Cozumel", "short", 150, 82, 141, 20, 0.90),
], columns=["ship_id", "ship_name", "brand", "itinerary", "trip_type",
            "cap_inside", "cap_oceanview", "cap_balcony", "cap_suite", "price_premium"])

SEASON = {1: 0.95, 2: 1.00, 3: 1.12, 4: 1.00, 5: 0.92, 6: 1.10,
          7: 1.15, 8: 1.00, 9: 0.80, 10: 0.85, 11: 0.93, 12: 1.10}
YEAR_DEMAND = {2024: 1.00, 2025: 1.03, 2026: 1.06, 2027: 1.08}
YEAR_PRICE = {2024: 1.00, 2025: 1.04, 2026: 1.08, 2027: 1.11}
BASE_PER_NIGHT = {"inside": 110, "oceanview": 135, "balcony": 190, "suite": 450}
CAT_FILL_ADJ = {"inside": 0.00, "oceanview": -0.02, "balcony": 0.03, "suite": -0.04}
CAT_TIMING = {"inside": 0.85, "oceanview": 0.95, "balcony": 1.10, "suite": 1.35}
CHANNELS = ["direct", "travel_agent", "online_partner"]
CHANNEL_P = [0.45, 0.40, 0.15]
CANCEL_P = {"direct": 0.09, "travel_agent": 0.15, "online_partner": 0.12}
MARKETS = ["US", "Canada", "UK", "Mexico", "Brazil", "Germany", "Other"]
MARKET_P = [0.70, 0.08, 0.06, 0.05, 0.04, 0.03, 0.04]


def holiday_boost(d: pd.Series) -> np.ndarray:
    """Extra demand for sailings around major holidays."""
    m, day = d.dt.month.to_numpy(), d.dt.day.to_numpy()
    boost = np.ones(len(d))
    boost[((m == 12) & (day >= 20)) | ((m == 1) & (day <= 3))] *= 1.12   # Christmas / New Year
    boost[(m == 11) & (day >= 22) & (day <= 30)] *= 1.08                  # Thanksgiving
    boost[(m == 7) & (day <= 7)] *= 1.06                                  # July 4
    boost[((m == 3) & (day >= 7)) | ((m == 4) & (day <= 10))] *= 1.05      # Spring break
    return boost


def build_sailings() -> pd.DataFrame:
    rows = []
    for s in SHIPS.itertuples():
        if s.trip_type == "long":
            dates = pd.date_range(config.FIRST_SAIL + pd.Timedelta(days=4 + s.ship_id), config.LAST_SAIL, freq="7D")
            for d in dates:
                rows.append((s.ship_id, d, 7))
        else:
            fridays = pd.date_range(config.FIRST_SAIL + pd.Timedelta(days=3 + s.ship_id), config.LAST_SAIL, freq="7D")
            for d in fridays:
                rows.append((s.ship_id, d, 3))                       # 3-night weekend
                if d + pd.Timedelta(days=3) <= config.LAST_SAIL:
                    rows.append((s.ship_id, d + pd.Timedelta(days=3), 4))  # 4-night midweek
    sail = pd.DataFrame(rows, columns=["ship_id", "sail_date", "nights"])
    sail = sail.sort_values(["sail_date", "ship_id"]).reset_index(drop=True)
    sail.insert(0, "sailing_id", np.arange(1, len(sail) + 1))
    sail = sail.merge(SHIPS[["ship_id", "itinerary"]], on="ship_id")
    return sail.sort_values("sailing_id").reset_index(drop=True)


def generate(as_of: pd.Timestamp = config.AS_OF, seed: int = config.SEED) -> dict:
    rng = np.random.default_rng(seed)
    sailings = build_sailings()

    # Demand strength per sailing
    sd = sailings["sail_date"]
    demand = (sd.dt.month.map(SEASON).to_numpy()
              * holiday_boost(sd)
              * sd.dt.year.map(YEAR_DEMAND).to_numpy()
              * np.where(sailings["nights"] < 7, 1.02, 1.0)
              * rng.lognormal(0, 0.06, len(sailings)))
    sailings["demand_index"] = demand  # hidden truth, not exported to raw

    # One row per sailing x category ("unit")
    inv = sailings[["sailing_id", "ship_id"]].merge(SHIPS, on="ship_id")
    inv = inv.melt(id_vars=["sailing_id"], value_vars=[f"cap_{c}" for c in config.CATEGORIES],
                   var_name="cabin_category", value_name="cabins_available")
    inv["cabin_category"] = inv["cabin_category"].str.replace("cap_", "", regex=False)
    inv = inv.sort_values(["sailing_id", "cabin_category"]).reset_index(drop=True)

    units = inv.merge(sailings, on="sailing_id").merge(SHIPS[["ship_id", "trip_type", "price_premium"]], on="ship_id")
    # Calibrated to SEC filings: cruise lines sail nearly full all year (107-112% load factor) and
    # flex PRICE with the season, so cabin fill only moves a few points between low and peak weeks.
    fill = (0.955 + 0.12 * (units["demand_index"] - 1.0)
            + 0.5 * units["cabin_category"].map(CAT_FILL_ADJ) + rng.normal(0, 0.015, len(units)))
    units["final_fill"] = fill.clip(0.85, 1.0)
    n_confirmed = np.round(units["cabins_available"] * units["final_fill"]).astype(int)
    # Extra bookings that will cancel (cabins get resold), ~12% on top
    n_total = np.round(n_confirmed / 0.88).astype(int)

    # Expand to one row per booking
    idx = np.repeat(np.arange(len(units)), n_total)
    b = units.iloc[idx][["sailing_id", "cabin_category", "sail_date", "nights", "trip_type",
                         "price_premium", "demand_index", "cabins_available"]].reset_index(drop=True)
    n = len(b)

    # Booking timing (booking curve)
    mean_days = np.where(b["trip_type"] == "long", 125, 75) * b["cabin_category"].map(CAT_TIMING) * b["demand_index"]
    days_out = rng.gamma(2.0, mean_days / 2.0).clip(1, 540).astype(int)
    b["booking_date"] = b["sail_date"] - pd.to_timedelta(days_out, unit="D")

    # Channel, market, guests
    b["channel"] = rng.choice(CHANNELS, n, p=CHANNEL_P)
    b["source_market"] = rng.choice(MARKETS, n, p=MARKET_P)
    # More families (3rd/4th guests) in summer and holiday weeks, which is why real load factors peak in Q3
    sm = b["sail_date"].dt.month
    family_season = (sm.between(6, 8) | (holiday_boost(b["sail_date"]) > 1)).to_numpy()
    g_family = rng.choice([1, 2, 3, 4], n, p=[0.04, 0.64, 0.19, 0.13])
    g_normal = rng.choice([1, 2, 3, 4], n, p=[0.06, 0.77, 0.11, 0.06])
    b["guests"] = np.where(family_season, g_family, g_normal)

    # Promotions
    bm, bd = b["booking_date"].dt.month, b["booking_date"].dt.day
    wave = bm.between(1, 3).to_numpy()
    black_friday = (((bm == 11) & (bd >= 20)) | ((bm == 12) & (bd <= 2))).to_numpy()
    r = rng.random(n)
    promo = np.full(n, None, dtype=object)
    promo[wave & (r < 0.15)] = "WAVE10"
    promo[black_friday & (r < 0.30)] = "BLACKFRIDAY15"
    promo[(promo == None) & (rng.random(n) < 0.03)] = "PASTGUEST5"  # noqa: E711
    discount = pd.Series(promo).map({"WAVE10": 0.90, "BLACKFRIDAY15": 0.85, "PASTGUEST5": 0.95}).fillna(1.0).to_numpy()
    b["promo_code"] = promo

    # Price: base x nights x season x year x dynamic pricing x promo x guests
    late = 1 - np.minimum(days_out, 365) / 365
    strength = np.clip((b["demand_index"] - 1.0) / 0.25, -1, 1)
    dynamic = 1 + 0.20 * late * strength
    guest_mult = b["guests"].map({1: 1.0, 2: 1.0, 3: 1.25, 4: 1.45}).to_numpy()
    price = (b["cabin_category"].map(BASE_PER_NIGHT) * b["nights"] * b["price_premium"]
             * b["demand_index"] ** 1.3 * b["sail_date"].dt.year.map(YEAR_PRICE)
             * dynamic * discount * guest_mult * rng.lognormal(0, 0.05, n))
    b["price_paid"] = price.round(2)

    # Cancellations
    cancel_p = b["channel"].map(CANCEL_P).to_numpy()
    cancelled = rng.random(n) < cancel_p
    cancel_after = (rng.random(n) * (days_out - 1)).astype(int)
    b["cancel_date"] = pd.NaT
    b.loc[cancelled, "cancel_date"] = b.loc[cancelled, "booking_date"] + pd.to_timedelta(cancel_after[cancelled], unit="D")
    b["status"] = np.where(cancelled, "cancelled", "confirmed")

    # Snapshot at AS_OF: future bookings don't exist; future cancellations haven't happened
    b = b[b["booking_date"] <= as_of].copy()
    future_cancel = b["cancel_date"] > as_of
    b.loc[future_cancel, "cancel_date"] = pd.NaT
    b.loc[future_cancel, "status"] = "confirmed"

    b = b.sort_values(["booking_date", "sailing_id"]).reset_index(drop=True)
    b.insert(0, "booking_id", np.arange(1, len(b) + 1))
    b.insert(1, "guest_id", rng.integers(1, 350_000, len(b)))
    bookings = b[["booking_id", "guest_id", "sailing_id", "cabin_category", "booking_date", "guests",
                  "price_paid", "promo_code", "channel", "source_market", "status", "cancel_date"]].copy()

    bookings = add_messy_rows(bookings, sailings, rng)

    ships_out = SHIPS[["ship_id", "ship_name", "brand", "itinerary", "trip_type"]]
    sail_out = sailings[["sailing_id", "ship_id", "sail_date", "nights", "itinerary"]]
    return {"ships": ships_out, "sailings": sail_out, "cabin_inventory": inv, "bookings": bookings}


def add_messy_rows(b: pd.DataFrame, sailings: pd.DataFrame, rng) -> pd.DataFrame:
    """Inject realistic data-quality problems for the ETL step to catch."""
    b = b.copy()
    n = len(b)
    # 1) Exact duplicates (same booking loaded twice), new booking_id
    dup = b.sample(frac=0.002, random_state=1).copy()
    dup["booking_id"] = np.arange(b["booking_id"].max() + 1, b["booking_id"].max() + 1 + len(dup))
    # 2) Missing prices
    b.loc[rng.choice(n, int(n * 0.001), replace=False), "price_paid"] = np.nan
    # 3) Zero or negative prices
    b.loc[rng.choice(n, 30, replace=False), "price_paid"] = rng.choice([0.0, -1.0, -250.0], 30)
    # 4) Booking dated after the sailing
    sail_dates = b["sailing_id"].map(sailings.set_index("sailing_id")["sail_date"])
    bad = rng.choice(np.flatnonzero((sail_dates < config.AS_OF).to_numpy()), 40, replace=False)
    b.loc[bad, "booking_date"] = sail_dates.iloc[bad].to_numpy() + pd.to_timedelta(rng.integers(1, 10, 40), unit="D")
    # 5) Inconsistent category text
    messy = rng.choice(n, int(n * 0.005), replace=False)
    b.loc[messy, "cabin_category"] = b.loc[messy, "cabin_category"].map(
        lambda s: rng.choice([s.upper(), s.title(), s + " "]))
    return pd.concat([b, dup], ignore_index=True)


def save(tables: dict) -> None:
    for name, df in tables.items():
        df.to_csv(config.DATA_RAW / f"{name}.csv", index=False, date_format="%Y-%m-%d")


if __name__ == "__main__":
    t = generate()
    save(t)
    for k, v in t.items():
        print(f"{k}: {len(v):,} rows")
