"""Extract raw CSVs, clean and validate them, and load clean Parquet files.

Checks (each one is counted in the data-quality report):
- inconsistent category text   -> standardized ("BALCONY " -> "balcony")
- unknown categories           -> dropped
- exact duplicate bookings     -> dropped (keep the first)
- booking dated after sailing  -> dropped
- zero or negative price       -> dropped
- missing price                -> filled with the median for that sailing and category, and flagged
- cancelled with no cancel date, or confirmed with one -> fixed to match status
"""
import json

import pandas as pd

from src import config

DATE_COLS = {"bookings": ["booking_date", "cancel_date"], "sailings": ["sail_date"]}


def extract() -> dict:
    tables = {}
    for name in ("ships", "sailings", "cabin_inventory", "bookings"):
        tables[name] = pd.read_csv(config.DATA_RAW / f"{name}.csv", parse_dates=DATE_COLS.get(name, []))
    return tables


def clean_bookings(b: pd.DataFrame, sailings: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    report = {"raw_rows": len(b)}
    b = b.copy()

    # Standardize text
    before = b["cabin_category"].copy()
    b["cabin_category"] = b["cabin_category"].astype(str).str.strip().str.lower()
    report["category_text_fixed"] = int((before != b["cabin_category"]).sum())
    unknown = ~b["cabin_category"].isin(config.CATEGORIES)
    report["unknown_category_dropped"] = int(unknown.sum())
    b = b[~unknown]

    # Duplicates: same booking loaded twice (everything identical except booking_id)
    key = [c for c in b.columns if c != "booking_id"]
    dups = b.duplicated(subset=key, keep="first")
    report["duplicates_dropped"] = int(dups.sum())
    b = b[~dups]

    # Dates must make sense
    b = b.merge(sailings[["sailing_id", "sail_date"]], on="sailing_id", how="left")
    no_sailing = b["sail_date"].isna()
    report["unknown_sailing_dropped"] = int(no_sailing.sum())
    b = b[~no_sailing]
    after_sail = b["booking_date"] > b["sail_date"]
    report["booked_after_sailing_dropped"] = int(after_sail.sum())
    b = b[~after_sail]

    # Prices
    bad_price = b["price_paid"] <= 0
    report["nonpositive_price_dropped"] = int(bad_price.sum())
    b = b[~bad_price].copy()
    missing = b["price_paid"].isna()
    report["missing_price_imputed"] = int(missing.sum())
    # Median for the same sailing and category; if there is none, the category median overall
    median = (b.groupby(["sailing_id", "cabin_category"])["price_paid"].transform("median")
              .fillna(b.groupby("cabin_category")["price_paid"].transform("median")))
    b["price_imputed"] = missing
    b.loc[missing, "price_paid"] = median[missing]
    report["missing_price_unfillable_dropped"] = int(b["price_paid"].isna().sum())
    b = b[b["price_paid"].notna()]

    # Status and cancel date must agree
    mismatch = ((b["status"] == "cancelled") & b["cancel_date"].isna()) | ((b["status"] == "confirmed") & b["cancel_date"].notna())
    report["status_cancel_date_mismatch"] = int(mismatch.sum())
    b.loc[(b["status"] == "confirmed"), "cancel_date"] = pd.NaT

    # Helpful derived columns
    b["days_out"] = (b["sail_date"] - b["booking_date"]).dt.days
    b["is_cancelled"] = b["status"].eq("cancelled")
    b["sail_year"] = b["sail_date"].dt.year
    b = b.drop(columns=["sail_date"])

    report["clean_rows"] = len(b)
    report["rows_removed"] = report["raw_rows"] - report["clean_rows"]
    return b.reset_index(drop=True), report


def load(tables: dict) -> None:
    for name, df in tables.items():
        df.to_parquet(config.DATA_CLEAN / f"{name}.parquet", index=False)
    # Partitioned copy, the layout Athena reads from S3 (one folder per sailing year).
    # Millisecond timestamps, because Athena can't read pandas' default nanoseconds.
    tables["bookings"].to_parquet(config.DATA_CLEAN / "bookings_partitioned", partition_cols=["sail_year"], index=False,
                                  coerce_timestamps="ms", allow_truncated_timestamps=True)


def write_report(report: dict) -> None:
    (config.OUTPUTS / "data_quality_report.json").write_text(json.dumps(report, indent=2))
    lines = ["# Data quality report", "", "| Check | Rows |", "|---|---:|"]
    lines += [f"| {k.replace('_', ' ')} | {v:,} |" for k, v in report.items()]
    (config.OUTPUTS / "data_quality_report.md").write_text("\n".join(lines) + "\n")


def run() -> dict:
    t = extract()
    t["bookings"], report = clean_bookings(t["bookings"], t["sailings"])
    load(t)
    write_report(report)
    return {"tables": t, "report": report}


if __name__ == "__main__":
    out = run()
    print(json.dumps(out["report"], indent=2))
