"""SQL reporting layer: runs SQL directly on the clean Parquet files with DuckDB.

The same queries run in AWS Athena against S3 (see aws/athena_setup.sql); DuckDB lets the
pipeline run them locally with no cloud account. Each query in sql/ becomes a CSV for Power BI.
"""
import duckdb

from src import config

SQL_DIR = config.ROOT / "sql"


def run() -> dict:
    con = duckdb.connect()
    for name in ("bookings", "sailings", "cabin_inventory", "ships"):
        path = (config.DATA_CLEAN / f"{name}.parquet").as_posix()
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')")

    results = {}
    for f in sorted(SQL_DIR.glob("*.sql")):
        df = con.execute(f.read_text()).df()
        df.to_csv(config.POWERBI / f"sql_{f.stem}.csv", index=False)
        results[f.stem] = df
    return results


if __name__ == "__main__":
    for k, v in run().items():
        print(f"\n== {k} ({len(v)} rows)\n{v.head(8).to_string()}")
