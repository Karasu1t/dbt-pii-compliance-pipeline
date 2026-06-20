"""Generates synthetic seed data for the dbt PII compliance pipeline.

All data is fake (Faker, seeded for reproducibility). The column design is
deliberate, not random — it covers four classification difficulty levels so
the Claude-based classifier has something real to prove:

1. Obvious direct identifiers   (email, full_name, phone_number)
2. An obfuscated-name identifier (national_id_ref — looks like a generic
   reference number, but the values are a government-ID-shaped string)
3. A quasi-identifier combination (postal_code + birth_date + gender —
   individually harmless, re-identifying together)
4. PII embedded in unstructured free text (support_notes occasionally
   contains an address or phone number inline)

A classifier that only pattern-matches column names will catch (1) and miss
(2), (3), and (4).
"""

import csv
import random
from pathlib import Path

from faker import Faker

SEED = 42
N_CUSTOMERS = 500
N_ORDERS = 1500
FREE_TEXT_PII_RATE = 0.15

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "dbt" / "seeds"

fake = Faker()
Faker.seed(SEED)
random.seed(SEED)

GENDERS = ["female", "male"]
LOYALTY_TIERS = ["bronze", "silver", "gold", "platinum"]

GENERIC_NOTES = [
    "Customer requested a refund for a damaged item.",
    "Asked about delivery delay, resolved within 2 days.",
    "Inquired about loyalty point balance.",
    "Reported a billing discrepancy, corrected.",
    "Requested invoice reissue for accounting purposes.",
]


def make_national_id_ref() -> str:
    # Synthetic, non-real ID format — shaped like a government identifier,
    # not a valid one. Column name deliberately avoids the word "id_number"
    # to test whether classification relies on values, not just naming.
    return f"{random.randint(10, 99)} {random.randint(100, 999)} {random.randint(100, 999)} {random.randint(0, 9)}"


def make_support_note() -> str:
    note = random.choice(GENERIC_NOTES)
    if random.random() < FREE_TEXT_PII_RATE:
        leak_type = random.choice(["address", "phone"])
        if leak_type == "address":
            note += f" Please ship the replacement to {fake.street_address()}, {fake.city()}."
        else:
            note += f" Customer can be reached directly at {fake.phone_number()}."
    return note


def generate_customers(n: int) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        rows.append(
            {
                "customer_id": i,
                "full_name": fake.name(),
                "email": fake.unique.email(),
                "phone_number": fake.phone_number(),
                "postal_code": fake.postcode(),
                "birth_date": fake.date_of_birth(minimum_age=18, maximum_age=85).isoformat(),
                "gender": random.choice(GENDERS),
                "national_id_ref": make_national_id_ref(),
                "signup_date": fake.date_between(start_date="-5y", end_date="today").isoformat(),
                "loyalty_tier": random.choice(LOYALTY_TIERS),
                "support_notes": make_support_note(),
            }
        )
    return rows


def generate_orders(n: int, n_customers: int) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        rows.append(
            {
                "order_id": i,
                "customer_id": random.randint(1, n_customers),
                "product_id": f"P-{random.randint(1000, 9999)}",
                "order_total": round(random.uniform(9.99, 499.99), 2),
                "order_date": fake.date_between(start_date="-2y", end_date="today").isoformat(),
                "shipping_address": fake.address().replace("\n", ", "),
            }
        )
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows -> {path}")


if __name__ == "__main__":
    customers = generate_customers(N_CUSTOMERS)
    orders = generate_orders(N_ORDERS, N_CUSTOMERS)

    write_csv(customers, OUTPUT_DIR / "raw_customers.csv")
    write_csv(orders, OUTPUT_DIR / "raw_orders.csv")

    leaked = sum(1 for c in customers if "shipping" in c["support_notes"] or "reached directly" in c["support_notes"])
    print(f"support_notes rows with embedded PII: {leaked}/{N_CUSTOMERS}")
