module "catalog" {
  source       = "../../modules/databricks/catalog"
  catalog_name = var.catalog_name
  project_root = var.project_root
}
