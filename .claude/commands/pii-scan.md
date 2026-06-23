Starting PII scan workflow.

---

## Navigation (available at every Proceed prompt)

At any `Proceed? (y/n/back/all back/or describe what you want)` prompt:
- `y`        → apply the change and move to the next step
- `n`        → revise and re-present the same step (no files changed)
- `back`     → revert the previous step's file changes (`git checkout -- <files changed in that step>`) and return to that step
- `all back` → abort the entire workflow: revert all changes, delete the working branch, and return to `dev`
  - Run: `git checkout dev && git branch -D {branch_name}`
  - Display: `⚠️ Workflow aborted. All changes reverted. Back on dev.`
- **Any other text** → treat as a manual override of a column's classification (e.g. "actually `signup_source` isn't PII, skip it"). Apply it, then re-present the classification table for confirmation. Record the override in the session log (see Post-Workflow section).

Always show `(y/n/back/all back/or describe what you want)` — not just `(y/n)`.

## Session Log (internal — maintained throughout the workflow)

Track every manual override made during the session:
```
[STEP {N}] Override: "{what the user asked}"
           Action taken : "{what was done}"
           Outcome      : success / revised / skipped
```
This log is used in the Post-Workflow improvement step.

---

## Phase 1: Classify Before Touching Any Files

### 1-1. Confirm Target Model

Arguments: $ARGUMENTS

If an argument is provided, use it directly and skip to validation below.

Otherwise, list every model found under `dbt/models/staging/` and `dbt/models/marts/`, numbered, and prompt:
```
Which dbt model should be scanned for PII?
  1. stg_customers
  2. stg_orders
  3. marts_customer_360

Enter a number or model name:
```

Accept either a number (resolve it to the corresponding model in the list above) or a model name typed directly.

Validate the model exists under `dbt/models/staging/` or `dbt/models/marts/`. If not found:
```
❌ Model '{model_name}' not found under dbt/models/staging/ or dbt/models/marts/.
   Available models:
     1. stg_customers
     2. stg_orders
     3. marts_customer_360

Enter a number or model name:
```

---

### 1-2. Run Classification

Do this classification yourself, in this session — there is no separate classification script. AI classification only happens here, interactively; CI only ever re-checks completeness and enforcement deterministically (`scripts/check_classification_completeness.py`, `dbt/tests/pii_mask_enforced.sql`), neither of which calls an LLM.

1. Read the model's compiled column list (`dbt/target/manifest.json`; run `dbt compile` first if stale)
2. Pull a bounded sample of rows — query Databricks directly if connected, otherwise read the corresponding `dbt/seeds/*.csv`
3. Classify each column individually (not_pii / direct_identifier / special_category / quasi_identifier), then check **combinations** of individually-low-risk columns for re-identification risk
4. Look at actual sample values, not just column names — a column named like a generic reference can still hold a government-ID-shaped value; free-text fields can contain embedded PII even when most rows don't

Also read any existing Unity Catalog tags on this table and show them as the "current state" baseline.

---

### 1-3. Present Classification Table

```
📋 PII Classification — {model_name}
  ─────────────────────────────────────────────
  Column            Classification        GDPR basis      Confidence
  ─────────────────────────────────────────────
  email             direct_identifier     Art. 4(1)        high
  full_name         direct_identifier     Art. 4(1)        high
  postal_code       quasi_identifier*     Recital 26        medium
  birth_date        quasi_identifier*     Recital 26        medium
  gender            quasi_identifier*     Recital 26        medium
  product_id        not_pii               —                 high
  ─────────────────────────────────────────────
  * postal_code + birth_date + gender form a re-identification group

  Is this model public-facing (BI tool / dashboard exposed)? (y/n)

  Anything to override before proceeding? (y/n/describe what you want)
```

If the user describes an override, apply it to the in-memory table and re-display. Loop until confirmed with `y`.

---

### 1-4. Final Confirmation

```
📋 Change Summary
  ─────────────────────────────
  Model         : {model_name}
  Public-facing : yes / no
  PII columns   : {count} ({list})
  Quasi-id group: {list, or "none"}
  ─────────────────────────────
  Files to modify ({N} total):
    - src/catalog/classification_{model_name}.json   … PII classification result — read directly by both the
                                                         unity_catalog_tags Terraform module (native
                                                         databricks_entity_tag_assignment, jsondecode) and
                                                         masking_policies (local-exec → apply_masks.py).
                                                         No per-model .tf files are created or edited.
    - terraform/env/dev/variables.tf                  … only if {model_name} differs from the current
                                                         table_fqn/classification_json_path — this Terraform
                                                         setup manages one table at a time
    - dbt/models/{staging|marts}/schema.yml            … human-readable column descriptions only — Unity
                                                         Catalog tags (not schema.yml) are the enforcement
                                                         source of truth read by pii_mask_enforced.sql
    - dbt/models/exposures.yml                         … only if newly public-facing
    - dbt/tests/pii_mask_enforced.sql                  … only if it doesn't exist yet — it already covers
                                                         every model listed in exposures.yml dynamically

Proceed with these changes? (y/n/back/all back)
```

