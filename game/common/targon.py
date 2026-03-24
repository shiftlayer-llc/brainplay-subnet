"""Helpers for working with Targon endpoint identifiers and URLs."""

from __future__ import annotations

from urllib.parse import urlparse


def normalize_endpoint_url(endpoint: str) -> str:
    value = (endpoint or "").strip().rstrip("/")
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    if value.endswith(".serverless.targon.com") or value.endswith(".caas.targon.com"):
        return f"https://{value}"
    if value.startswith("wrk-"):
        return f"https://{value}.serverless.targon.com"
    return f"https://{value}.serverless.targon.com"


def extract_workload_uid(endpoint: str) -> str:
    value = (endpoint or "").strip().rstrip("/")
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        host = urlparse(value).netloc or ""
    else:
        host = value

    if host.endswith(".serverless.targon.com"):
        return host.split(".serverless.targon.com", 1)[0]
    if host.endswith(".caas.targon.com"):
        return host.split(".caas.targon.com", 1)[0]
    return host
