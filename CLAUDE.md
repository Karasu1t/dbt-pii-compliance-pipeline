# dbt PII Compliance Pipeline - Project Guide

## Language

Always respond in English in this project.

## Project Overview

A pipeline that semi-automates GDPR-driven PII governance for a dbt project running on Databricks.
- dbt (dbt-databricks) → Databricks Unity Catalog → Delta Lake (UniForm / Iceberg-readable)
- AI classification: done two ways, deliberately —
  - Interactively, inside a Claude Code session (`/pii-scan`): no separate billing, it's covered by the Claude Code session itself
  - Non-interactively, in CI (`pii_compliance_check.yml`): calls the Anthropic API directly via `src/pii_classifier/classify.py`, since GitHub Actions runs unattended and there's no Claude Code session to lean on. This is the only place an `ANTHROPIC_API_KEY` is actually required.
- Enforcement: Unity Catalog column tags + masking functions, verified continuously by dbt tests
- Infrastructure: Terraform (Databricks provider)
- CI/CD: GitHub Actions (ci / dbt_build / pii_compliance_check / terraform_apply / terraform_destroy)

## Branch Strategy

- `main`: production
- `dev`: integration branch for development
- `feature/{YYYYMMDD}/pii_scan_{model_name}`: working branches (cut from `dev`)

---

## PII Scan Workflow

Use the `/pii-scan` command whenever a dbt model is added or its column set changes.

```
/pii-scan stg_customers
/pii-scan marts_customer_360
```

The command handles the full workflow in two phases:

**Phase 1 — Classify before touching any files**
- Read the target model's compiled columns (via `dbt/manifest.json` and `information_schema`)
- Pull a bounded sample of rows from Databricks for context
- Claude Code classifies each column directly in this session (no API call, no extra cost): not PII / direct identifier / sensitive category (GDPR Art. 9) / quasi-identifier
- Also checks **combinations** of low-sensitivity columns for re-identification risk (e.g. `postal_code` + `birth_date` + `gender`), not just single-column keyword matching
- Full classification table presented for confirmation/adjustment before any file changes

**Phase 2 — Execute one step at a time with confirmation**
Each step shows the exact diff and asks `Proceed? (y/n)` before making any change.

| Step | Target | Purpose |
|------|--------|---------|
| 1/8 | Branch creation | `feature/{YYYYMMDD}/pii_scan_{model_name}` from `dev` |
| 2/8 | `terraform/modules/databricks/unity_catalog_tags/` | Unity Catalog column tags: `pii_category` (classification) and `mask_required` (true/false — makes a deliberate "tagged as risk but intentionally left unmasked" call explicit, e.g. `gender`) |
| 3/8 | `terraform/modules/databricks/masking_policies/` | Column masking function assignment for columns where `mask_required = true` |
| 4/8 | `dbt/models/**/schema.yml` | Column-level documentation only — the actual enforcement source of truth is the Unity Catalog tags applied in step 2, not schema.yml |
| 5/8 | `dbt/tests/pii_mask_enforced.sql` | Singular dbt test: cross-references `information_schema.column_tags` (`mask_required = true`) against `information_schema.column_masks` for models listed in `exposures.yml` — fails if any tagged column lacks an active mask |
| 6/8 | `dbt/models/exposures.yml` | Marks the model as public-facing if newly dashboard/BI-exposed |
| 7/8 | `dbt test` (local run) | Validates the new test passes against the live warehouse |
| 8/8 | Commit + PR | Opens PR against `dev`, triggers Terraform apply + dbt build + PII compliance check automatically |

---

## CI/CD Behavior

Opening a PR against `dev` triggers the CI pipeline (`ci.yml`):

```
pull_request → dev
    ├── terraform_apply.yml      (parallel)
    └── dbt_build.yml            (parallel)
              ↓ only if both pass
         pii_compliance_check.yml
```

- `dbt_build.yml` and `terraform_apply.yml` run in parallel.
- `pii_compliance_check.yml` runs only after both succeed, and re-runs the Claude classification non-interactively against the diffed models — if a column is newly exposed without a tag/mask, the PR is blocked and Claude posts a PR comment explaining which column and why.
- Terraform apply runs on PR so Unity Catalog tags/masks are live before the compliance check queries them.

---

## Execution Principles

- Never modify files without confirmation (interactive mode) — in CI, the non-interactive checker only blocks/comments, it never auto-fixes.
- Each step is independent — never batch multiple steps together.
- If an error occurs mid-step, report immediately and do not proceed.
- If `n` is answered, revise and re-present the same step.
- Synthetic data only (`Faker`-generated) — never load real customer PII into this repo's sample dataset.

---

## PII Category Reference

| Category | GDPR basis | Example columns | Default action |
|----------|-----------|------------------|-----------------|
| Direct identifier | Art. 4(1) | `email`, `full_name`, `phone_number` | Mask in all non-owner-role queries |
| Special category | Art. 9 | `health_notes`, `religion`, `union_membership` | Mask + restrict to explicit allowlist role |
| Quasi-identifier (combination) | Recital 26 (re-identification risk) | `postal_code` + `birth_date` + `gender` | Flag combination, require generalization or row-level policy |
| Not PII | — | `product_id`, `order_total` | No action |
