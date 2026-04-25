"""Firestore-backed storage — drop-in replacement for SheetsService."""

import logging
import os
import uuid as _uuid
from datetime import date, datetime
from typing import Optional

from google.cloud import firestore as _fs

from models.expense import ExpenseRecord, User
from models.category import UserCategory, UserSubcategory, default_user_categories

logger = logging.getLogger(__name__)

# {user_id: list[UserCategory]} — invalidated on writes
_category_cache: dict[str, list] = {}


class FirestoreService:
    """CRUD operations backed by Cloud Firestore.

    The ``user_id`` parameter in all per-user methods is ``str(telegram_id)``,
    which callers pass as ``user.spreadsheet_id`` after migration.

    Authentication uses Application Default Credentials automatically.
    """

    def __init__(self, client: Optional[_fs.Client] = None) -> None:
        if client is None:
            db_name = os.environ.get("FIRESTORE_DATABASE", "(default)")
            client = _fs.Client(database=db_name)
        self._db = client

    # ── Path helpers ─────────────────────────────────────────────────────────

    def _user_ref(self, user_id: str) -> _fs.DocumentReference:
        return self._db.collection("users").document(user_id)

    def _tx_col(self, user_id: str) -> _fs.CollectionReference:
        return self._user_ref(user_id).collection("transactions")

    def _cat_col(self, user_id: str) -> _fs.CollectionReference:
        return self._user_ref(user_id).collection("categories")

    def _rec_col(self, user_id: str) -> _fs.CollectionReference:
        return self._user_ref(user_id).collection("recurring")

    # ── Transactions ─────────────────────────────────────────────────────────

    def append_transaction(self, user_id: str, record: ExpenseRecord) -> None:
        self._tx_col(user_id).document(record.id).set(record.to_firestore_dict())
        logger.info("Appended transaction %s for user %s", record.id, user_id)

    def delete_last_transaction(self, user_id: str) -> Optional[ExpenseRecord]:
        docs = list(
            self._tx_col(user_id)
            .order_by("timestamp", direction=_fs.Query.DESCENDING)
            .limit(1)
            .stream()
        )
        if not docs:
            return None
        data = docs[0].to_dict()
        docs[0].reference.delete()
        try:
            return ExpenseRecord.from_firestore_dict(data)
        except Exception as exc:
            logger.warning("Could not parse deleted transaction: %s", exc)
            return None

    def delete_transaction_by_id(self, user_id: str, expense_id: str) -> Optional[ExpenseRecord]:
        doc = self._tx_col(user_id).document(expense_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        doc.reference.delete()
        logger.info("Deleted transaction %s for user %s", expense_id, user_id)
        try:
            return ExpenseRecord.from_firestore_dict(data)
        except Exception as exc:
            logger.warning("Could not parse deleted transaction: %s", exc)
            return None

    def _get_all_transactions(self, user_id: str) -> list[ExpenseRecord]:
        docs = list(
            self._tx_col(user_id)
            .order_by("timestamp", direction=_fs.Query.DESCENDING)
            .stream()
        )
        records: list[ExpenseRecord] = []
        for doc in docs:
            try:
                records.append(ExpenseRecord.from_firestore_dict(doc.to_dict()))
            except Exception:
                continue
        return records

    def get_transactions(
        self,
        user_id: str,
        since: Optional[date] = None,
        until: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> list[ExpenseRecord]:
        all_records = self._get_all_transactions(user_id)

        if since or until:
            filtered = []
            for r in all_records:
                d = r.timestamp.date()
                if since and d < since:
                    continue
                if until and d > until:
                    continue
                filtered.append(r)
        else:
            filtered = list(all_records)

        if limit:
            filtered = filtered[:limit]
        return filtered

    def get_last_n_transactions(self, user_id: str, n: int = 10) -> list[ExpenseRecord]:
        return self.get_transactions(user_id, limit=n)

    def update_transaction_category(
        self, user_id: str, record_id: str, category: str, subcategory: str
    ) -> bool:
        doc = self._tx_col(user_id).document(record_id).get()
        if not doc.exists:
            return False
        doc.reference.update({"category": category, "subcategory": subcategory})

        logger.info("Updated category for transaction %s (user %s): %s/%s", record_id, user_id, category, subcategory)
        return True

    def update_transaction_description(
        self, user_id: str, record_id: str, description: str
    ) -> bool:
        doc = self._tx_col(user_id).document(record_id).get()
        if not doc.exists:
            return False
        doc.reference.update({"description": description})

        logger.info("Updated description for transaction %s (user %s)", record_id, user_id)
        return True

    def clear_all_transactions(self, user_id: str) -> int:
        docs = list(self._tx_col(user_id).stream())
        if not docs:
            return 0
        for i in range(0, len(docs), 500):
            batch = self._db.batch()
            for doc in docs[i : i + 500]:
                batch.delete(doc.reference)
            batch.commit()

        logger.info("Cleared %d transactions for user %s", len(docs), user_id)
        return len(docs)

    # ── Categories ────────────────────────────────────────────────────────────

    def get_categories(self, user_id: str) -> list[UserCategory]:
        if user_id in _category_cache:
            return _category_cache[user_id]

        categories: list[UserCategory] = []
        try:
            docs = list(self._cat_col(user_id).stream())
            for doc in docs:
                data = doc.to_dict()
                subs = [
                    UserSubcategory(
                        slug=s["slug"],
                        label=s.get("label", s["slug"]),
                        budget=s.get("budget"),
                    )
                    for s in data.get("subcategories", [])
                ]
                cat_budget = data.get("budget")
                if cat_budget is None:
                    sub_total = sum(s.budget for s in subs if s.budget is not None)
                    if sub_total > 0:
                        cat_budget = sub_total
                categories.append(UserCategory(
                    slug=data["slug"],
                    label=data.get("label", data["slug"]),
                    budget=cat_budget,
                    subcategories=subs,
                ))
        except Exception as exc:
            logger.warning("Could not read categories for user %s: %s", user_id, exc)

        if not categories:
            categories = default_user_categories()
            try:
                self.ensure_categories_sheet(user_id)
            except Exception as exc:
                logger.warning("Could not seed categories for user %s: %s", user_id, exc)

        _category_cache[user_id] = categories
        return categories

    def ensure_categories_sheet(self, user_id: str) -> None:
        docs = list(self._cat_col(user_id).limit(1).stream())
        if docs:
            return
        batch = self._db.batch()
        for cat in default_user_categories():
            doc_ref = self._cat_col(user_id).document(cat.slug)
            batch.set(doc_ref, {
                "slug": cat.slug,
                "label": cat.label,
                "budget": None,
                "subcategories": [
                    {"slug": s.slug, "label": s.label, "budget": None}
                    for s in cat.subcategories
                ],
            })
        batch.commit()
        _category_cache.pop(user_id, None)
        logger.info("Seeded default categories for user %s", user_id)

    def get_budgets(self, user_id: str) -> dict[str, float]:
        result: dict[str, float] = {}
        for cat in self.get_categories(user_id):
            if cat.budget is not None:
                result[cat.slug] = cat.budget
            else:
                sub_total = sum(s.budget for s in cat.subcategories if s.budget is not None)
                if sub_total > 0:
                    result[cat.slug] = sub_total
        return result

    def update_subcategory_budgets(self, user_id: str, budgets: dict[str, float]) -> None:
        """budgets keys are 'category/subcategory'."""
        cat_slugs = {k.split("/")[0] for k in budgets}
        for cat_slug in cat_slugs:
            cat_ref = self._cat_col(user_id).document(cat_slug)
            cat_doc = cat_ref.get()
            if not cat_doc.exists:
                continue
            data = cat_doc.to_dict()
            subs = data.get("subcategories", [])
            updated = False
            for s in subs:
                key = f"{cat_slug}/{s['slug']}"
                if key in budgets:
                    s["budget"] = budgets[key]
                    updated = True
            if updated:
                cat_ref.update({"subcategories": subs})

        _category_cache.pop(user_id, None)
        logger.info("Updated subcategory budgets for user %s", user_id)

    def update_category_budgets(self, user_id: str, budgets: dict[str, float]) -> None:
        for slug, amount in budgets.items():
            cat_ref = self._cat_col(user_id).document(slug)
            if cat_ref.get().exists:
                cat_ref.update({"budget": amount})

        _category_cache.pop(user_id, None)
        logger.info("Updated category budgets for user %s", user_id)

    def add_category(
        self, user_id: str, slug: str, label: str, budget: Optional[float] = None
    ) -> None:
        existing = self.get_categories(user_id)
        if any(c.slug == slug for c in existing):
            raise ValueError(f"Category '{slug}' already exists")
        self._cat_col(user_id).document(slug).set({
            "slug": slug, "label": label, "budget": budget, "subcategories": [],
        })

        _category_cache.pop(user_id, None)
        logger.info("Added category '%s' for user %s", slug, user_id)

    def add_subcategory(
        self, user_id: str, cat_slug: str, sub_slug: str, label: str
    ) -> None:
        cat_ref = self._cat_col(user_id).document(cat_slug)
        cat_doc = cat_ref.get()
        if not cat_doc.exists:
            raise ValueError(f"Category '{cat_slug}' not found")
        data = cat_doc.to_dict()
        subs = data.get("subcategories", [])
        if any(s["slug"] == sub_slug for s in subs):
            raise ValueError(f"Subcategory '{sub_slug}' already exists in '{cat_slug}'")
        subs.append({"slug": sub_slug, "label": label, "budget": None})
        cat_ref.update({"subcategories": subs})

        _category_cache.pop(user_id, None)
        logger.info("Added subcategory '%s/%s' for user %s", cat_slug, sub_slug, user_id)

    def delete_category(self, user_id: str, cat_slug: str) -> bool:
        doc = self._cat_col(user_id).document(cat_slug).get()
        if not doc.exists:
            return False
        doc.reference.delete()

        _category_cache.pop(user_id, None)
        logger.info("Deleted category '%s' for user %s", cat_slug, user_id)
        return True

    def delete_subcategory(self, user_id: str, cat_slug: str, sub_slug: str) -> bool:
        cat_ref = self._cat_col(user_id).document(cat_slug)
        cat_doc = cat_ref.get()
        if not cat_doc.exists:
            return False
        data = cat_doc.to_dict()
        subs = data.get("subcategories", [])
        new_subs = [s for s in subs if s["slug"] != sub_slug]
        if len(new_subs) == len(subs):
            return False
        cat_ref.update({"subcategories": new_subs})

        _category_cache.pop(user_id, None)
        logger.info("Deleted subcategory '%s/%s' for user %s", cat_slug, sub_slug, user_id)
        return True

    # ── Recurring expenses ────────────────────────────────────────────────────

    def get_recurring(self, user_id: str) -> list[dict]:
        docs = list(self._rec_col(user_id).stream())
        return [doc.to_dict() for doc in docs]

    def add_recurring(self, user_id: str, entry: dict) -> None:
        eid = entry.get("id") or str(_uuid.uuid4())
        data = {**entry, "id": eid}
        self._rec_col(user_id).document(eid).set(data)

    def delete_recurring(self, user_id: str, entry_id: str) -> bool:
        doc = self._rec_col(user_id).document(entry_id).get()
        if not doc.exists:
            return False
        doc.reference.delete()
        return True

    # ── Master Registry ───────────────────────────────────────────────────────

    def find_user(self, telegram_id: int) -> Optional[User]:
        doc = self._db.collection("users").document(str(telegram_id)).get()
        if not doc.exists:
            return None
        try:
            return User.from_firestore_dict(doc.to_dict())
        except Exception as exc:
            logger.error("Malformed user document for %s: %s", telegram_id, exc)
            return None

    def get_all_active_users(self) -> list[User]:
        from models.expense import UserStatus
        docs = self._db.collection("users").where("status", "==", UserStatus.active.value).stream()
        users: list[User] = []
        for doc in docs:
            try:
                users.append(User.from_firestore_dict(doc.to_dict()))
            except Exception as exc:
                logger.error("Malformed user document: %s", exc)
        return users

    def register_user(self, user: User) -> None:
        self._db.collection("users").document(str(user.telegram_id)).set(user.to_firestore_dict())
        logger.info("Registered user %s (%s)", user.telegram_id, user.display_name)

    def append_feedback(
        self, telegram_id: int, username: str, display_name: str, feedback: str
    ) -> None:
        self._db.collection("feedback").add({
            "telegram_id": telegram_id,
            "username": username,
            "display_name": display_name,
            "feedback": feedback,
            "created_at": datetime.utcnow(),
        })
        logger.info("Appended feedback from %s", telegram_id)

    def update_user_email(self, telegram_id: int, email: str) -> bool:
        ref = self._db.collection("users").document(str(telegram_id))
        if not ref.get().exists:
            return False
        ref.update({"email": email})
        return True

    def update_user_settings(
        self,
        telegram_id: int,
        base_currency: Optional[str] = None,
        default_currency: Optional[str] = None,
        budget_alerts: Optional[bool] = None,
        weekly_summary: Optional[bool] = None,
        insights: Optional[bool] = None,
    ) -> bool:
        ref = self._db.collection("users").document(str(telegram_id))
        if not ref.get().exists:
            return False
        updates: dict = {}
        if base_currency is not None:
            updates["base_currency"] = base_currency.upper()
        if default_currency is not None:
            updates["default_currency"] = default_currency.upper()
        if budget_alerts is not None:
            updates["budget_alerts"] = budget_alerts
        if weekly_summary is not None:
            updates["weekly_summary"] = weekly_summary
        if insights is not None:
            updates["insights"] = insights
        if updates:
            ref.update(updates)
        return True

    # ── Initialisation (no-ops — Firestore is schemaless) ─────────────────────

    def ensure_transactions_header(self, user_id: str) -> None:
        pass

    def ensure_registry_header(self) -> None:
        pass
