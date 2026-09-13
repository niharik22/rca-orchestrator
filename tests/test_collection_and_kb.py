from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import pytest

from rca_orchestrator.evidence import CollectionEvidence, EvidencePackage
from rca_orchestrator.jira_intelligence import JiraIntelligenceError, JiraIntelligenceHttpClient
from rca_orchestrator.knowledge_base import KBPassage, KBSelection, KnowledgeBaseError, ManifestKnowledgeBase
from rca_orchestrator.workflow import RcaWorkflow


def test_fixture_run_records_jira_evidence_kb_citations_and_unverified_product_version(
    tmp_path: Path,
) -> None:
    jira = _FakeJiraIntelligence()
    kb = _FakeKnowledgeBase()
    workflow = RcaWorkflow(
        output_root=tmp_path,
        jira_intelligence_client=jira,
        knowledge_base=kb,
    )

    run = workflow.run(issue_key="PC-123", model="fixture")

    assert run.collection_run_id == "collection-123"
    assert run.confirmed_observations == ("Summary: Policy binding fails", "Component: runtime")
    assert run.reported_claims == ("Description: NullPointerException while binding",)
    assert run.missing_evidence == ("No Jira attachments were collected in Ticket 2.",)
    assert run.kb_passage_ids == ("runtime-transactions:concepts.md",)
    assert run.kb_domains == ("runtime-transactions",)
    assert run.product_version is None
    assert run.kb_version_applicability == "unverified"
    assert jira.requests == [("PC-123", run.run_id)]
    assert kb.product_versions == [None]
    assert "## Jira observations\n\n- Summary: Policy binding fails\n- Component: runtime" in run.report_path.read_text(
        encoding="utf-8"
    )
    assert "## Reported but unverified claims\n\n- Description: NullPointerException while binding" in run.report_path.read_text(
        encoding="utf-8"
    )
    assert "- KB version applicability: unverified" in run.report_path.read_text(encoding="utf-8")


def test_resume_reuses_persisted_collection_and_kb_selection(tmp_path: Path) -> None:
    jira = _FakeJiraIntelligence()
    kb = _FakeKnowledgeBase()
    workflow = RcaWorkflow(
        output_root=tmp_path,
        jira_intelligence_client=jira,
        knowledge_base=kb,
    )
    original = workflow.run(issue_key="PC-123", model="fixture")

    resumed = workflow.resume(original.run_id)

    assert resumed == original
    assert jira.requests == [("PC-123", original.run_id)]
    assert kb.product_versions == [None]


def test_product_version_is_persisted_and_passed_to_kb_retrieval(tmp_path: Path) -> None:
    kb = _FakeKnowledgeBase()
    run = RcaWorkflow(
        output_root=tmp_path,
        jira_intelligence_client=_FakeJiraIntelligence(),
        knowledge_base=kb,
    ).run(issue_key="PC-123", model="fixture", product_version="50.16.0 P1")

    assert run.product_version == "50.16.0 P1"
    assert run.kb_version_applicability == "not_verified"
    assert kb.product_versions == ["50.16.0 P1"]
    assert "- Product Version: 50.16.0 P1" in run.report_path.read_text(encoding="utf-8")


def test_jira_intelligence_failure_persists_a_blocked_run_without_a_report(tmp_path: Path) -> None:
    workflow = RcaWorkflow(
        output_root=tmp_path,
        jira_intelligence_client=_FailingJiraIntelligence(),
        knowledge_base=_FakeKnowledgeBase(),
    )

    run = workflow.run(issue_key="PC-123", model="fixture")

    assert run.state == "blocked"
    assert run.blocked_reason == "Jira Intelligence collection is unavailable."
    assert not run.report_path.exists()


def test_manifest_kb_selects_bounded_cited_passages_and_marks_absent_product_version(
    tmp_path: Path,
) -> None:
    _write_kb(
        tmp_path,
        """
kb_revision: pc-50.16.0-p1
domains:
  - id: runtime-transactions
    path: domains/runtime-transactions
    keywords: [runtime, binding, NullPointerException]
  - id: data-entities
    path: domains/data-entities
    keywords: [entity, database]
  - id: integrations-messaging
    path: domains/integrations-messaging
    keywords: [api, message]
  - id: testing-quality
    path: domains/testing-quality
    keywords: [test]
""",
    )
    _write_domain(tmp_path, "runtime-transactions", "Runtime diagnosis\n\nNullPointerException on binding.")
    _write_domain(tmp_path, "data-entities", "Data entity guidance.")
    _write_domain(tmp_path, "integrations-messaging", "Integration guidance.")
    _write_domain(tmp_path, "testing-quality", "Testing guidance.")

    selection = ManifestKnowledgeBase(tmp_path).retrieve(
        EvidencePackage(
            collection_run_id="collection-123",
            confirmed_observations=("Summary: Policy binding fails",),
            reported_claims=("Description: NullPointerException",),
            missing_evidence=(),
            components=("runtime",),
            labels=("binding",),
        ),
        product_version=None,
    )

    assert selection.kb_revision == "pc-50.16.0-p1"
    assert selection.version_applicability == "unverified"
    assert selection.domain_ids == ("runtime-transactions",)
    assert selection.passages == (
        KBPassage(
            citation_id="runtime-transactions:concepts.md",
            domain_id="runtime-transactions",
            relative_path="domains/runtime-transactions/concepts.md",
            text="Runtime diagnosis\n\nNullPointerException on binding.",
        ),
    )


