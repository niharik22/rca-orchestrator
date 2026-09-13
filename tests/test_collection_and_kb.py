from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from rca_orchestrator.evidence import CollectionEvidence, EvidencePackage
from rca_orchestrator.jira_intelligence import JiraIntelligenceError, JiraIntelligenceHttpClient
from rca_orchestrator.knowledge_base import KBPassage, KBSelection, ManifestKnowledgeBase
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
    assert run.collection_run_id is None
    assert run.kb_revision is None
    assert not run.report_path.exists()


def test_manifest_kb_selects_bounded_cited_passages_and_marks_absent_product_version(tmp_path: Path) -> None:
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

    run = RcaWorkflow(
        output_root=tmp_path / "outputs",
        jira_intelligence_client=_FakeJiraIntelligence(),
        knowledge_base=ManifestKnowledgeBase(tmp_path),
    ).run(issue_key="PC-123", model="fixture")

    assert run.kb_revision == "pc-50.16.0-p1"
    assert run.kb_version_applicability == "unverified"
    assert run.kb_domains == ("runtime-transactions",)
    assert run.kb_passages == (
        KBPassage(
            citation_id="runtime-transactions:domains/runtime-transactions/concepts.md",
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

    run = RcaWorkflow(
        output_root=tmp_path / "outputs",
        jira_intelligence_client=_FakeJiraIntelligence(),
        knowledge_base=ManifestKnowledgeBase(tmp_path),
    ).run(issue_key="PC-123", model="fixture")

    assert run.state == "blocked"
    assert run.blocked_reason == "KB path is outside the configured KB root."


def test_manifest_kb_stops_reading_after_six_passages_and_keeps_citations_unique(tmp_path: Path) -> None:
    _write_kb(
        tmp_path,
        """
kb_revision: pc-50.16.0-p1
domains:
  - id: runtime-transactions
    path: domains/runtime-transactions
    keywords: [runtime]
""",
    )
    domain = tmp_path / "domains" / "runtime-transactions"
    domain.mkdir(parents=True)
    paths = [
        "guidance/concepts.md",
        "troubleshooting/concepts.md",
        "one.md",
        "two.md",
        "three.md",
        "four.md",
        "unreadable.md",
    ]
    (domain / "index.yaml").write_text(
        "passages:\n" + "\n".join(f"  - {path}" for path in paths) + "\n",
        encoding="utf-8",
    )
    for relative_path in paths[:6]:
        passage = domain / relative_path
        passage.parent.mkdir(parents=True, exist_ok=True)
        passage.write_text(f"Guidance from {relative_path}", encoding="utf-8")
    (domain / "unreadable.md").write_bytes(b"\xff")

    run = RcaWorkflow(
        output_root=tmp_path / "outputs",
        jira_intelligence_client=_FakeJiraIntelligence(),
        knowledge_base=ManifestKnowledgeBase(tmp_path),
    ).run("PC-123", "fixture")

    assert run.state == "completed"
    assert len(run.kb_passages) == 6
    assert len(set(run.kb_passage_ids)) == 6
    assert "runtime-transactions:domains/runtime-transactions/guidance/concepts.md" in run.kb_passage_ids
    assert "runtime-transactions:domains/runtime-transactions/troubleshooting/concepts.md" in run.kb_passage_ids


def test_unreadable_selected_kb_passage_persists_a_blocked_run(tmp_path: Path) -> None:
    _write_kb(
        tmp_path,
        """
kb_revision: pc-50.16.0-p1
domains:
  - id: runtime-transactions
    path: domains/runtime-transactions
    keywords: [runtime]
""",
    )
    domain = tmp_path / "domains" / "runtime-transactions"
    domain.mkdir(parents=True)
    (domain / "index.yaml").write_text("passages: [invalid.md]\n", encoding="utf-8")
    (domain / "invalid.md").write_bytes(b"\xff")

    run = RcaWorkflow(
        output_root=tmp_path / "outputs",
        jira_intelligence_client=_FakeJiraIntelligence(),
        knowledge_base=ManifestKnowledgeBase(tmp_path),
    ).run("PC-123", "fixture")

    assert run.state == "blocked"
    assert run.blocked_reason == "Unable to read KB passage: domains/runtime-transactions/invalid.md"
    assert not run.report_path.exists()


def test_empty_kb_passage_is_not_rendered_as_a_citation(tmp_path: Path) -> None:
    _write_kb(
        tmp_path,
        """
kb_revision: pc-50.16.0-p1
domains:
  - id: runtime-transactions
    path: domains/runtime-transactions
    keywords: [runtime]
""",
    )
    domain = tmp_path / "domains" / "runtime-transactions"
    domain.mkdir(parents=True)
    (domain / "index.yaml").write_text("passages: [empty.md]\n", encoding="utf-8")
    (domain / "empty.md").write_text("\n\n", encoding="utf-8")

    run = RcaWorkflow(
        output_root=tmp_path / "outputs",
        jira_intelligence_client=_FakeJiraIntelligence(),
        knowledge_base=ManifestKnowledgeBase(tmp_path),
    ).run("PC-123", "fixture")

    assert run.state == "completed"
    assert run.kb_passages == ()
    assert "## KB guidance and citations\n\n- None." in run.report_path.read_text(encoding="utf-8")


def test_workflow_uses_jira_intelligence_adapter_for_collection(tmp_path: Path) -> None:
    def respond(request: object) -> bytes:
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

    run = RcaWorkflow(
        output_root=tmp_path,
        jira_intelligence_client=JiraIntelligenceHttpClient("http://127.0.0.1:8001", request=respond),
        knowledge_base=_FakeKnowledgeBase(),
    ).run("PC-123", "fixture")

    assert run.collection_run_id == "collection-123"
    assert run.reported_claims == ("Description: NullPointerException while binding",)


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
