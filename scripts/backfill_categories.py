"""Backfill missing categories/subcategories from the Transactions sheet.

For each active user, reads all transactions and adds any (category, subcategory)
pair that exists in Transactions but is absent from the Categories sheet.

Category labels are taken from the hardcoded registry when available;
unknown slugs get a title-cased label derived from the slug.

Usage (from project root):
    python scripts/backfill_categories.py [--dry-run] [--user <telegram_id>]

Options:
    --dry-run        Print what would be added without writing to Sheets.
    --user <id>      Process only the user with this Telegram ID.
"""

import argparse
import os
import sys
from pathlib import Path

# ── Env setup ────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import yaml  # noqa: E402


def _load_env() -> None:
    env_file = _ROOT / ".env.yaml"
    if not env_file.exists():
        sys.exit(f"Error: {env_file} not found")
    with open(env_file) as f:
        data = yaml.safe_load(f)
    for key, value in (data or {}).items():
        if value is not None:
            os.environ.setdefault(key, str(value))
    # Service account key for local auth (same as integration tests)
    sa_file = _ROOT / "credentials.json"
    if sa_file.exists():
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", str(sa_file))


_load_env()

# ── Imports (after env is set) ───────────────────────────────────────────────

from models.category import category_label, CATEGORY_BY_SLUG  # noqa: E402
from models.expense import User  # noqa: E402
from services.sheets import SheetsService  # noqa: E402


def _slug_to_label(slug: str) -> str:
    """Best-effort human label for a slug."""
    cat = CATEGORY_BY_SLUG.get(slug)
    if cat:
        return cat.label
    return slug.replace("_", " ").title()


def backfill_user(
    sheets: SheetsService,
    user: User,
    dry_run: bool,
) -> tuple[int, int]:
    """Add missing categories/subcategories for one user.

    Returns:
        (categories_added, subcategories_added)
    """
    # Collect (category, subcategory) pairs from all transactions.
    transactions = sheets.get_transactions(user.spreadsheet_id)
    seen: dict[str, set[str]] = {}
    for tx in transactions:
        cat = tx.category.strip().lower()
        sub = tx.subcategory.strip().lower() if tx.subcategory else ""
        if cat:
            seen.setdefault(cat, set()).add(sub)

    if not seen:
        return 0, 0

    # Current categories in the sheet.
    existing = sheets.get_categories(user.spreadsheet_id)
    existing_cats = {c.slug: {s.slug for s in c.subcategories} for c in existing}

    cats_added = 0
    subs_added = 0

    for cat_slug, sub_slugs in sorted(seen.items()):
        # Add missing category row.
        if cat_slug not in existing_cats:
            label = _slug_to_label(cat_slug)
            print(f"  + category  {cat_slug!r}  ({label})")
            if not dry_run:
                sheets.add_category(user.spreadsheet_id, cat_slug, label)
            existing_cats[cat_slug] = set()
            cats_added += 1

        # Add missing subcategory rows.
        for sub_slug in sorted(sub_slugs):
            if not sub_slug:
                continue
            if sub_slug not in existing_cats[cat_slug]:
                # Try to get label from hardcoded registry.
                cat_def = CATEGORY_BY_SLUG.get(cat_slug)
                sub_def = next(
                    (s for s in (cat_def.subcategories if cat_def else []) if s.slug == sub_slug),
                    None,
                )
                label = sub_def.label if sub_def else sub_slug.replace("_", " ").title()
                print(f"    + subcategory  {cat_slug}/{sub_slug}  ({label})")
                if not dry_run:
                    sheets.add_subcategory(user.spreadsheet_id, cat_slug, sub_slug, label)
                existing_cats[cat_slug].add(sub_slug)
                subs_added += 1

    return cats_added, subs_added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--user", type=int, metavar="TELEGRAM_ID", help="Process only this user")
    args = parser.parse_args()

    sheets = SheetsService()

    users: list[User] = sheets.get_all_active_users()
    if args.user:
        users = [u for u in users if u.telegram_id == args.user]
        if not users:
            sys.exit(f"User {args.user} not found in registry")

    if args.dry_run:
        print("=== DRY RUN — no changes will be written ===\n")

    total_cats = 0
    total_subs = 0

    for user in users:
        print(f"User {user.telegram_id} ({user.display_name})")
        cats, subs = backfill_user(sheets, user, dry_run=args.dry_run)
        if cats == 0 and subs == 0:
            print("  nothing to add")
        else:
            print(f"  → {cats} categories, {subs} subcategories {'(dry run)' if args.dry_run else 'added'}")
        total_cats += cats
        total_subs += subs
        print()

    print(f"Done. Total: {total_cats} categories, {total_subs} subcategories added.")


if __name__ == "__main__":
    main()
