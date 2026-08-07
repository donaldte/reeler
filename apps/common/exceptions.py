"""Shared DRF exception handling.

Wraps DRF's default handler so every error response has a consistent shape:

    {"error": {"code": "not_found", "message": "..."}}

instead of DRF's default bare `{"detail": "..."}`, which is easier for a
single frontend (and third-party API consumers) to branch on.
"""

import logging

from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("reeler")


def reeler_exception_handler(exc: Exception, context: dict) -> Response | None:
    response = exception_handler(exc, context)
    if response is None:
        # Unhandled exception — DRF would otherwise let it propagate into a
        # raw 500. Log it with context and re-raise so Django's own error
        # handling / reporting still applies.
        logger.exception("Unhandled exception in %s", context.get("view"))
        return None

    code = getattr(exc, "default_code", exc.__class__.__name__.lower())
    detail = (
        response.data.get("detail", response.data)
        if isinstance(response.data, dict)
        else response.data
    )
    response.data = {"error": {"code": code, "message": detail}}
    return response
