"""Postgres persistence helpers."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SECRET_QUERY_PARAMETERS = frozenset(
    {
        "pass",
        "passwd",
        "password",
        "pwd",
        "sslpassword",
    }
)


def _redact_query_parameters(query: str) -> str:
    if not query:
        return ""

    return urlencode(
        [
            (
                key,
                "***" if key.lower() in _SECRET_QUERY_PARAMETERS else value,
            )
            for key, value in parse_qsl(query, keep_blank_values=True)
        ],
        doseq=True,
        safe="*",
    )


def redact_postgres_dsn(dsn: str) -> str:
    normalized = dsn.strip()
    if not normalized:
        return ""

    parsed = urlsplit(normalized)
    netloc = parsed.netloc
    if parsed.netloc and "@" in parsed.netloc:
        userinfo, hostinfo = parsed.netloc.rsplit("@", 1)
        username, separator, _password = userinfo.partition(":")
        if separator:
            netloc = f"{username}:***@{hostinfo}"

    return urlunsplit(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            _redact_query_parameters(parsed.query),
            parsed.fragment,
        )
    )


__all__ = ("redact_postgres_dsn",)
