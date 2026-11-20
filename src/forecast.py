"""Demand forecast: predict final cabins booked per sailing and category.

Baseline: last year's pace. final = this year's on-the-books x (last year's final / last year's
on-the-books at the same horizon). If there's no last-year sailing, use the median pickup ratio.

Model: XGBoost predicting the final occupancy %, using what's on the books, last year's
pattern, price, season and ship. It's kept only if it beats the baseline on a time-based backtest.
"""
import json

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from src import config
from src.features import FEATURES, build_open_rows, build_training_rows


def mape(actual, pred) -> float:
    """Mean absolute % error, skipping rows where the actual is 0."""
    actual, pred = np.asarray(actual, float), np.asarray(pred, float)
    ok = actual > 0
    return float(np.mean(np.abs(pred[ok] - actual[ok]) / actual[ok]) * 100)


def wape(actual, pred) -> float:
    """Weighted absolute % error: total error / total actual. Robust for small categories."""
    actual, pred = np.asarray(actual, float), np.asarray(pred, float)
    return float(np.abs(pred - actual).sum() / actual.sum() * 100)


def baseline_predict(df: pd.DataFrame, pickup_medians: pd.Series) -> np.ndarray:
    ly_ratio = df["ly_final"] / df["ly_otb"].where(df["ly_otb"] > 0)
    fallback = df.set_index(["horizon", "cabin_category"]).index.map(pickup_medians).to_numpy(dtype=float)
    ratio = ly_ratio.fillna(pd.Series(fallback, index=df.index))
    pred = df["otb"] * ratio
    pred = np.where(df["otb"] == 0, df["ly_final"].fillna(0), pred)
    return np.clip(pred, 0, df["cabins_available"])


def pickup_ratios(train: pd.DataFrame) -> pd.Series:
    t = train[train["otb"] > 0]
    return (t["final"] / t["otb"]).groupby([t["horizon"], t["cabin_category"]]).median()


def make_model() -> XGBRegressor:
    return XGBRegressor(n_estimators=600, learning_rate=0.03, max_depth=5, subsample=0.8,
                        colsample_bytree=0.8, min_child_weight=5, random_state=config.SEED)


def backtest(rows: pd.DataFrame, as_of=config.AS_OF) -> dict:
    """Train on older sailings, test on the most recent departed ones.

    A gap of max(HORIZONS) days separates train and test, so no training outcome was
    unknown at the time a test forecast would have been made.
    """
    departed = rows[rows["departed"]]
    test_start = as_of - pd.DateOffset(months=config.TEST_MONTHS)
    train_end = test_start - pd.Timedelta(days=max(config.HORIZONS))
    train = departed[departed["sail_date"] < train_end]
    test = departed[departed["sail_date"] >= test_start].copy()

    model = make_model().fit(train[FEATURES], train["final_pct"])
    test["pred_model"] = np.clip(model.predict(test[FEATURES]), 0, 1) * test["cabins_available"]
    test["pred_baseline"] = baseline_predict(test, pickup_ratios(train))

    by_h = []
    for h, g in test.groupby("horizon"):
        by_h.append({"horizon": int(h),
                     "model_mape": mape(g["final"], g["pred_model"]),
                     "baseline_mape": mape(g["final"], g["pred_baseline"]),
                     "model_wape": wape(g["final"], g["pred_model"]),
                     "baseline_wape": wape(g["final"], g["pred_baseline"])})
    summary = {
        "train_sailings": f"{train['sail_date'].min().date()} to {train['sail_date'].max().date()}",
        "test_sailings": f"{test['sail_date'].min().date()} to {test['sail_date'].max().date()}",
        "train_rows": len(train), "test_rows": len(test),
        "model_mape": mape(test["final"], test["pred_model"]),
        "baseline_mape": mape(test["final"], test["pred_baseline"]),
        "model_wape": wape(test["final"], test["pred_model"]),
        "baseline_wape": wape(test["final"], test["pred_baseline"]),
        "model_mae_cabins": float(np.mean(np.abs(test["pred_model"] - test["final"]))),
        "baseline_mae_cabins": float(np.mean(np.abs(test["pred_baseline"] - test["final"]))),
        "by_horizon": by_h,
    }
    summary["mape_improvement_pct"] = (summary["baseline_mape"] - summary["model_mape"]) / summary["baseline_mape"] * 100
    importance = pd.DataFrame({"feature": FEATURES, "importance": model.feature_importances_}).sort_values("importance", ascending=False)
    return {"summary": summary, "test": test, "importance": importance}


def recommend(occ: float) -> str:
    if occ >= 0.97:
        return "Raise price"
    if occ <= 0.85:
        return "Promote / discount"
    return "Hold price"


def forecast_open(rows: pd.DataFrame, bookings, sailings, inventory, ships, as_of=config.AS_OF) -> pd.DataFrame:
    """Refit on every departed sailing, then forecast sailings in the next 180 days."""
    departed = rows[rows["departed"]]
    model = make_model().fit(departed[FEATURES], departed["final_pct"])
    open_rows = build_open_rows(bookings, sailings, inventory, as_of)
    open_rows["forecast_final"] = np.clip(model.predict(open_rows[FEATURES]), 0, 1) * open_rows["cabins_available"]
    open_rows["forecast_final"] = np.maximum(open_rows["forecast_final"], 0).round(0)
    open_rows["forecast_occupancy"] = open_rows["forecast_final"] / open_rows["cabins_available"]
    open_rows["baseline_final"] = baseline_predict(open_rows, pickup_ratios(departed)).round(0)
    open_rows["recommendation"] = open_rows["forecast_occupancy"].map(recommend)
    open_rows.loc[open_rows["horizon"] < 7, "recommendation"] = "Too close to sailing"
    out = open_rows.merge(ships[["ship_id", "ship_name"]], on="ship_id")
    cols = ["sailing_id", "ship_name", "sail_date", "nights", "cabin_category", "horizon", "cabins_available",
            "otb", "otb_pct", "ly_otb", "pace_vs_ly", "ly_final", "baseline_final", "forecast_final",
            "forecast_occupancy", "avg_price_otb", "recommendation"]
    return out[cols].rename(columns={"horizon": "days_to_sailing"}).sort_values(["sail_date", "ship_name", "cabin_category"])


def run(tables: dict, as_of=config.AS_OF) -> dict:
    b, s, inv, ships = tables["bookings"], tables["sailings"], tables["cabin_inventory"], tables["ships"]
    rows = build_training_rows(b, s, inv, as_of=as_of)
    bt = backtest(rows, as_of)
    fc = forecast_open(rows, b, s, inv, ships, as_of)

    (config.OUTPUTS / "forecast_backtest.json").write_text(json.dumps(bt["summary"], indent=2))
    bt["test"].to_csv(config.OUTPUTS / "backtest_predictions.csv", index=False)
    bt["importance"].to_csv(config.OUTPUTS / "feature_importance.csv", index=False)
    fc.to_csv(config.OUTPUTS / "forecast_open_sailings.csv", index=False)
    return {"rows": rows, "backtest": bt, "forecast": fc}


if __name__ == "__main__":
    from src import etl
    t = etl.run()["tables"]
    out = run(t)
    print(json.dumps(out["backtest"]["summary"], indent=2))
    print(out["forecast"]["recommendation"].value_counts())
