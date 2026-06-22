# Verified against the provider source that databricks_entity_tag_assignment
# exists and supports entity_type = "columns" — unlike catalog (blocked by
# this workspace's storage config) and masking (no native resource at all),
# there's no real justification for wrapping a script here. The same
# classification JSON apply_tags.py reads is loaded directly via
# jsondecode(file(...)) instead of shelling out.
locals {
  classification = jsondecode(file("${var.project_root}/${var.classification_json_path}"))
  pii_columns = {
    for col in local.classification.columns : col.column => col
    if col.classification != "not_pii"
  }
}

resource "databricks_entity_tag_assignment" "pii_category" {
  for_each = local.pii_columns

  entity_type = "columns"
  entity_name = "${var.table_fqn}.${each.key}"
  tag_key     = "pii_category"
  tag_value   = each.value.classification
}

resource "databricks_entity_tag_assignment" "mask_required" {
  for_each = local.pii_columns

  entity_type = "columns"
  entity_name = "${var.table_fqn}.${each.key}"
  tag_key     = "mask_required"
  tag_value   = each.value.mask_strategy != "none" ? "true" : "false"
}