If `y` → move to Phase 2. If `n` → return to 1-3.

---

## Phase 2: Execute (one step at a time)

**Show the diff for each step and ask `Proceed? (y/n/back/all back)` before making any change.**
Only `y` moves forward. Track which files were changed at each step to enable rollback.

---

### STEP 1/9: Create working branch

```
[STEP 1/9] Create branch
  Current branch : {current_branch}
  → {if not dev: "switching to dev first" / if dev: "creating from here"}
  New branch     : feature/{YYYYMMDD}/pii_scan_{model_name}
Proceed? (y/n/back/all back)
```

`back` at STEP 1 → no files have been changed yet; return to Phase 1 final confirmation.

---

### STEP 2/9: src/catalog/classification_{model_name}.json

```
[STEP 2/9] src/catalog/classification_{model_name}.json
  Diff:
    {full classification JSON: columns[] with classification/gdpr_basis/confidence/reasoning/mask_strategy,
     plus quasi_identifier_groups[]}
Proceed? (y/n/back/all back)
```

This single file is what both the `unity_catalog_tags` Terraform module (native `databricks_entity_tag_assignment`,
read via `jsondecode`) and `masking_policies` (local-exec → `apply_masks.py`) consume — no `.tf` files are
hand-edited per model.

`back` → `git checkout -- src/catalog/classification_{model_name}.json` (or delete it if newly created) and return to STEP 1.

---

### STEP 3/9: terraform/env/dev/variables.tf

Only applies if `{model_name}`'s table differs from the current `table_fqn` — this Terraform setup manages
**one table at a time**. If it's the same table already configured, skip with no change.

```
[STEP 3/9] terraform/env/dev/variables.tf
  Assessment : {no change — already configured for this table / updating table_fqn and classification_json_path}
  {diff if changing}
Proceed? (y/n/back/all back)
```

`back` → `git checkout -- terraform/env/dev/variables.tf` and return to STEP 2.

---

### STEP 4/9: dbt/models/{staging|marts}/schema.yml

Documentation only — Unity Catalog tags (applied in STEP 6) are the actual enforcement source of truth, not this file.

```
[STEP 4/9] dbt/models/{staging|marts}/schema.yml
  Diff:
    {column descriptions noting PII status, for human readability in dbt docs}
Proceed? (y/n/back/all back)
```

`back` → `git checkout -- dbt/models/{staging|marts}/schema.yml` and return to STEP 3.

---

### STEP 5/9: dbt/models/exposures.yml

Only applies if the model is public-facing and not already listed.

```
[STEP 5/9] dbt/models/exposures.yml
  Assessment : {already listed, no change / adding new exposure entry}
  {if adding: diff}
Proceed? (y/n/back/all back)
```

`back` → `git checkout -- dbt/models/exposures.yml` and return to STEP 4.

---

### STEP 6/9: terraform plan / apply

Applies the tags and masks for real — `pii_mask_enforced.sql` (STEP 7) has nothing to check against until this runs.

**Prerequisite — check this before running plan/apply, every time:** `{table_fqn}` must already exist
in Databricks (`unity_catalog_tags` and `masking_policies` both fail with "Table ... does not exist" otherwise —
discovered the hard way running this command against a freshly-destroyed environment). Tags/masks are layered
on top of dbt-managed tables; they don't create them. If unsure whether the table exists, run
`dbt seed --project-dir ./dbt && dbt run --project-dir ./dbt` first — cheap and idempotent if it already does.

```
[STEP 6/9] terraform plan / apply
  Pre-check : {table_fqn} exists in Databricks? {yes / no — ran dbt seed + dbt run first}
  Command   : terraform -chdir=terraform/env/dev apply
  {show plan summary — resources to add/change}
Proceed? (y/n/back/all back)
```

`back` → no terraform state revert needed if plan was only previewed; if applied, note that a subsequent
`terraform destroy` or manual cleanup would be needed — ask before reverting applied infrastructure.

