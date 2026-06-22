# The native databricks_catalog resource requires an explicit managed
# storage location on this workspace's metastore ("Metastore storage root
# URL does not exist" without one) — not worth setting up for a portfolio
# dev catalog. CREATE CATALOG IF NOT EXISTS via SQL already works against
# this workspace's default storage, so this delegates to the same dbt macro
# used interactively (dbt/macros/create_catalog.sql), for the same
# single-source-of-truth reason as unity_catalog_tags / masking_policies.
resource "null_resource" "create_catalog" {
  # destroy-time provisioners can only reference `self`, so project_root
  # has to be carried in triggers rather than read from var.project_root.
  triggers = {
    catalog_name = var.catalog_name
    project_root = var.project_root
  }

  provisioner "local-exec" {
    command     = ".venv/bin/dbt run-operation create_catalog_if_not_exists --project-dir ./dbt"
    working_dir = var.project_root
  }

  # DROP CATALOG ... CASCADE removes the tags and masking functions created
  # by the other two modules too, so this single destroy-time call is
  # enough to tear down everything terraform apply created.
  provisioner "local-exec" {
    when        = destroy
    command     = ".venv/bin/dbt run-operation drop_catalog_if_exists --project-dir ./dbt"
    working_dir = self.triggers.project_root
  }
}
