"""Manifest-first, bounded PolicyCenter KB retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

from .evidence import EvidencePackage


class KnowledgeBaseError(ValueError):
    """Raised when a configured KB is malformed or escapes its root."""


@dataclass(frozen=True)
class KBPassage:
    """A cited, bounded excerpt from one KB file."""

    citation_id: str
    domain_id: str
    relative_path: str
    text: str


@dataclass(frozen=True)
class KBSelection:
    """The deterministic KB guidance selected for an Evidence Package."""

    kb_revision: str
    version_applicability: str
    domain_ids: tuple[str, ...]
    passages: tuple[KBPassage, ...]


class KnowledgeBase(Protocol):
    def retrieve(self, evidence: EvidencePackage, product_version: str | None) -> KBSelection: ...


@dataclass(frozen=True)
class _Domain:
    domain_id: str
    relative_path: str
    keywords: tuple[str, ...]


class ManifestKnowledgeBase:
    """Retrieves at most three domains and six passages from one KB root."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def retrieve(self, evidence: EvidencePackage, product_version: str | None) -> KBSelection:
        manifest = self._load_yaml(self._root / "manifest.yaml")
        domains = self._domains(manifest)
        selected_domains = self._select_domains(domains, evidence.retrieval_terms)
        passages: list[KBPassage] = []
        for domain in selected_domains:
            remaining = 6 - len(passages)
            if remaining == 0:
                break
            passages.extend(self._passages_for_domain(domain, remaining))
        revision = _optional_string(manifest, "kb_revision") or _optional_string(manifest, "version") or "unknown"
        return KBSelection(
            kb_revision=revision,
            version_applicability="unverified" if product_version is None else "not_verified",
            domain_ids=tuple(domain.domain_id for domain in selected_domains),
            passages=tuple(passages),
        )

    def _domains(self, manifest: dict[str, Any]) -> tuple[_Domain, ...]:
        raw_domains = manifest.get("domains")
        if isinstance(raw_domains, dict):
            raw_domains = [dict(value, id=key) for key, value in raw_domains.items() if isinstance(value, dict)]
        if not isinstance(raw_domains, list):
            raise KnowledgeBaseError("KB manifest must define a domains list or mapping.")
        domains: list[_Domain] = []
        for raw_domain in raw_domains:
            if not isinstance(raw_domain, dict):
                raise KnowledgeBaseError("KB manifest domains must be objects.")
            domain_id = _required_string(raw_domain, "id")
            relative_path = _required_string(raw_domain, "path")
            self._contained_path(relative_path)
            keywords = raw_domain.get("keywords", [])
            if not isinstance(keywords, list) or not all(isinstance(keyword, str) for keyword in keywords):
                raise KnowledgeBaseError(f"KB domain {domain_id} has invalid keywords.")
            domains.append(_Domain(domain_id, relative_path, tuple(keyword.lower() for keyword in keywords)))
        return tuple(domains)

    def _select_domains(self, domains: tuple[_Domain, ...], terms: tuple[str, ...]) -> tuple[_Domain, ...]:
        term_set = set(terms)
        scored = [
            (
                sum(term in term_set for term in (*domain.keywords, *domain.domain_id.lower().split("-"))),
                domain,
            )
            for domain in domains
        ]
        return tuple(domain for score, domain in sorted(scored, key=lambda item: (-item[0], item[1].domain_id)) if score > 0)[:3]

    def _passages_for_domain(self, domain: _Domain, maximum: int) -> tuple[KBPassage, ...]:
        domain_root = self._contained_path(domain.relative_path)
        index = self._load_yaml(domain_root / "index.yaml")
        raw_passages = index.get("passages", ("concepts.md", "patterns.md"))
        if not isinstance(raw_passages, list):
            raise KnowledgeBaseError(f"KB domain {domain.domain_id} has invalid passages.")
        passages: list[KBPassage] = []
        for entry in raw_passages:
            relative_path = entry.get("path") if isinstance(entry, dict) else entry
            if not isinstance(relative_path, str):
                raise KnowledgeBaseError(f"KB domain {domain.domain_id} has invalid passage path.")
            path = self._contained_path(Path(domain.relative_path) / relative_path)
            if not path.is_file():
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as error:
                raise KnowledgeBaseError(f"Unable to read KB passage: {path.relative_to(self._root)}") from error
            if not source.strip():
                continue
            relative = path.relative_to(self._root).as_posix()
            passages.append(
                KBPassage(
                    citation_id=f"{domain.domain_id}:{relative}",
                    domain_id=domain.domain_id,
                    relative_path=relative,
                    text=source[:4000],
                )
            )
            if len(passages) == maximum:
                break
        return tuple(passages)

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        contained = self._contained_path(path.relative_to(self._root))
        if not contained.is_file():
            raise KnowledgeBaseError(f"Required KB file is missing: {contained.relative_to(self._root)}")
        try:
            parsed = yaml.safe_load(contained.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as error:
            raise KnowledgeBaseError(f"Unable to read KB file: {contained.relative_to(self._root)}") from error
        except yaml.YAMLError as error:
            raise KnowledgeBaseError(f"Invalid YAML in {contained.relative_to(self._root)}") from error
        if not isinstance(parsed, dict):
            raise KnowledgeBaseError(f"KB file must contain a mapping: {contained.relative_to(self._root)}")
        return parsed

    def _contained_path(self, relative_path: str | Path) -> Path:
        try:
            candidate = (self._root / relative_path).resolve()
        except OSError as error:
            raise KnowledgeBaseError("Unable to resolve a KB path.") from error
        try:
            candidate.relative_to(self._root)
        except ValueError as error:
            raise KnowledgeBaseError("KB path is outside the configured KB root.") from error
        return candidate


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeBaseError(f"KB manifest has no {key}.")
    return value.strip()


def _optional_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None
