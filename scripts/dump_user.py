#!/usr/bin/env python3
"""Dump a user's Firestore data to local CSV files.

Usage:
    python scripts/dump_user.py <telegram_id> [--out-dir ./dump]

Produces:
    <out_dir>/<telegram_id>_transactions.csv
    <out_dir>/<telegram_id>_categories.csv
    <out_dir>/<telegram_id>_recurring.csv
"""

import argparse
import csv
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dump_user")


def _load_dotenv_yaml() -> None:
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env.yaml")
    if not os.path.exists(env_path):
        return
    try:
        import yaml
        with open(env_path) as f:
            data = yaml.safe_load(f) or {}
        for k, v in data.items():
            if k not in os.environ:
                os.environ[k] = str(v)
    except Exception as exc:
        logger.warning("Could not load .env.yaml: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump a Firestore user's data to CSV")
    parser.add_argument("telegram_id", type=int, help="User's Telegram ID")
    parser.add_argument("--out-dir", default=".", help="Output directory (default: current dir)")
    args = parser.parse_args()

    _load_dotenv_yaml()
    os.environ["STORAGE_BACKEND"] = "firestore"

    from services.firestore_service import FirestoreService
    fs = FirestoreService()
    user_id = str(args.telegram_id)
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)

    # ── Transactions ──────────────────────────────────────────────────────────
    txns_path = os.path.join(out_dir, f"{user_id}_transactions.csv")
    txns = fs.get_transactions(user_id)
    with open(txns_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "id", "timestamp", "amount_local", "local_currency",
            "amount_base", "base_currency", "fx_rate",
            "category", "subcategory", "description", "source",
            "recurring", "recurring_template_id",
        ])
        for r in txns:
            writer.writerow([
                r.id, r.timestamp.isoformat(), r.amount_local, r.local_currency,
                r.amount_base, r.base_currency, r.fx_rate,
                r.category, r.subcategory, r.description, r.source.value,
                r.recurring, r.recurring_template_id,
            ])
    logger.info("Wrote %d transactions → %s", len(txns), txns_path)

    # ── Categories ────────────────────────────────────────────────────────────
    cats_path = os.path.join(out_dir, f"{user_id}_categories.csv")
    cats = fs.get_categories(user_id)
    with open(cats_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "subcategory", "label", "budget"])
        for cat in cats:
            writer.writerow([cat.slug, "", cat.label, cat.budget or ""])
            for sub in cat.subcategories:
                writer.writerow([cat.slug, sub.slug, sub.label, sub.budget or ""])
    logger.info("Wrote %d categories → %s", len(cats), cats_path)

    # ── Recurring ─────────────────────────────────────────────────────────────
    rec_path = os.path.join(out_dir, f"{user_id}_recurring.csv")
    items = fs.get_recurring(user_id)
    with open(rec_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "category", "subcategory", "description", "amount_local", "local_currency", "day_of_month"])
        for item in items:
            writer.writerow([
                item.get("id", ""), item.get("category", ""), item.get("subcategory", ""),
                item.get("description", ""), item.get("amount_local", ""),
                item.get("local_currency", ""), item.get("day_of_month", ""),
            ])
    logger.info("Wrote %d recurring items → %s", len(items), rec_path)


if __name__ == "__main__":
    main()
