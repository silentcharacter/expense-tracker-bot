#!/usr/bin/env python3
"""One-time migration: Google Sheets → Firestore.

Reads all users from the Master Registry sheet, then for each user migrates
their Transactions, Categories, and Recurring data to Firestore.

Idempotent: every write uses set() with the document's UUID/slug as ID, so
re-running will overwrite without creating duplicates.  Safe to run while the
bot is still pointing at Sheets; the bot can be cut over to Firestore
afterwards by setting STORAGE_BACKEND=firestore.

Usage:
    python scripts/migrate_sheets_to_firestore.py [--dry-run]

Env vars required (same as the bot):
    REGISTRY_SHEET_ID, GOOGLE_APPLICATION_CREDENTIALS (or ADC)
"""

import argparse
import logging
import os
import sys
import time

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("migrate")


def _load_dotenv_yaml() -> None:
    """Load .env.yaml into os.environ for local dev if it exists."""
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
        logger.info("Loaded env from .env.yaml")
    except Exception as exc:
        logger.warning("Could not load .env.yaml: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Sheets data to Firestore")
    parser.add_argument("--dry-run", action="store_true", help="Log what would be written, without touching Firestore")
    args = parser.parse_args()
    dry_run: bool = args.dry_run

    _load_dotenv_yaml()

    if dry_run:
        logger.info("DRY RUN — no data will be written to Firestore")

    # Build Sheets service using OAuth refresh token (ADC lacks Sheets scope locally)
    os.environ["STORAGE_BACKEND"] = "sheets"
    from services.sheets import SheetsService
    import gspread
    from google.oauth2.credentials import Credentials as OAuthCredentials
    from google.auth.transport.requests import Request

    creds = OAuthCredentials(
        token=None,
        refresh_token=os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_OAUTH_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    gc = gspread.Client(auth=creds)
    sheets = SheetsService(client=gc)

    # Build Firestore service directly (not through factory)
    from services.firestore_service import FirestoreService
    fs = FirestoreService()

    # Fetch all users from Registry
    logger.info("Fetching all users from Registry…")
    users = sheets.get_all_active_users()
    # Also fetch suspended users so we migrate everything
    try:
        from models.expense import User
        from gspread.utils import ValueRenderOption
        sheet = sheets._get_sheet(sheets._registry_id, "Registry")
        rows = sheet.get_all_records(
            expected_headers=User.required_registry_headers(),
            value_render_option=ValueRenderOption.unformatted,
        )
        all_users: list[User] = []
        for row in rows:
            try:
                all_users.append(User(**row))
            except Exception as exc:
                logger.warning("Skipping malformed registry row: %s", exc)
    except Exception as exc:
        logger.warning("Could not read all users, falling back to active only: %s", exc)
        all_users = users

    logger.info("Found %d users to migrate", len(all_users))

    totals = {"users": 0, "transactions": 0, "categories": 0, "recurring": 0, "errors": 0}

    for user in all_users:
        tid = user.telegram_id
        firestore_user_id = str(tid)
        logger.info("--- Migrating user %s (%s) ---", tid, user.display_name)

        # ── User document ────────────────────────────────────────────────────
        user_data = user.to_firestore_dict()
        # In Firestore, spreadsheet_id = str(telegram_id) so all code using
        # user.spreadsheet_id continues to work transparently.
        legacy_sid = user.spreadsheet_id
        user_data["spreadsheet_id"] = firestore_user_id
        user_data["legacy_spreadsheet_id"] = legacy_sid

        if not dry_run:
            fs._db.collection("users").document(firestore_user_id).set(user_data)
        logger.info("  User doc written (legacy_spreadsheet_id=%s)", legacy_sid)
        totals["users"] += 1

        # ── Transactions ─────────────────────────────────────────────────────
        try:
            txns = sheets.get_transactions(legacy_sid)
            logger.info("  Transactions: %d rows", len(txns))
            if not dry_run and txns:
                batch = fs._db.batch()
                for i, r in enumerate(txns):
                    doc_ref = fs._tx_col(firestore_user_id).document(r.id)
                    batch.set(doc_ref, r.to_firestore_dict())
                    if (i + 1) % 500 == 0:
                        batch.commit()
                        batch = fs._db.batch()
                batch.commit()
            totals["transactions"] += len(txns)
        except Exception as exc:
            logger.error("  Transactions migration failed for user %s: %s", tid, exc)
            totals["errors"] += 1

        # ── Categories ───────────────────────────────────────────────────────
        try:
            cats = sheets.get_categories(legacy_sid)
            logger.info("  Categories: %d", len(cats))
            if not dry_run and cats:
                batch = fs._db.batch()
                for cat in cats:
                    doc_ref = fs._cat_col(firestore_user_id).document(cat.slug)
                    batch.set(doc_ref, {
                        "slug": cat.slug,
                        "label": cat.label,
                        "budget": cat.budget,
                        "subcategories": [
                            {"slug": s.slug, "label": s.label, "budget": s.budget}
                            for s in cat.subcategories
                        ],
                    })
                batch.commit()
            totals["categories"] += len(cats)
        except Exception as exc:
            logger.error("  Categories migration failed for user %s: %s", tid, exc)
            totals["errors"] += 1

        # ── Recurring templates ───────────────────────────────────────────────
        try:
            items = sheets.get_recurring(legacy_sid)
            logger.info("  Recurring: %d", len(items))
            if not dry_run and items:
                batch = fs._db.batch()
                for item in items:
                    eid = str(item.get("id", "")).strip()
                    if not eid:
                        continue
                    doc_ref = fs._rec_col(firestore_user_id).document(eid)
                    batch.set(doc_ref, item)
                batch.commit()
            totals["recurring"] += len(items)
        except Exception as exc:
            logger.error("  Recurring migration failed for user %s: %s", tid, exc)
            totals["errors"] += 1

        # Pause between users to avoid Sheets read quota (300 req/min/user)
        time.sleep(3)

    logger.info(
        "Migration complete%s: %d users, %d transactions, %d categories, %d recurring, %d errors",
        " (DRY RUN)" if dry_run else "",
        totals["users"], totals["transactions"], totals["categories"],
        totals["recurring"], totals["errors"],
    )

    if totals["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
