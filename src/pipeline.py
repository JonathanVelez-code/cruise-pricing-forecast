"""Run the whole pipeline: generate -> clean (ETL) -> SQL reports -> forecast -> A/B test -> Power BI export -> charts.

    python -m src.pipeline                   # full run with the default snapshot date
    python -m src.pipeline --as-of 2026-12-01
    python -m src.pipeline --skip-generate   # reuse existing raw data

Every run appends to logs/pipeline.log and writes outputs/run_summary.json.
"""
import argparse
import json
import logging
import os
import shutil
import time

import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", help="Snapshot date (YYYY-MM-DD). Default: config.AS_OF")
    ap.add_argument("--skip-generate", action="store_true", help="Reuse data/raw instead of regenerating")
    args = ap.parse_args()
    if args.as_of:
        os.environ["AS_OF"] = args.as_of

    # Import after AS_OF is set so config picks it up
    from src import calibration, config, etl, experiment, export_powerbi, figures, forecast, generate_data, sql_reports

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(config.LOGS / "pipeline.log"), logging.StreamHandler()])
    log = logging.getLogger("pipeline")
    start = time.time()
    log.info("Pipeline start, as_of=%s", config.AS_OF.date())

    if not args.skip_generate:
        tables = generate_data.generate(config.AS_OF)
        generate_data.save(tables)
        log.info("Generated %s raw bookings", f"{len(tables['bookings']):,}")

    shutil.rmtree(config.DATA_CLEAN / "bookings_partitioned", ignore_errors=True)
    e = etl.run()
    log.info("ETL: %s clean rows, %s removed, %s prices imputed", f"{e['report']['clean_rows']:,}",
             f"{e['report']['rows_removed']:,}", f"{e['report']['missing_price_imputed']:,}")

    q = sql_reports.run()
    cal = calibration.run(e["tables"], config.AS_OF)
    if cal is not None:
        log.info("Load factor vs SEC filings (year): synthetic %.1f%%, Royal Caribbean %.1f%%",
                 cal.loc["Year", "synthetic"], cal.loc["Year", "Royal Caribbean"])
    log.info("SQL reports (DuckDB on Parquet): %s", ", ".join(f"{k} ({len(v)} rows)" for k, v in q.items()))

    f = forecast.run(e["tables"], config.AS_OF)
    bt = f["backtest"]["summary"]
    log.info("Forecast backtest MAPE: model %.1f%% vs baseline %.1f%%", bt["model_mape"], bt["baseline_mape"])

    x = experiment.run(f["rows"], config.AS_OF)["results"]
    log.info("A/B test: CUPED lift %.2f%% (p=%s). %s", x["cuped_lift_pct"], x["cuped_p_value"], x["decision"])

    export_powerbi.run(e["tables"], config.AS_OF)
    figures.run(e["tables"])
    log.info("Power BI tables and charts written")

    summary = {
        "as_of": str(config.AS_OF.date()),
        "runtime_seconds": round(time.time() - start, 1),
        "clean_bookings": e["report"]["clean_rows"],
        "forecast_model_mape": round(bt["model_mape"], 2),
        "forecast_baseline_mape": round(bt["baseline_mape"], 2),
        "open_sailing_recommendations": f["forecast"]["recommendation"].value_counts().to_dict(),
        "experiment_decision": x["decision"],
    }
    (config.OUTPUTS / "run_summary.json").write_text(json.dumps(summary, indent=2))
    log.info("Done in %.1fs", summary["runtime_seconds"])


if __name__ == "__main__":
    pd.options.mode.copy_on_write = True
    main()
