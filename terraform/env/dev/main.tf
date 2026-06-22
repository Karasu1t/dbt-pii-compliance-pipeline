module "catalog" {
  source       = "../../modules/databricks/catalog"
  catalog_name = var.catalog_name
  project_root = var.project_root
}

module "unity_catalog_tags" {
  source                   = "../../modules/databricks/unity_catalog_tags"
  table_fqn                = var.table_fqn
  classification_json_path = var.classification_json_path
  project_root              = var.project_root

  depends_on = [module.catalog]
}

module "masking_policies" {
  source                   = "../../modules/databricks/masking_policies"
  table_fqn                = var.table_fqn
  classification_json_path = var.classification_json_path
  project_root              = var.project_root

  depends_on = [module.unity_catalog_tags]
}
