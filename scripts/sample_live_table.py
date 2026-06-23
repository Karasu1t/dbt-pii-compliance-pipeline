"""Prints a live sample of rows from a table, exactly as any ordinary query
would see them today.

This script makes no judgment — it only fetches and prints. Whether the
printed values reveal residual re-identification risk despite masking, or
contain a PII pattern the original classification missed, is exactly the
kind of judgment /pii-scan's STEP 8/9 brings a human + Claude back in for;
a plain script can't tell "this generalized postal code still isolates one
row" from "this one doesn't."
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "catalog"))
from apply_tags import get_connection_params  # noqa: E402
from databricks import sql  # noqa: E402


def fetch_sample(table_fqn: str, limit: int) -> tuple[list[str], list[tuple]]:
    conn_params = get_connection_params()
    with sql.connect(
        server_hostname=conn_params["server_hostname"],
        http_path=conn_params["http_path"],
        access_token=conn_params["access_token"],
    ) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table_fqn} LIMIT {limit}")
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
    return columns, rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a live sample of a table's current (masked) output.")
    parser.add_argument("table_fqn", help="catalog.schema.table")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    columns, rows = fetch_sample(args.table_fqn, args.limit)
    print("\t".join(columns))
    for row in rows:
        print("\t".join(str(v) for v in row))


if __name__ == "__main__":
    main()
