"""Checks that every column in an exposed model has a PII classification entry.

This catches "forgot to run /pii-scan for a new column" deterministically —
no AI judgment is needed here. The judgment call (is this column PII, does
it combine with others into a re-identification risk) already happened when
a human ran /pii-scan and reviewed the result; this script only verifies
that the resulting classification_{model}.json actually covers every column
that exists live in Databricks today. Classifying is /pii-scan's job;
checking for completeness is this script's job, and the two don't need the
same tool.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "catalog"))
from apply_tags import get_connection_params  # noqa: E402
from databricks import sql  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "dbt" / "target" / "manifest.json"
CLASSIFICATION_DIR = PROJECT_ROOT / "src" / "catalog"


def get_exposed_table_names(manifest: dict) -> list[str]:
    names = []
    for exposure in manifest.get("exposures", {}).values():
        for dep in exposure.get("depends_on", {}).get("nodes", []):
            node = manifest["nodes"].get(dep)
            if node:
                names.append(node["alias"])
    return names


def get_live_columns(cursor, catalog: str, schema: str, table: str) -> set[str]:
    cursor.execute(
        f"SELECT column_name FROM {catalog}.information_schema.columns "
        f"WHERE table_schema = '{schema}' AND table_name = '{table}'"
    )
    return {row[0] for row in cursor.fetchall()}


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text())
    conn_params = get_connection_params()
    catalog, schema = conn_params["catalog"], conn_params["schema"]
    table_names = get_exposed_table_names(manifest)

    failures = []
    with sql.connect(
        server_hostname=conn_params["server_hostname"],
        http_path=conn_params["http_path"],
        access_token=conn_params["access_token"],
    ) as conn:
        with conn.cursor() as cursor:
            for table in table_names:
                classification_path = CLASSIFICATION_DIR / f"classification_{table}.json"
                if not classification_path.exists():
                    failures.append(f"{table}: no classification file ({classification_path.name}) — run /pii-scan {table}")
                    continue

                classification = json.loads(classification_path.read_text())
                classified_columns = {col["column"] for col in classification["columns"]}
                live_columns = get_live_columns(cursor, catalog, schema, table)

                missing = live_columns - classified_columns
                if missing:
                    failures.append(f"{table}: unclassified columns {sorted(missing)} — run /pii-scan {table}")

    if failures:
        print("Classification completeness check FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"Classification completeness check passed for {len(table_names)} exposed table(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
