"""The RCA-side adapter for Jira Intelligence's loopback collection API."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from .evidence import CollectionEvidence, evidence_from_intelligence_envelope


class JiraIntelligenceError(RuntimeError):
    """Raised when Jira Intelligence cannot provide required RCA evidence."""


@dataclass(frozen=True)
class ArtifactDescriptor:
    """An opaque artifact reference listed by Jira Intelligence."""

    reference: str
    kind: str
    filename: str
    mime_type: str | None
    size: int


class JiraIntelligenceClient(Protocol):
    def collect_or_reuse(self, issue_key: str, rca_run_id: str) -> CollectionEvidence: ...

    def list_artifacts(self, issue_key: str, collection_run_id: str) -> tuple[ArtifactDescriptor, ...]: ...

    def read_artifact(
        self, issue_key: str, collection_run_id: str, reference: str, max_bytes: int
    ) -> bytes: ...

    def post_status_comment(
        self,
        issue_key: str,
        plain_text: str,
        *,
        collection_run_id: str,
        orchestration_run_id: str,
        approval_reference: str,
        idempotency_key: str,
    ) -> tuple[str, ...]: ...

    def upload_analysis_report(
        self,
        issue_key: str,
        *,
        collection_run_id: str,
        orchestration_run_id: str,
        approval_reference: str,
        idempotency_key: str,
    ) -> tuple[str, ...]: ...


class JiraIntelligenceHttpClient:
    """Uses Jira Intelligence's loopback evidence and controlled-writeback API."""

    def __init__(
        self,
        base_url: str,
        request: Callable[[Request], bytes] | None = None,
        limited_request: Callable[[Request, int], bytes] | None = None,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1":
            raise ValueError("Jira Intelligence URL must use http://127.0.0.1.")
        self._base_url = base_url.rstrip("/")
        self._request = request or _read_response
        self._limited_request = limited_request or _read_response_limited

    def collect_or_reuse(self, issue_key: str, rca_run_id: str) -> CollectionEvidence:
        encoded_issue_key = quote(issue_key.upper(), safe="")
        request = Request(
            f"{self._base_url}/v1/issues/{encoded_issue_key}/intelligence",
            data=json.dumps(
                {"download_attachments": True, "orchestration_run_id": rca_run_id}
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

    def list_artifacts(self, issue_key: str, collection_run_id: str) -> tuple[ArtifactDescriptor, ...]:
        payload = self._json_response(
            f"/v1/issues/{quote(issue_key.upper(), safe='')}/intelligence/"
            f"{quote(collection_run_id, safe='')}/artifacts"
        )
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            raise JiraIntelligenceError("Jira Intelligence artifact list returned an invalid response.")
        descriptors: list[ArtifactDescriptor] = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise JiraIntelligenceError("Jira Intelligence artifact list returned invalid metadata.")
            reference = artifact.get("reference")
            kind = artifact.get("kind")
            filename = artifact.get("filename")
            size = artifact.get("size")
            mime_type = artifact.get("mime_type")
            if (
                not isinstance(reference, str)
                or not reference
                or not isinstance(kind, str)
                or not kind
                or not isinstance(filename, str)
                or not filename
                or not isinstance(size, int)
                or size < 0
                or mime_type is not None
                and not isinstance(mime_type, str)
            ):
                raise JiraIntelligenceError("Jira Intelligence artifact list returned invalid metadata.")
            descriptors.append(ArtifactDescriptor(reference, kind, filename, mime_type, size))
        return tuple(descriptors)

    def read_artifact(
        self, issue_key: str, collection_run_id: str, reference: str, max_bytes: int
    ) -> bytes:
        if max_bytes < 0:
            raise ValueError("max_bytes must not be negative")
        request = Request(
            f"{self._base_url}/v1/issues/{quote(issue_key.upper(), safe='')}/intelligence/"
            f"{quote(collection_run_id, safe='')}/artifacts/{quote(reference, safe='')}",
            method="GET",
        )
        try:
            response = self._limited_request(request, max_bytes)
        except (HTTPError, URLError, OSError) as error:
            raise JiraIntelligenceError(f"Jira Intelligence artifact retrieval failed: {error}") from error
        if not isinstance(response, bytes):
            raise JiraIntelligenceError("Jira Intelligence artifact retrieval returned invalid content.")
        return response

    def post_status_comment(
        self,
        issue_key: str,
        plain_text: str,
        *,
        collection_run_id: str,
        orchestration_run_id: str,
        approval_reference: str,
        idempotency_key: str,
    ) -> tuple[str, ...]:
        payload = self._post_json(
            issue_key,
            "comments",
            {
                "plain_text": plain_text,
                "collection_run_id": collection_run_id,
                "orchestration_run_id": orchestration_run_id,
                "approval_reference": approval_reference,
            },
            idempotency_key,
        )
        return _event_ids(payload, "Jira Intelligence comment writeback")

    def upload_analysis_report(
        self,
        issue_key: str,
        *,
        collection_run_id: str,
        orchestration_run_id: str,
        approval_reference: str,
        idempotency_key: str,
    ) -> tuple[str, ...]:
        payload = self._post_json(
            issue_key,
            "attachments",
            {
                "collection_run_id": collection_run_id,
                "orchestration_run_id": orchestration_run_id,
                "approval_reference": approval_reference,
            },
            idempotency_key,
        )
        return _event_ids(payload, "Jira Intelligence attachment writeback")

    def _json_response(self, path: str) -> dict[str, Any]:
        request = Request(f"{self._base_url}{path}", method="GET")
        try:
            response = self._request(request)
            payload = json.loads(response.decode("utf-8"))
        except (HTTPError, URLError, OSError, json.JSONDecodeError, ValueError) as error:
            raise JiraIntelligenceError(f"Jira Intelligence artifact list failed: {error}") from error
        if not isinstance(payload, dict):
            raise JiraIntelligenceError("Jira Intelligence artifact list returned an invalid response.")
        return payload

    def _post_json(
        self, issue_key: str, operation: str, payload: dict[str, str], idempotency_key: str
    ) -> dict[str, Any]:
        request = Request(
            f"{self._base_url}/v1/issues/{quote(issue_key.upper(), safe='')}/{operation}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Idempotency-Key": idempotency_key},
            method="POST",
        )
        try:
            response = self._request(request)
            response_payload = json.loads(response.decode("utf-8"))
        except (HTTPError, URLError, OSError, json.JSONDecodeError, ValueError) as error:
            raise JiraIntelligenceError(f"Jira Intelligence {operation} writeback failed: {error}") from error
        if not isinstance(response_payload, dict):
            raise JiraIntelligenceError(f"Jira Intelligence {operation} writeback returned an invalid response.")
        return response_payload


def _read_response(request: Request) -> bytes:
    with urlopen(request, timeout=30) as response:  # noqa: S310 - loopback URL is validated above.
        return response.read()


def _read_response_limited(request: Request, max_bytes: int) -> bytes:
    with urlopen(request, timeout=30) as response:  # noqa: S310 - loopback URL is validated above.
        return response.read(max_bytes + 1)


def _event_ids(payload: dict[str, Any], operation: str) -> tuple[str, ...]:
    events = payload.get("writeback_events", [payload])
    if not isinstance(events, list):
        raise JiraIntelligenceError(f"{operation} returned invalid events.")
    event_ids = tuple(event.get("id") for event in events if isinstance(event, dict))
    if len(event_ids) != len(events) or not all(isinstance(event_id, str) and event_id for event_id in event_ids):
        raise JiraIntelligenceError(f"{operation} returned an event without an identifier.")
    return event_ids
