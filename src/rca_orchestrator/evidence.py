"""Bounded Jira evidence models used by the RCA workflow."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class EvidencePackage:
    """The Jira evidence that may be used for RCA analysis."""

    collection_run_id: str
    confirmed_observations: tuple[str, ...]
    reported_claims: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    components: tuple[str, ...]
    labels: tuple[str, ...]
    attachments: tuple[AttachmentEvidence, ...] = ()

    @property
    def retrieval_terms(self) -> tuple[str, ...]:
        text = " ".join(
            (*self.confirmed_observations, *self.reported_claims, *self.components, *self.labels)
        )
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", text.lower())
        errors = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*(?:Exception|Error)\b", text)
        return tuple(dict.fromkeys((*words, *(error.lower() for error in errors))))


@dataclass(frozen=True)
class CollectionEvidence:
    """A Collection Run and its normalized Evidence Package."""

    collection_run_id: str
    evidence: EvidencePackage
    attachment_metadata: tuple[AttachmentMetadata, ...] = ()


@dataclass(frozen=True)
class AttachmentMetadata:
    """Jira's immutable attachment metadata from a Collection Run."""

    attachment_id: str
    filename: str
    mime_type: str | None
    size: int


@dataclass(frozen=True)
class AttachmentEvidence:
    """One attachment's bounded inclusion or explicit exclusion from RCA evidence."""

    reference: str | None
    filename: str
    mime_type: str | None
    size: int
    status: str
    reason: str | None = None
    text: str | None = None
    truncated: bool = False


def evidence_from_intelligence_envelope(payload: dict[str, Any]) -> CollectionEvidence:
    """Create a bounded Evidence Package from a Jira Intelligence response."""
    collection_run = _required_mapping(payload, "collection_run")
    normalized_issue = _required_mapping(payload, "normalized_issue")
    collection_run_id = _required_string(collection_run, "id")
    components = _string_tuple(normalized_issue.get("components"))
    labels = _string_tuple(normalized_issue.get("labels"))
    attachment_metadata = _attachment_metadata(normalized_issue.get("attachments"))

    observations = _present(
        (
            _prefixed("Summary", normalized_issue.get("summary")),
            _prefixed("Status", normalized_issue.get("status")),
            *(_prefixed("Component", component) for component in components),
            *(_prefixed("Label", label) for label in labels),
        )
    )
    description = normalized_issue.get("description")
    description_text = description.get("text") if isinstance(description, dict) else None
    claims = _present((_prefixed("Description", description_text),))
    missing: list[str] = []
    if not claims:
        missing.insert(0, "No Jira description was available in the Collection Run.")
    for error in payload.get("errors", []):
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            missing.append(f"Jira Intelligence reported: {error['message']}")

    return CollectionEvidence(
        collection_run_id=collection_run_id,
        evidence=EvidencePackage(
            collection_run_id=collection_run_id,
            confirmed_observations=observations,
            reported_claims=claims,
            missing_evidence=tuple(missing),
            components=components,
            labels=labels,
        ),
        attachment_metadata=attachment_metadata,
    )


def _required_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Jira Intelligence response has no {key} object.")
    return value


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Jira Intelligence response has no {key}.")
    return value


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _prefixed(name: str, value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return f"{name}: {value.strip()}"


def _present(values: tuple[str | None, ...]) -> tuple[str, ...]:
    return tuple(value for value in values if value is not None)


def _attachment_metadata(value: Any) -> tuple[AttachmentMetadata, ...]:
    if not isinstance(value, list):
        return ()
    metadata: list[AttachmentMetadata] = []
    for attachment in value:
        if not isinstance(attachment, dict):
            continue
        attachment_id = attachment.get("id")
        filename = attachment.get("filename")
        size = attachment.get("size")
        mime_type = attachment.get("mime_type")
        if (
            not isinstance(attachment_id, str)
            or not attachment_id
            or not isinstance(filename, str)
            or not filename
            or not isinstance(size, int)
            or size < 0
        ):
            continue
        metadata.append(
            AttachmentMetadata(
                attachment_id=attachment_id,
                filename=filename,
                mime_type=mime_type if isinstance(mime_type, str) and mime_type else None,
                size=size,
            )
        )
    return tuple(metadata)
