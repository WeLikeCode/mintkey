"""
Log-safe redaction helpers for structured and string log calls.

Provides a single ``redact_secret`` function that turns any raw credential
value into a safe display token (first 4 chars + "…") so it can be passed
to ``logger.*`` calls without triggering CodeQL py/clear-text-logging-sensitive-data.

Usage::

    from mintkey_models.log_redact import redact_secret

    # Authorization header (e.g. "Bearer mk_svckey_ABCDE12345")
    logger.info("bearer: authorization=%s", redact_secret(authorization))
    # → "bearer: authorization=Bear…"

    # Short ids or API keys
    logger.info("api-key-header: x_api_key=%s", redact_secret(x_api_key))
    # → "api-key-header: x_api_key=cana…"

    # True secrets (passwords, raw tokens without a predictable prefix):
    # pass them through the same helper — the first 4 chars are still safe.

Design notes:
- No external deps: stdlib only.
- Thread-safe: pure function, no shared state.
- Consistent with the existing ADR-0017.6 OTel redaction policy.
"""
from __future__ import annotations

_REDACT_SUFFIX = "…"  # "…"  (HORIZONTAL ELLIPSIS)


def redact_secret(value: str | None, *, visible: int = 4) -> str:
    """Return a redacted display token safe for log output.

    Parameters
    ----------
    value:
        The raw secret/credential string.  ``None`` is returned as the
        literal string ``"<None>"`` so log lines remain parseable.
    visible:
        Number of leading characters to keep (default 4).  Must be >= 0.

    Returns
    -------
    str
        ``value[:visible] + "…"`` when ``len(value) > visible``, otherwise
        ``"<redacted>"`` to avoid leaking short secrets in full.

    Examples
    --------
    >>> redact_secret("Bearer mk_svckey_ABCDE12345")
    'Bear…'
    >>> redact_secret("canary-demo-api-key")
    'cana…'
    >>> redact_secret(None)
    '<None>'
    >>> redact_secret("abc")   # shorter than visible threshold
    '<redacted>'
    """
    if value is None:
        return "<None>"
    if len(value) <= visible:
        return "<redacted>"
    return value[:visible] + _REDACT_SUFFIX
