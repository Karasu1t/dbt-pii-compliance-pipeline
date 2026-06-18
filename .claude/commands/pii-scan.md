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

```
Which dbt model should be scanned for PII?
  → /pii-scan {model_name}   e.g. /pii-scan marts_customer_360

Enter the model name:
```

If an argument is provided, use it directly. Otherwise wait for input.

Validate the model exists under `dbt/models/staging/` or `dbt/models/marts/`. If not found:
```
❌ Model '{model_name}' not found under dbt/models/staging/ or dbt/models/marts/.
   Available models: {list}
```

---

### 1-2. Run Classification

Invoke `src/pii_classifier/classify.py {model_name}`, which:
1. Reads the model's compiled column list (`dbt/target/manifest.json`; run `dbt compile` first if stale)
2. Pulls a bounded sample of rows — from Databricks if a live workspace connection is configured, otherwise from the corresponding `dbt/seeds/*.csv`
3. Calls the Claude API to classify each column individually, then checks **combinations** of individually-low-risk columns for re-identification risk
4. Returns a JSON report: `{column, classification, gdpr_basis, confidence, quasi_identifier_group}`

Existing Unity Catalog tags on this table (if any) are also read and shown as the "current state" baseline.

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
    - terraform/modules/databricks/unity_catalog_tags/{model_name}.tf     … Unity Catalog column tags
    - terraform/modules/databricks/masking_policies/{model_name}.tf      … masking function assignment (only if public-facing + PII present)
    - dbt/models/{staging|marts}/schema.yml                              … meta.pii / meta.pii_category annotations
    - dbt/tests/generic/pii_mask_enforced.sql                            … generic test (created once, otherwise unchanged)
    - dbt/models/exposures.yml                                           … only if newly public-facing

Proceed with these changes? (y/n/back/all back)
```

If `y` → move to Phase 2. If `n` → return to 1-3.

---

## Phase 2: Execute (one step at a time)

**Show the diff for each step and ask `Proceed? (y/n/back/all back)` before making any change.**
Only `y` moves forward. Track which files were changed at each step to enable rollback.

---

### STEP 1/8: Create working branch

```
[STEP 1/8] Create branch
  Current branch : {current_branch}
  → {if not dev: "switching to dev first" / if dev: "creating from here"}
  New branch     : feature/{YYYYMMDD}/pii_scan_{model_name}
Proceed? (y/n/back/all back)
```

`back` at STEP 1 → no files have been changed yet; return to Phase 1 final confirmation.

---

### STEP 2/8: terraform/modules/databricks/unity_catalog_tags/{model_name}.tf

```
[STEP 2/8] terraform/modules/databricks/unity_catalog_tags/{model_name}.tf
  Diff:
    {databricks_catalog_tag / column tag resource per PII column}
Proceed? (y/n/back/all back)
```

`back` → `git checkout -- terraform/modules/databricks/unity_catalog_tags/{model_name}.tf` and return to STEP 1.

---

### STEP 3/8: terraform/modules/databricks/masking_policies/{model_name}.tf

Only applies if the model is public-facing **and** has at least one PII or quasi-identifier-group column.

```
[STEP 3/8] terraform/modules/databricks/masking_policies/{model_name}.tf
  Assessment : {change needed / skipped — model not public-facing / skipped — no PII present}
  {if change needed: diff of masking function + ALTER TABLE ... SET MASK}
Proceed? (y/n/back/all back)
```

`back` → `git checkout -- terraform/modules/databricks/masking_policies/{model_name}.tf` and return to STEP 2.

---

### STEP 4/8: dbt/models/{staging|marts}/schema.yml

```
[STEP 4/8] dbt/models/{staging|marts}/schema.yml
  Diff:
    {meta.pii: true/false and meta.pii_category per column, added under the model's existing schema.yml entry}
Proceed? (y/n/back/all back)
```

`back` → `git checkout -- dbt/models/{staging|marts}/schema.yml` and return to STEP 3.

---

### STEP 5/8: dbt/tests/generic/pii_mask_enforced.sql

```
[STEP 5/8] dbt/tests/generic/pii_mask_enforced.sql
  Assessment : {already exists, no change / creating for the first time}
  {if creating: show full generic test definition — fails if a column with meta.pii: true
   in a model listed in exposures.yml lacks an active Unity Catalog mask}
Proceed? (y/n/back/all back)
```

`back` → `git checkout -- dbt/tests/generic/pii_mask_enforced.sql` and return to STEP 4.

---

### STEP 6/8: dbt/models/exposures.yml

Only applies if the model is public-facing and not already listed.

```
[STEP 6/8] dbt/models/exposures.yml
  Assessment : {already listed, no change / adding new exposure entry}
  {if adding: diff}
Proceed? (y/n/back/all back)
```

`back` → `git checkout -- dbt/models/exposures.yml` and return to STEP 5.

---

### STEP 7/8: Run `dbt test` locally

```
[STEP 7/8] Run dbt test
  Command : dbt test --select {model_name}
  {show output summary — pass/fail per test}
Proceed? (y/n/back/all back)
```

If tests fail, report the failure and do not proceed to STEP 8 until resolved.
`back` → return to STEP 6 (no file revert needed, this step only runs tests).

---

### STEP 8/8: Commit & open PR

```
[STEP 8/8] Commit & open PR
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

    ## Automated Checks
    Opening this PR against dev will automatically trigger:
    - dbt_build.yml             (model + test build)
    - terraform_apply.yml       (Unity Catalog tags + masks go live)
    - pii_compliance_check.yml  (non-interactive re-classification of the diff — runs only if both above pass)

  ⚠️ Creating this PR will trigger dbt_build, terraform_apply, and pii_compliance_check automatically.
Proceed? (y/n/back/all back)
```

`back` → return to STEP 7 (no git action needed, nothing committed yet).

If y → run `git add` → `commit` → `push` → `gh pr create` and display the PR URL.

```
✅ PII scan workflow complete
  PR: {URL}
  GitHub Actions (dbt_build / terraform_apply → pii_compliance_check) is now running.
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
