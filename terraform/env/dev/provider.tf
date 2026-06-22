# ------------------------------------
# Terraform Configuration
# ------------------------------------
# The databricks provider is only needed for unity_catalog_tags
# (databricks_entity_tag_assignment). catalog and masking_policies still
# delegate to local-exec scripts — see each module's main.tf for why.
terraform {
  required_version = ">= 1.4"
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.55"
    }
    null = {
      source = "hashicorp/null"
    }
  }
}

# ---------------------------------------------
# Provider
# Note: In GitHub Actions, Databricks credentials come from environment
# variables (DATABRICKS_HOST, DATABRICKS_TOKEN) set as repository secrets,
# mapped to TF_VAR_databricks_host / TF_VAR_databricks_token.
# In local development, export the same variables, or pass -var on the CLI
# using the values already in ~/.dbt/profiles.yml.
provider "databricks" {
  host  = var.databricks_host
  token = var.databricks_token
}
