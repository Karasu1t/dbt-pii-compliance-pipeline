variable "table_fqn" {
  type        = string
  description = "Fully-qualified table (catalog.schema.table) to apply masks to"
}

variable "classification_json_path" {
  type        = string
  description = "Path (relative to project_root) to the PII classification result JSON"
}

variable "project_root" {
  type        = string
  description = "Absolute path to the repo root, used as the local-exec working directory"
}
