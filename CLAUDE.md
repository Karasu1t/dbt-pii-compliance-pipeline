# dbt PII Compliance Pipeline - Project Guide

## Language

Always respond in English in this project.

## Project Overview

A pipeline that semi-automates GDPR-driven PII governance for a dbt project running on Databricks.
- dbt (dbt-databricks) → Databricks Unity Catalog → Delta Lake (UniForm / Iceberg-readable)
- AI classification happens in exactly one place: interactively, inside a Claude Code session, via `/pii-scan`. This is a **developer-time skill**, not a CI step — there is no Anthropic API usage anywhere in this repo, and no `ANTHROPIC_API_KEY` is needed.
- CI/CD's job is verifying that what `/pii-scan` already decided is actually complete and actually enforced — both are deterministic set-comparison / metadata checks, not classification judgment, so no AI is involved:
  - **Completeness**: does every live column in an exposed table have a classification entry? (`scripts/check_classification_completeness.py`)
  - **Enforcement**: does every column tagged `mask_required = true` have an active Unity Catalog mask? (`dbt/tests/pii_mask_enforced.sql`)
- Enforcement: Unity Catalog column tags + masking functions, verified continuously by dbt tests
- Infrastructure: Terraform (Databricks provider)
- CI/CD: GitHub Actions (`dbt_build.yml`, `terraform_apply.yml`, `governance_check.yml`)

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
| 2/8 | `src/catalog/classification_{model_name}.json` | The classification result — read directly by both `unity_catalog_tags` (native `databricks_entity_tag_assignment`, via `jsondecode`) and `masking_policies` (local-exec → `apply_masks.py`). No `.tf` files are hand-edited per model. |
| 3/8 | `terraform/env/dev/variables.tf` | Only if `{model_name}`'s table differs from the currently-configured `table_fqn` — this setup manages one table at a time |
| 4/8 | `dbt/models/**/schema.yml` | Column-level documentation only — the actual enforcement source of truth is the Unity Catalog tags applied in step 6, not schema.yml |
| 5/8 | `dbt/models/exposures.yml` | Marks the model as public-facing if newly dashboard/BI-exposed |
| 6/8 | `terraform plan` / `apply` | Applies the tags and masks for real — nothing for STEP 7 to check until this runs. **Prerequisite: `{table_fqn}` must already exist** (`dbt seed && dbt run` first if unsure) — tags/masks layer onto dbt-managed tables, they don't create them |
| 7/8 | `dbt test --select pii_mask_enforced` (local run) | Already covers every model in `exposures.yml` dynamically — nothing to create, just run it |
| 8/8 | Commit + PR | Opens PR against `dev`, triggers `dbt_build.yml` + `terraform_apply.yml` + `governance_check.yml` automatically — all three are deterministic checks, no AI involved at this stage |

---

## CI/CD Behavior

Opening a PR against `dev` triggers a **sequential** pipeline — not parallel jobs joining at the end. This is
deliberate: `terraform_apply` tags/masks a table that only `dbt_build` creates (`dbt seed` + `dbt run`), the same
ordering bug found running `/pii-scan` end-to-end against a freshly-destroyed environment (see STEP 6/8's
prerequisite note). Running them in parallel would race the same failure into CI.

```
pull_request → dev
    dbt_build.yml                (seed + run + test, excluding pii_mask_enforced — masks don't exist yet)
        ↓
    terraform_apply.yml          (tags + masks go live, now that dbt_build's tables exist)
        ↓
    governance_check.yml         (dbt test --select pii_mask_enforced + completeness script — both deterministic, no AI)
```

`governance_check.yml` checks two things, neither requiring an LLM:
1. **Enforcement** (`pii_mask_enforced.sql`): does every column tagged `mask_required = true` have an active mask?
2. **Completeness** (`scripts/check_classification_completeness.py`): does every live column in an exposed table have a classification entry at all? If a column was added without anyone running `/pii-scan`, the PR is blocked with a list of which columns are missing.

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
