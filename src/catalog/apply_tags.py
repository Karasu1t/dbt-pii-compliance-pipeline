"""Applies Unity Catalog column tags based on a PII classification result.

Used by the interactive /pii-scan workflow (Phase 2, STEP 2/8) and, later,
by the non-interactive CI compliance check. Tags are applied via SQL
ALTER TABLE ... ALTER COLUMN ... SET TAGS, which Unity Catalog enforces at
query time regardless of which engine reads the table.

Connection details are read from the existing dbt profiles.yml (project-local
dbt/profiles.yml if present, otherwise ~/.dbt/profiles.yml) so credentials
aren't duplicated between dbt and these scripts.
"""

import argparse
import json
import os
from pathlib import Path

import yaml
from databricks import sql

PROFILE_NAME = "pii_compliance_pipeline"


def _find_profiles_yml() -> Path:
    project_local = Path(__file__).resolve().parent.parent.parent / "dbt" / "profiles.yml"
    if project_local.exists():
        return project_local
    default = Path(os.environ.get("DBT_PROFILES_DIR", str(Path.home() / ".dbt"))) / "profiles.yml"
    if default.exists():
        return default
    raise FileNotFoundError("No profiles.yml found (checked dbt/profiles.yml and ~/.dbt/profiles.yml)")


def get_connection_params(target: str | None = None) -> dict:
    profiles = yaml.safe_load(_find_profiles_yml().read_text())
    profile = profiles[PROFILE_NAME]
    target = target or profile["target"]
    output = profile["outputs"][target]
    # In CI, profiles.yml.example's host/http_path/token are Jinja env_var()
    # placeholders that only dbt itself resolves — yaml.safe_load() can't.
    # DATABRICKS_* env vars (from GitHub Actions secrets) take precedence so
    # these scripts work against the same secrets without needing Jinja.
    return {
        "server_hostname": os.environ.get("DATABRICKS_HOST") or output["host"],
        "http_path": os.environ.get("DATABRICKS_HTTP_PATH") or output["http_path"],
        "access_token": os.environ.get("DATABRICKS_TOKEN") or output["token"],
        "catalog": output["catalog"],
        "schema": output["schema"],
    }


def apply_column_tags(table_fqn: str, columns: list[dict]) -> None:
    conn_params = get_connection_params()
    with sql.connect(
        server_hostname=conn_params["server_hostname"],
        http_path=conn_params["http_path"],
        access_token=conn_params["access_token"],
    ) as conn:
        with conn.cursor() as cursor:
            for col in columns:
                if col["classification"] == "not_pii":
                    continue
                # mask_required makes a deliberate "tagged as risk but left
                # unmasked" decision (e.g. gender, low cardinality alone)
                # explicit and queryable, instead of leaving the dbt test to
                # treat it as an undetected gap.
                mask_required = "true" if col.get("mask_strategy", "none") != "none" else "false"
                stmt = (
                    f"ALTER TABLE {table_fqn} ALTER COLUMN {col['column']} "
                    f"SET TAGS ('pii_category' = '{col['classification']}', 'mask_required' = '{mask_required}')"
                )
                cursor.execute(stmt)
                print(
                    f"tagged {table_fqn}.{col['column']} -> "
                    f"pii_category={col['classification']}, mask_required={mask_required}"
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply Unity Catalog PII tags from a classification JSON.")
    parser.add_argument("table_fqn", help="catalog.schema.table")
    parser.add_argument("classification_json", type=Path, help="path to a classification result JSON")
    args = parser.parse_args()

    result = json.loads(args.classification_json.read_text())
    apply_column_tags(args.table_fqn, result["columns"])