def test_manifest_kb_rejects_a_domain_path_outside_the_configured_root(tmp_path: Path) -> None:
    _write_kb(
        tmp_path,
        """
kb_revision: pc-50.16.0-p1
domains:
  - id: runtime-transactions
    path: ../outside
    keywords: [runtime]
""",
    )

    with pytest.raises(KnowledgeBaseError, match="outside the configured KB root"):
        ManifestKnowledgeBase(tmp_path).retrieve(
            EvidencePackage(
                collection_run_id="collection-123",
                confirmed_observations=("Summary: runtime",),
                reported_claims=(),
                missing_evidence=(),
                components=("runtime",),
                labels=(),
            ),
            product_version="50.16.0 P1",
        )


def test_jira_intelligence_adapter_uses_only_the_collection_endpoint() -> None:
    requests: list[object] = []

    def respond(request: object) -> bytes:
        requests.append(request)
        return json.dumps(
            {
                "collection_run": {"id": "collection-123"},
                "normalized_issue": {
                    "summary": "Policy binding fails",
                    "components": ["runtime"],
                    "labels": ["binding"],
                    "description": {"text": "NullPointerException while binding"},
                },
            }
        ).encode("utf-8")

    collected = JiraIntelligenceHttpClient("http://127.0.0.1:8001", request=respond).collect_or_reuse(
        "pc-123", "rca-run-123"
    )

    request = requests[0]
    assert request.full_url == "http://127.0.0.1:8001/v1/issues/PC-123/intelligence"
    assert request.get_method() == "POST"
    assert request.get_header("Idempotency-key") == "rca-collection-rca-run-123"
    assert json.loads(request.data.decode("utf-8")) == {
        "download_attachments": False,
        "orchestration_run_id": "rca-run-123",
    }
    assert collected.collection_run_id == "collection-123"
    assert collected.evidence.reported_claims == ("Description: NullPointerException while binding",)


@dataclass
class _FakeJiraIntelligence:
    requests: list[tuple[str, str]]

    def __init__(self) -> None:
        self.requests = []

    def collect_or_reuse(self, issue_key: str, rca_run_id: str) -> CollectionEvidence:
        self.requests.append((issue_key, rca_run_id))
        return CollectionEvidence(
            collection_run_id="collection-123",
            evidence=EvidencePackage(
                collection_run_id="collection-123",
                confirmed_observations=("Summary: Policy binding fails", "Component: runtime"),
                reported_claims=("Description: NullPointerException while binding",),
                missing_evidence=("No Jira attachments were collected in Ticket 2.",),
                components=("runtime",),
                labels=("binding",),
            ),
        )


@dataclass
class _FakeKnowledgeBase:
    product_versions: list[str | None]

    def __init__(self) -> None:
        self.product_versions = []

    def retrieve(self, evidence: EvidencePackage, product_version: str | None) -> KBSelection:
        self.product_versions.append(product_version)
        return KBSelection(
            kb_revision="pc-50.16.0-p1",
            version_applicability="unverified" if product_version is None else "not_verified",
            domain_ids=("runtime-transactions",),
            passages=(
                KBPassage(
                    citation_id="runtime-transactions:concepts.md",
                    domain_id="runtime-transactions",
                    relative_path="domains/runtime-transactions/concepts.md",
                    text="Runtime diagnosis",
                ),
            ),
        )


class _FailingJiraIntelligence:
    def collect_or_reuse(self, issue_key: str, rca_run_id: str) -> CollectionEvidence:
        raise JiraIntelligenceError("Jira Intelligence collection is unavailable.")


def _write_kb(root: Path, manifest: str) -> None:
    (root / "manifest.yaml").write_text(manifest.strip() + "\n", encoding="utf-8")


def _write_domain(root: Path, domain_id: str, content: str) -> None:
    domain_directory = root / "domains" / domain_id
    domain_directory.mkdir(parents=True)
    (domain_directory / "index.yaml").write_text("passages: [concepts.md]\n", encoding="utf-8")
    (domain_directory / "concepts.md").write_text(content, encoding="utf-8")
