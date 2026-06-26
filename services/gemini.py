"""Gemini Flash client: audio/text → structured Expense JSON."""

import asyncio
import logging
import os
import random
from typing import Optional

from google import genai
from google.genai import errors
from google.genai import types

from models.expense import Expense
from models.category import UserCategory

logger = logging.getLogger(__name__)

_GEMINI_MAX_ATTEMPTS = 3
_GEMINI_RETRY_BASE_DELAY_SECONDS = 0.5
_GEMINI_RETRY_MAX_DELAY_SECONDS = 4.0
_TRANSIENT_GEMINI_STATUS_CODES = {429, 500, 502, 503, 504}

_SYSTEM_INSTRUCTION_TEMPLATE = """\
You are an expense parser. Extract the following fields from the user's input \
(voice transcript or text):

- amount: numeric value (float, > 0)
- currency: ISO 4217 code.
  Common mappings:
    "бат" / "baht" / "฿"        → THB
    "dollar" / "$" / "доллар"   → USD
    "euro" / "€" / "евро"       → EUR
    "pound" / "£" / "фунт"      → GBP
    "yen" / "¥" / "иена"        → JPY
    "ruble" / "руб" / "₽"       → RUB
  If the currency is not mentioned, use the user's default currency \
(provided below).
- category: one of the category slugs listed below.
- subcategory: MUST be one of the subcategory slugs listed for the chosen \
category below, or empty string if unclear. Do NOT invent new values.
- description: a brief description in the same language as the input (2–5 words).

Available categories and their subcategories:
{categories_with_subs}

Respond ONLY with valid JSON matching the schema. Do not add any extra text.
Default currency: {default_currency}
"""


def _build_system_instruction(categories: list[UserCategory], default_currency: str) -> str:
    """Render the system prompt with per-user categories and default currency."""
    lines = []
    for c in categories:
        subs = ", ".join(f"{s.slug} ({s.label})" for s in c.subcategories)
        lines.append(f"  {c.slug} ({c.label}): [{subs}]")
    return _SYSTEM_INSTRUCTION_TEMPLATE.format(
        categories_with_subs="\n".join(lines),
        default_currency=default_currency,
    )


class GeminiServiceError(Exception):
    """Raised when Gemini fails to parse the input."""


class GeminiService:
    """Wraps the Gemini API for expense parsing.

    Supports audio (OGG/WebM bytes from Telegram) and plain text.
    Uses structured JSON output via response_schema to guarantee a
    well-formed Expense on every call.
    """

    MODEL = "gemini-2.5-flash-lite"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._client = genai.Client(
            api_key=api_key or os.environ["GOOGLE_API_KEY"]
        )

    # ── Public API ──────────────────────────────────────────────────────────

    async def parse_audio(
        self,
        audio_bytes: bytes,
        default_currency: str,
        categories: list[UserCategory],
    ) -> Expense:
        """Parse an OGG voice message into a structured Expense.

        Args:
            audio_bytes:      Raw OGG/Opus bytes downloaded from Telegram.
            default_currency: User's default ISO 4217 currency code; used
                              when the user does not mention a currency.
            categories:       User's configured expense categories.

        Returns:
            Parsed Expense model.

        Raises:
            GeminiServiceError: When Gemini returns an unprocessable response.
        """
        system = _build_system_instruction(categories, default_currency)
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"),
                    types.Part.from_text(
                        text=f"Parse this voice expense. Default currency: {default_currency}"
                    ),
                ],
            )
        ]
        return await self._generate(system, contents)

    async def parse_text(
        self,
        text: str,
        default_currency: str,
        categories: list[UserCategory],
    ) -> Expense:
        """Parse a text message into a structured Expense.

        Args:
            text:             Raw text from the user (e.g. "350 baht food grab").
            default_currency: User's default ISO 4217 currency code.
            categories:       User's configured expense categories.

        Returns:
            Parsed Expense model.

        Raises:
            GeminiServiceError: When Gemini returns an unprocessable response.
        """
        system = _build_system_instruction(categories, default_currency)
        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=f"Parse this expense: {text}\nDefault currency: {default_currency}"
                    )
                ],
            )
        ]
        return await self._generate(system, contents)

    # ── Internal helpers ────────────────────────────────────────────────────

    @staticmethod
    def _is_transient_api_error(exc: Exception) -> bool:
        """Return True for Gemini errors that are worth retrying."""
        if not isinstance(exc, errors.APIError):
            return False
        code = getattr(exc, "code", None)
        return code in _TRANSIENT_GEMINI_STATUS_CODES

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        """Calculate exponential retry delay with small jitter."""
        base = _GEMINI_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
        delay = min(base, _GEMINI_RETRY_MAX_DELAY_SECONDS)
        return delay + random.uniform(0, 0.25)

    async def _generate(
        self,
        system_instruction: str,
        contents: list[types.Content],
    ) -> Expense:
        """Call Gemini and parse the response into an Expense.

        Raises:
            GeminiServiceError: On API or validation failure.
        """
        response = None
        for attempt in range(1, _GEMINI_MAX_ATTEMPTS + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=Expense,
                        temperature=0.1,
                    ),
                )
                break
            except Exception as exc:
                if self._is_transient_api_error(exc) and attempt < _GEMINI_MAX_ATTEMPTS:
                    delay = self._retry_delay(attempt)
                    logger.warning(
                        "Transient Gemini API error on attempt %s/%s; retrying in %.2fs: %s",
                        attempt,
                        _GEMINI_MAX_ATTEMPTS,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.exception("Gemini API error after %s attempt(s): %s", attempt, exc)
                raise GeminiServiceError(f"Gemini API error: {exc}") from exc

        if response is None:
            raise GeminiServiceError("Gemini API error: empty response")

        raw = response.text
        logger.debug("Gemini raw response: %s", raw)

        try:
            expense = Expense.model_validate_json(raw)
        except Exception as exc:
            logger.exception("Failed to parse Gemini response: %s — raw: %s", exc, raw)
            raise GeminiServiceError(f"Invalid JSON from Gemini: {exc}") from exc

        return expense
