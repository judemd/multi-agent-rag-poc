"""Seeded support fixtures. Expected answers are never added to the index."""
import argparse
import csv
import io
import json
import random
from pathlib import Path
from reportlab.pdfgen import canvas

def generate(seed=42, tickets=100):
    rng = random.Random(seed)
    products = [{"product_id": f"P{i:03}", "name": f"Beacon {i}", "price_gbp": 49.0 + i * 10,
                 "available": i % 4 != 0, "released": f"2025-{i:02}-01",
                 "specs": {"battery_hours": 8 + i, "wireless": True},
                 "notes": None if i % 3 == 0 else "USB-C charging"} for i in range(1, 13)]
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=["ticket_id", "product_id", "customer_id", "opened", "resolved", "issue", "resolution"])
    writer.writeheader()
    rows = []
    for i in range(tickets):
        p = rng.choice(products)
        rows.append({"ticket_id": f"T{i:04}", "product_id": p["product_id"], "customer_id": f"C{rng.randrange(20):03}",
                     "opened": f"2026-09-{1 + i % 28:02}", "resolved": i % 5 != 0,
                     "issue": "charging indicator flashes", "resolution": "" if i % 5 == 0 else "Use a 5V USB-C adapter; hold power for 10 seconds."})
    if rows:
        rows[-1] = dict(rows[0])
    writer.writerows(rows)
    files = {"tickets.csv": out.getvalue().encode(), "products.json": json.dumps(products, indent=2).encode()}
    policies = {
        "returns.txt": "POL-RET: Unused Beacon products may be returned within 30 days of delivery. Contact support with the product_id and order receipt.",
        "warranty.txt": "POL-WAR: Beacon products P001 through P012 have a 24-month limited warranty for manufacturing defects. Accidental water damage is excluded.",
        "shipping.txt": "POL-SHIP: Standard UK delivery takes 3 to 5 working days. Contact support with the order ID after 5 working days.",
    }
    files.update({name: value.encode() for name, value in policies.items()})
    for i in range(1, 4):
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, invariant=1)
        pdf.drawString(50, 790, f"Beacon {i} manual - product_id P{i:03}")
        pdf.drawString(50, 765, "Charging: use a 5V USB-C adapter. Reset: hold power for 10 seconds.")
        pdf.drawString(50, 740, f"Expected battery runtime: {8+i} hours. Warranty: see POL-WAR.")
        pdf.save()
        files[f"manual_P{i:03}.pdf"] = buffer.getvalue()
    references = [
        {"question": "What is the return window for unused Beacon products?", "expected": "30 days after delivery", "sources": ["returns.txt"]},
        {"question": "How do I reset Beacon 1?", "expected": "Hold power for 10 seconds", "sources": ["manual_P001.pdf"]},
        {"question": "Is accidental water damage covered?", "expected": "No", "sources": ["warranty.txt"]},
        {"question": "What is Beacon 1 battery runtime?", "expected": "9 hours", "sources": ["products.json", "manual_P001.pdf"]},
        {"question": "What is the CEO's private phone number?", "expected": "Insufficient evidence", "sources": []},
    ]
    return files, references

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/synthetic")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    path = Path(args.output)
    path.mkdir(parents=True, exist_ok=True)
    files, references = generate(args.seed)
    for name, content in files.items():
        (path / name).write_bytes(content)
    (path / "reference_questions.json").write_text(json.dumps(references, indent=2), encoding="utf-8")
    print(f"Generated {len(files)} source files plus reference questions in {path}")
