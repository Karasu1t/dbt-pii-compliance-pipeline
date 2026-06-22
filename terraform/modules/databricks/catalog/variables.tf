variable "catalog_name" {
  type        = string
  description = "Unity Catalog name to create"
}

variable "project_root" {
  type        = string
  description = "Absolute path to the repo root, used as the local-exec working directory"
}
