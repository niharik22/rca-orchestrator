"""The RCA-side adapter for Jira Intelligence's loopback collection API."""

from __future__ import annotations

import json
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .evidence import CollectionEvidence, evidence_from_intelligence_envelope


class JiraIntelligenceError(RuntimeError):
    """Raised when Jira Intelligence cannot create or return a Collection Run."""


class JiraIntelligenceClient(Protocol):
    def collect_or_reuse(self, issue_key: str, rca_run_id: str) -> CollectionEvidence: ...


class JiraIntelligenceHttpClient:
    """Collects Jira evidence only through the local Jira Intelligence API."""

    def __init__(
        self,
        base_url: str,
        request: Callable[[Request], bytes] | None = None,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
            raise ValueError("Jira Intelligence URL must use http://127.0.0.1.")
        self._base_url = base_url.rstrip("/")
        self._request = request or _read_response

    def collect_or_reuse(self, issue_key: str, rca_run_id: str) -> CollectionEvidence:
        encoded_issue_key = quote(issue_key.upper(), safe="")
        request = Request(
            f"{self._base_url}/v1/issues/{encoded_issue_key}/intelligence",
            data=json.dumps(
                {"download_attachments": False, "orchestration_run_id": rca_run_id}
            ).encode("utf-8"),
            headers={"Content-Type": "application/json", "Idempotency-Key": f"rca-collection-{rca_run_id}"},
            method="POST",
        )
        try:
            response = self._request(request)
            payload = json.loads(response.decode("utf-8"))
        except (HTTPError, URLError, OSError, json.JSONDecodeError, ValueError) as error:
            raise JiraIntelligenceError(f"Jira Intelligence collection failed: {error}") from error
        if not isinstance(payload, dict):
            raise JiraIntelligenceError("Jira Intelligence collection returned an invalid response.")
        try:
            return evidence_from_intelligence_envelope(payload)
        except ValueError as error:
            raise JiraIntelligenceError(str(error)) from error


def _read_response(request: Request) -> bytes:
    with urlopen(request, timeout=30) as response:  # noqa: S310 - loopback URL is validated above.
        return response.read()
