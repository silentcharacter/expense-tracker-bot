"""Lightweight request-scoped performance tracer.

Emits structured JSON to stdout so GCF 2nd gen automatically indexes
each field in Cloud Logging (query via jsonPayload.operation, etc.).
"""

import json
import time
from contextlib import contextmanager
from typing import Optional


class RequestTracer:
    """Collects named step timings and logs a structured summary."""

    def __init__(self, operation: str, user_id: Optional[int] = None) -> None:
        self.operation = operation
        self.user_id = user_id
        self.steps: list[dict] = []
        self._start = time.perf_counter()

    @contextmanager
    def step(self, name: str):
        """Time a named step. Duration is recorded even if the step raises."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - t0) * 1000
            self.steps.append({"name": name, "duration_ms": round(duration_ms, 1)})

    def finish(self) -> dict:
        """Print structured JSON summary and return it."""
        total_ms = round((time.perf_counter() - self._start) * 1000, 1)
        summary = {
            "severity": "INFO",
            "message": f"{self.operation} completed in {total_ms:.0f}ms",
            "operation": self.operation,
            "user_id": self.user_id,
            "total_ms": total_ms,
            "steps": self.steps,
        }
        print(json.dumps(summary, ensure_ascii=False))
        return summary

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        self.finish()
