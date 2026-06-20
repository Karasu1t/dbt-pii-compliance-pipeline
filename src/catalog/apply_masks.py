"""Creates Unity Catalog masking functions and applies them to columns based
on a PII classification result's `mask_strategy` field.

Two masking strategies, deliberately not one generic "hide everything":

- redact: full redaction for direct identifiers — nothing useful leaks.
- generalize_*: for quasi-identifiers, reduce precision instead of dropping
  the column entirely (postal_code -> first 3 chars, birth_date -> year only).
  This keeps the column useful for aggregate analysis while breaking the
  postal_code + birth_date + gender re-identification combination.

Both strategies carve out an exception for an authorized group
(`pii_admins`) — masking that nobody, not even legitimate roles, can see
through isn't governance, it's just data loss.
"""

import argparse
import json
from pathlib import Path

from databricks import sql

from apply_tags import get_connection_params

ADMIN_GROUP = "pii_admins"

MASK_FUNCTIONS = {
    "redact": {
        "name": "mask_direct_identifier",
        "arg_type": "STRING",
        "return_type": "STRING",
        "body": f"CASE WHEN is_account_group_member('{ADMIN_GROUP}') THEN value ELSE '***REDACTED***' END",
    },
    "generalize_postal_code": {
        "name": "generalize_postal_code",
        "arg_type": "STRING",
        "return_type": "STRING",
        "body": f"CASE WHEN is_account_group_member('{ADMIN_GROUP}') THEN value "
        f"ELSE concat(substring(value, 1, 3), 'XX') END",
    },
    "generalize_birth_date": {
        "name": "generalize_birth_date",
        "arg_type": "DATE",
        "return_type": "DATE",
        "body": f"CASE WHEN is_account_group_member('{ADMIN_GROUP}') THEN value "
        f"ELSE date_trunc('YEAR', value) END",
    },
}


def create_mask_functions(cursor, catalog: str, schema: str) -> None:
    for strategy, spec in MASK_FUNCTIONS.items():
        stmt = (
            f"CREATE OR REPLACE FUNCTION {catalog}.{schema}.{spec['name']}(value {spec['arg_type']}) "
            f"RETURNS {spec['return_type']} "
            f"RETURN {spec['body']}"
        )
        cursor.execute(stmt)
        print(f"created/updated function {catalog}.{schema}.{spec['name']}")


def apply_column_masks(table_fqn: str, columns: list[dict]) -> None:
    catalog, schema, _table = table_fqn.split(".")
    conn_params = get_connection_params()
    with sql.connect(
        server_hostname=conn_params["server_hostname"],
        http_path=conn_params["http_path"],
        access_token=conn_params["access_token"],
    ) as conn:
        with conn.cursor() as cursor:
            create_mask_functions(cursor, catalog, schema)
            for col in columns:
                strategy = col.get("mask_strategy", "none")
                if strategy == "none":
                    continue
                func_name = MASK_FUNCTIONS[strategy]["name"]
                stmt = f"ALTER TABLE {table_fqn} ALTER COLUMN {col['column']} SET MASK {catalog}.{schema}.{func_name}"
                cursor.execute(stmt)
                print(f"masked {table_fqn}.{col['column']} -> {func_name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create + apply Unity Catalog masks from a classification JSON.")
    parser.add_argument("table_fqn", help="catalog.schema.table")
    parser.add_argument("classification_json", type=Path, help="path to a classification result JSON")
    args = parser.parse_args()

    result = json.loads(args.classification_json.read_text())
    apply_column_masks(args.table_fqn, result["columns"])
