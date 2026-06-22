# ------------------------------------
# Terraform Configuration
# ------------------------------------
# No databricks provider is configured here — every module in this
# environment delegates to local-exec scripts (dbt run-operation,
# apply_tags.py, apply_masks.py) that already read credentials from
# ~/.dbt/profiles.yml. See each module's main.tf for why the native
# databricks_catalog resource and Unity Catalog tag/mask resources weren't
# used directly.
terraform {
  required_version = ">= 1.4"
  required_providers {
    null = {
      source = "hashicorp/null"
    }
  }
}
