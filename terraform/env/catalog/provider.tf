# ------------------------------------
# Terraform Configuration
# ------------------------------------
# Separate state from terraform/env/dev/ on purpose: catalog creation is
# infrequent bootstrap infrastructure (apply once per environment, rarely
# touched again), while env/dev's tags/masks are reconciled on every PR.
# Bundling both into one state meant routine PR-triggered applies would
# also re-evaluate catalog creation, and — worse — catalog must exist
# before dbt seed/run can create the tables that tags/masks attach to,
# which made a single sequential "terraform apply" for everything
# impossible to order correctly against dbt_build.
terraform {
  required_version = ">= 1.4"
  required_providers {
    null = {
      source = "hashicorp/null"
    }
  }
}