---

### STEP 7/9: Run `dbt test` locally

`dbt/tests/pii_mask_enforced.sql` already exists and dynamically covers every model listed in `exposures.yml` —
nothing to create here, just run it.

```
[STEP 7/9] Run dbt test
  Command : dbt test --select pii_mask_enforced
  {show output summary — pass/fail per test}
Proceed? (y/n/back/all back)
```

If tests fail, report the failure and do not proceed to STEP 8 until resolved.
`back` → return to STEP 6 (no file revert needed, this step only runs tests).

---

### STEP 8/9: Review live data for residual risk

By this point the masks from STEP 6 are live, and STEP 7 already confirmed every `mask_required` column has
*some* mask attached. This step checks something metadata can't: whether the actual masked output still
leaks something, or contains a PII pattern the Phase 1 classification didn't catch. This is the same kind of
judgment Phase 1 made on raw sample data, applied here to the real masked output instead.

1. Run `python scripts/sample_live_table.py {table_fqn} --limit 100` — prints column headers and 100 live rows,
   exactly as any ordinary query against `{table_fqn}` would see them today (i.e. already masked).
2. Review the output, column by column, against the Phase 1 classification:
   - For every masked column: does anything in this sample still look identifiable? (a generalized
     `postal_code` narrow enough to isolate one row, a quasi-identifier combination that's still too
     specific even after generalization, a redaction that missed a row)
   - For every column, masked or not: does anything in the actual values look like a PII pattern the
     original classification missed?

```
[STEP 8/9] Review live data for residual risk
  Command : python scripts/sample_live_table.py {table_fqn} --limit 100
  Findings:
    {✅ no residual risk or new PII pattern found in this sample
     — or —
     ⚠️ {specific finding, with the column and the row that triggered it}}
Proceed? (y/n/back/all back/or describe what you want)
```

A flagged finding doesn't automatically block STEP 9 — discuss it with the user. Options are revising the
mask strategy (`back` all the way to STEP 2) or accepting it and proceeding (e.g. a finding that's an
artifact of small synthetic sample size rather than a real gap).

`back` → return to STEP 7 (no file revert needed, this step only reads data).

---

### STEP 9/9: Commit & open PR

```
[STEP 9/9] Commit & open PR
  Changed files ({N}):
    {list of modified files}
  Commit message : {Conventional Commits format}
  PR title       : {same as commit message}
  Target branch  : dev

  PR description (auto-generated):
    ## PII Classification — {model_name}
    {classification table from Phase 1}

    ## Modified Files
    {bullet list of each file and what changed}

    ## Automated Checks (all deterministic — no AI runs in CI)
    Opening this PR against dev will automatically trigger:
    - dbt_build.yml                      (seed + run + test build)
    - terraform_apply.yml                (Unity Catalog tags + masks go live)
    - governance_check.yml                (dbt test pii_mask_enforced + classification completeness — runs only after terraform_apply succeeds)

  ⚠️ Creating this PR will trigger dbt_build, terraform_apply, and governance_check automatically.
Proceed? (y/n/back/all back)
```

`back` → return to STEP 8 (no git action needed, nothing committed yet).

If y → run `git add` → `commit` → `push` → `gh pr create` and display the PR URL.

```
✅ PII scan workflow complete
  PR: {URL}
  GitHub Actions (dbt_build / terraform_apply → governance_check) is now running.
  Check the PR page for results.
```

---

## Post-Workflow: Improvement Suggestions

After the PR is created, review the session log.

**If there were no overrides:** skip this section entirely.

**If there were any overrides:** display the following and ask for approval:

```
💡 Workflow Improvement Suggestions

The following overrides were made during this session:
  [STEP {N}] "{override}" → {action taken}
  ...

Based on these, the following improvements are proposed:

  [A] Add to .claude/commands/pii-scan.md:
      {specific addition — e.g. a new column-name heuristic, a new category}
      Reason: {why this should be a permanent part of the workflow}

  [B] Add to CLAUDE.md:
      {specific addition — e.g. a project convention, a recurring classification pattern}
      Reason: {why this belongs in the project guide}

Apply these improvements? (y / n / select: A B / describe changes)
```

- `y`            → apply all proposed improvements
- `n`            → skip, no changes made
- `select: A B`  → apply only selected items (space-separated letters)
- Any other text → treat as revision instructions and re-propose

If improvements are applied, commit them separately:
```
chore: improve /pii-scan workflow based on session feedback
```

```
✅ Workflow guide updated. Changes will apply from the next /pii-scan session.
```
