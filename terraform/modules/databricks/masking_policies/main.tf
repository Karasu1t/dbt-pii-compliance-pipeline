# Column masking functions + SET MASK assignment have no mature native
# Terraform resource either, so this delegates to src/catalog/apply_masks.py
# for the same reason as unity_catalog_tags. Ordered after tagging (see
# depends_on in env/dev/main.tf) to match the documented /pii-scan workflow
# (CLAUDE.md STEP 2/8 then 3/8) — both scripts read the same classification
# JSON independently, so this isn't a hard data dependency, just sequencing
# consistency with how the steps are meant to be reviewed.
resource "null_resource" "apply_masks" {
  triggers = {
    classification_hash = filesha256("${var.project_root}/${var.classification_json_path}")
    table_fqn            = var.table_fqn
  }

  provisioner "local-exec" {
    command     = ".venv/bin/python src/catalog/apply_masks.py ${var.table_fqn} ${var.classification_json_path}"
    working_dir = var.project_root
  }
}
