variable "databricks_host" {
  type        = string
  description = "Databricks workspace URL, e.g. dbc-xxxxxxxx-xxxx.cloud.databricks.com (no https://)"
}

variable "databricks_token" {
  type        = string
  sensitive   = true
  description = "Databricks personal access token"
}

variable "table_fqn" {
  type        = string
  default     = "pii_compliance_dev.default.marts_customer_360"
  description = "Fully-qualified table that tags/masks are applied to"
}

variable "classification_json_path" {
  type        = string
  default     = "src/catalog/classification_marts_customer_360.json"
  description = "Path (relative to project_root) to the PII classification result JSON"
}

variable "project_root" {
  type        = string
  description = "Absolute path to the repo root (local-exec working directory for the tagging/masking scripts)"
}
