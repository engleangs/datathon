#!/usr/bin/env python3
"""Upload District Court decision PDFs from a local folder to the S3 landing bucket.

You download the PDFs by hand first (see README, "Get the documents").
This script does NOT crawl any website.

Usage:
    python scripts/upload_judgments.py --bucket $(terraform -chdir=terraform output -raw s3_bucket)
    python scripts/upload_judgments.py --bucket my-bucket --folder data/judgments --dry-run
"""

import argparse
import re
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

PREFIX = "judgments/"
MAX_BYTES = 100 * 1024 * 1024  # AI functions reject files of 100 MB or more


def safe_key(name: str) -> str:
    """Keep S3 keys simple: letters, digits, dot, dash, underscore."""
    stem, dot, ext = name.rpartition(".")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_")
    return f"{PREFIX}{stem}.{ext.lower()}"


def exists(s3, bucket: str, key: str) -> bool:
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as err:
        if err.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--folder", default="data/judgments")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    folder = Path(args.folder)
    pdfs = sorted(p for p in folder.glob("*") if p.suffix.lower() == ".pdf")
    if not pdfs:
        print(f"No PDFs in {folder}. Download some first (see README).")
        return 1

    s3 = boto3.client("s3")
    uploaded = skipped = rejected = 0

    for pdf in pdfs:
        key = safe_key(pdf.name)
        size = pdf.stat().st_size

        if size >= MAX_BYTES:
            print(f"REJECT  {pdf.name}: {size / 1e6:.1f} MB is over the 100 MB limit")
            rejected += 1
            continue
        with pdf.open("rb") as fh:
            if fh.read(5) != b"%PDF-":
                print(f"REJECT  {pdf.name}: not a real PDF (maybe an HTML error page)")
                rejected += 1
                continue

        if exists(s3, args.bucket, key):
            print(f"SKIP    {key} (already in S3)")
            skipped += 1
            continue

        if args.dry_run:
            print(f"DRY-RUN {pdf.name} -> s3://{args.bucket}/{key}")
        else:
            s3.upload_file(
                str(pdf), args.bucket, key,
                ExtraArgs={"ServerSideEncryption": "AES256", "ContentType": "application/pdf"},
            )
            print(f"UPLOAD  {pdf.name} -> s3://{args.bucket}/{key}")
        uploaded += 1

    print(f"\nDone. uploaded={uploaded} skipped={skipped} rejected={rejected}")
    print("Next: CALL NZDC_DEV.RAW.PROCESS_NEW_DECISIONS();")
    return 0


if __name__ == "__main__":
    sys.exit(main())
