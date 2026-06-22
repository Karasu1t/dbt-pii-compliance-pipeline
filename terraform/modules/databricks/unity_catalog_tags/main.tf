# Unity Catalog column tags (pii_category, mask_required) have no mature
# native Terraform resource yet, so this delegates to the same
# src/catalog/apply_tags.py script used interactively by /pii-scan — a
# single source of truth instead of re-implementing the SQL in HCL.
resource "null_resource" "apply_tags" {
  triggers = {
    classification_hash = filesha256("${var.project_root}/${var.classification_json_path}")
    table_fqn            = var.table_fqn
  }

  provisioner "local-exec" {
    command     = ".venv/bin/python src/catalog/apply_tags.py ${var.table_fqn} ${var.classification_json_path}"
    working_dir = var.project_root
  }
}
