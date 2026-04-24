"""Storage backend factory — returns SheetsService or FirestoreService based on STORAGE_BACKEND env var."""

import os

_storage = None


def get_storage():
    """Return the module-level storage singleton (SheetsService or FirestoreService).

    Reads STORAGE_BACKEND env var: 'firestore' → FirestoreService, anything else → SheetsService.
    """
    global _storage
    if _storage is None:
        backend = os.environ.get("STORAGE_BACKEND", "sheets")
        if backend == "firestore":
            from services.firestore_service import FirestoreService
            _storage = FirestoreService()
        else:
            from services.sheets import SheetsService
            _storage = SheetsService()
    return _storage
