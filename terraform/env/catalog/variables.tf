variable "catalog_name" {
  type    = string
  default = "pii_compliance_dev"
}

variable "project_root" {
  type        = string
  description = "Absolute path to the repo root (local-exec working directory for dbt run-operation)"
}
