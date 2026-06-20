"""Claude-based PII classifier.

Reads a column list + sample data and asks Claude to classify each column
against GDPR categories, including multi-column quasi-identifier risk.
Used both interactively by /pii-scan and non-interactively by the CI
compliance check (pii_compliance_check.yml).
"""

import argparse
import csv
import json
import os
import random
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
SAMPLE_SIZE = 8

SYSTEM_PROMPT = """You are a GDPR data protection analyst reviewing columns in a data \
warehouse table for personal data risk. For each column, classify it into exactly \
one category:

- not_pii: no personal data risk
- direct_identifier: directly identifies a person on its own (GDPR Art. 4(1))
- special_category: GDPR Art. 9 special category data (health, religion, union \
  membership, biometric, sexual orientation, etc.)
- quasi_identifier: not risky alone, but can re-identify a person in combination \
  with other quasi-identifiers (GDPR Recital 26)

You must look at actual sample values, not just column names — a column named \
"notes" or "ref_id" can still contain personal data. Free text fields may contain \
embedded PII (addresses, phone numbers) even when most rows don't.

After classifying individual columns, identify any GROUPS of quasi_identifier \
columns that together create meaningful re-identification risk (e.g. postal_code \
+ birth_date + gender). Only group columns that are individually classified as \
quasi_identifier.

Respond by calling the `submit_classification` tool exactly once."""

CLASSIFICATION_TOOL = {
    "name": "submit_classification",
    "description": "Submit the PII classification result for all columns in the table.",
    "input_schema": {
        "type": "object",
        "properties": {
            "columns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "column": {"type": "string"},
                        "classification": {
                            "type": "string",
                            "enum": ["not_pii", "direct_identifier", "special_category", "quasi_identifier"],
                        },
                        "gdpr_basis": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "reasoning": {"type": "string"},
                    },
                    "required": ["column", "classification", "confidence", "reasoning"],
                },
            },
            "quasi_identifier_groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "columns": {"type": "array", "items": {"type": "string"}},
                        "risk": {"type": "string", "enum": ["high", "medium", "low"]},
                        "reasoning": {"type": "string"},
                    },
                    "required": ["columns", "risk", "reasoning"],
                },
            },
        },
        "required": ["columns", "quasi_identifier_groups"],
    },
}


def load_sample_from_csv(csv_path: Path, sample_size: int = SAMPLE_SIZE) -> tuple[list[str], list[dict]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    columns = list(rows[0].keys()) if rows else []
    sample = random.sample(rows, min(sample_size, len(rows)))
    return columns, sample


def build_user_message(table_name: str, columns: list[str], sample: list[dict]) -> str:
    sample_json = json.dumps(sample, indent=2, ensure_ascii=False)
    return f"""Table: {table_name}
Columns: {columns}

Sample rows ({len(sample)} of the table):
{sample_json}

Classify every column listed above."""


def classify(table_name: str, columns: list[str], sample: list[dict]) -> dict:
    client = anthropic.Anthropic()
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[CLASSIFICATION_TOOL],
        tool_choice={"type": "tool", "name": "submit_classification"},
        messages=[{"role": "user", "content": build_user_message(table_name, columns, sample)}],
    )
    for block in message.content:
        if block.type == "tool_use" and block.name == "submit_classification":
            return block.input
    raise RuntimeError("Claude did not return a classification")


def print_report(table_name: str, result: dict) -> None:
    print(f"\nPII Classification — {table_name}")
    print("-" * 70)
    for col in result["columns"]:
        print(f"  {col['column']:<22} {col['classification']:<20} ({col['confidence']})")
        print(f"      {col['reasoning']}")
    if result["quasi_identifier_groups"]:
        print("\n  Quasi-identifier groups:")
        for group in result["quasi_identifier_groups"]:
            print(f"    {' + '.join(group['columns'])}  [{group['risk']} risk]")
            print(f"      {group['reasoning']}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classify PII risk for a table's columns.")
    parser.add_argument("table_name", help="e.g. raw_customers, stg_customers")
    parser.add_argument("--csv", type=Path, help="path to a seed CSV to sample from")
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    parser.add_argument("--out", type=Path, help="write the raw JSON result to this path")
    args = parser.parse_args()

    csv_path = args.csv or Path(__file__).resolve().parent.parent.parent / "dbt" / "seeds" / f"{args.table_name}.csv"
    if not csv_path.exists():
        raise SystemExit(f"No CSV found at {csv_path}. Pass --csv explicitly for non-seed models.")

    columns, sample = load_sample_from_csv(csv_path, args.sample_size)
    result = classify(args.table_name, columns, sample)
    print_report(args.table_name, result)

    if args.out:
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"wrote classification JSON -> {args.out}")
