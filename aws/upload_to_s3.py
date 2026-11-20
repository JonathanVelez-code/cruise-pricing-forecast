"""Upload the clean, partitioned Parquet data to S3 so Athena can query it.

Prerequisites (one time):
  1. An AWS account (the free tier covers this project's size).
  2. pip install boto3
  3. Credentials configured: run `aws configure`, or set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY.
     Never commit credentials to Git.
  4. A bucket you own, e.g. cruise-pricing-<your-initials>.

Usage:
  python aws/upload_to_s3.py --bucket cruise-pricing-xyz [--prefix cruise] [--region us-east-1]
Then run aws/athena_setup.sql in the Athena console (replace the bucket name).
"""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"


def main():
    import boto3  # imported here so the rest of the project doesn't need it

    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--prefix", default="cruise")
    ap.add_argument("--region", default="us-east-1")
    args = ap.parse_args()
    s3 = boto3.client("s3", region_name=args.region)

    uploads = []
    for f in (CLEAN / "bookings_partitioned").rglob("*.parquet"):
        rel = f.relative_to(CLEAN / "bookings_partitioned").as_posix()    # sail_year=2026/xxx.parquet
        uploads.append((f, f"{args.prefix}/bookings/{rel}"))
    for name in ("sailings", "ships", "cabin_inventory"):
        uploads.append((CLEAN / f"{name}.parquet", f"{args.prefix}/{name}/{name}.parquet"))

    for path, key in uploads:
        s3.upload_file(str(path), args.bucket, key)
        print(f"uploaded s3://{args.bucket}/{key}")


if __name__ == "__main__":
    main()
