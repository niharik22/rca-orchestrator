from __future__ import annotations

from pathlib import Path
import json

import pytest

from rca_orchestrator.evidence import CollectionEvidence, EvidencePackage
from rca_orchestrator.jira_intelligence import JiraIntelligenceError, JiraIntelligenceHttpClient
from rca_orchestrator.workflow import FixtureProvenance, RcaWorkflow


def test_declined_writeback_persists_the_decision_without_a_jira_mutation(tmp_path: Path) -> None:
    jira = _WritebackJiraIntelligence()
    workflow = RcaWorkflow(
        output_root=tmp_path,
        jira_intelligence_client=jira,
        fixture_runner=_FixtureRunner("needs_evidence"),
    )
    run = workflow.run("PC-123", "fixture")

    decided = workflow.confirm_writeback(run.run_id, approved=False)

    assert decided.writeback_decision == "declined"
    assert decided.writeback_event_ids == ()
    assert jira.comments == []
    assert jira.uploads == []


def test_confirmed_passed_writeback_posts_a_comment_and_only_the_markdown_report(tmp_path: Path) -> None:
    jira = _WritebackJiraIntelligence()
    analysis_root = tmp_path / "jira-intelligence-workspace"
    workflow = RcaWorkflow(
        output_root=tmp_path / "outputs",
        analysis_root=analysis_root,
        jira_intelligence_client=jira,
        fixture_runner=_FixtureRunner("passed"),
    )
    run = workflow.run("PC-123", "fixture")

    decided = workflow.confirm_writeback(run.run_id, approved=True)

    assert decided.writeback_decision == "approved"
    assert decided.writeback_event_ids == ("comment-event", "attachment-event")
    assert jira.comments == [
        {
            "issue_key": "PC-123",
            "collection_run_id": "fixture-collection-PC-123",
            "orchestration_run_id": run.run_id,
            "approval_reference": f"terminal-approval-{run.run_id}",
            "idempotency_key": f"rca-comment-{run.run_id}",
            "plain_text": "RCA Orchestrator status: Evaluation Result is passed. The evidence-cited RCA Report is attached.",
        }
    ]
    assert jira.uploads == [
        {
            "issue_key": "PC-123",
            "collection_run_id": "fixture-collection-PC-123",
            "orchestration_run_id": run.run_id,
            "approval_reference": f"terminal-approval-{run.run_id}",
            "idempotency_key": f"rca-attachment-{run.run_id}",
        }
    ]
    analysis_report = (
        analysis_root / "PC-123" / "runs" / "fixture-collection-PC-123" / "analysis" / "rca-report.md"
    )
    assert analysis_report.read_text(encoding="utf-8") == run.report_path.read_text(encoding="utf-8")
    assert workflow.get(run.run_id).writeback_event_ids == ("comment-event", "attachment-event")

    declined_after_approval = workflow.confirm_writeback(run.run_id, approved=False)

    assert declined_after_approval.writeback_decision == "approved"


def test_confirmed_non_passing_writeback_posts_only_a_clearly_labelled_status_comment(tmp_path: Path) -> None:
    jira = _WritebackJiraIntelligence()
    workflow = RcaWorkflow(
        output_root=tmp_path,
        jira_intelligence_client=jira,
        fixture_runner=_FixtureRunner("escalated"),
    )
    run = workflow.run("PC-123", "fixture")

    workflow.confirm_writeback(run.run_id, approved=True)

    assert jira.comments[0]["plain_text"] == (
        "RCA Orchestrator status: Evaluation Result is escalated. "
        "No RCA Report is attached; this result requires follow-up before a root-cause conclusion."
    )
    assert jira.uploads == []


def test_passed_writeback_rejects_an_analysis_directory_with_an_unrelated_artifact(tmp_path: Path) -> None:
    jira = _WritebackJiraIntelligence()
    analysis_root = tmp_path / "jira-intelligence-workspace"
    analysis_directory = analysis_root / "PC-123" / "runs" / "fixture-collection-PC-123" / "analysis"
    analysis_directory.mkdir(parents=True)
    (analysis_directory / "unrelated.txt").write_text("do not upload", encoding="utf-8")
    workflow = RcaWorkflow(
        output_root=tmp_path / "outputs",
        analysis_root=analysis_root,
        jira_intelligence_client=jira,
        fixture_runner=_FixtureRunner("passed"),
    )
    run = workflow.run("PC-123", "fixture")

    with pytest.raises(JiraIntelligenceError, match="outside this RCA Report"):
        workflow.confirm_writeback(run.run_id, approved=True)

    assert jira.comments == []
    assert jira.uploads == []


def test_jira_intelligence_client_uses_distinct_idempotent_comment_and_attachment_requests() -> None:
    requests: list[object] = []
    client = JiraIntelligenceHttpClient(
        "http://127.0.0.1:8001",
        request=lambda request: _writeback_response(request, requests),
    )

    comment_events = client.post_status_comment(
        "pc-123", "RCA status", collection_run_id="collection-123", orchestration_run_id="rca-123",
        approval_reference="terminal-approval-rca-123", idempotency_key="rca-comment-rca-123",
    )
    attachment_events = client.upload_analysis_report(
        "PC-123", collection_run_id="collection-123", orchestration_run_id="rca-123",
        approval_reference="terminal-approval-rca-123", idempotency_key="rca-attachment-rca-123",
    )

    assert comment_events == ("comment-event",)
    assert attachment_events == ("attachment-event",)
    assert [request.full_url for request in requests] == [
        "http://127.0.0.1:8001/v1/issues/PC-123/comments",
        "http://127.0.0.1:8001/v1/issues/PC-123/attachments",
    ]
    assert [request.get_header("Idempotency-key") for request in requests] == [
        "rca-comment-rca-123", "rca-attachment-rca-123"
    ]


def _writeback_response(request: object, requests: list[object]) -> bytes:
    requests.append(request)
    if request.full_url.endswith("/comments"):
        assert json.loads(request.data.decode("utf-8"))["plain_text"] == "RCA status"
        return b'{"id": "comment-event"}'
    assert json.loads(request.data.decode("utf-8"))["collection_run_id"] == "collection-123"
    return b'{"writeback_events": [{"id": "attachment-event"}]}'


class _FixtureRunner:
    def __init__(self, result: str) -> None:
        self._result = result

    def provenance_for(self, _issue_key: str) -> FixtureProvenance:
        return FixtureProvenance(self._result, "fixture-v1", ())


class _WritebackJiraIntelligence:
    def __init__(self) -> None:
        self.comments: list[dict[str, str]] = []
        self.uploads: list[dict[str, str]] = []

    def collect_or_reuse(self, issue_key: str, _rca_run_id: str) -> CollectionEvidence:
        collection_run_id = f"fixture-collection-{issue_key}"
        return CollectionEvidence(
            collection_run_id=collection_run_id,
            evidence=EvidencePackage(
                collection_run_id=collection_run_id,
                confirmed_observations=("The test issue has been collected.",),
                reported_claims=(),
                missing_evidence=(),
                components=(),
                labels=(),
            ),
        )

    def list_artifacts(self, _issue_key: str, _collection_run_id: str) -> tuple[object, ...]:
        return ()

    def read_artifact(
        self, _issue_key: str, _collection_run_id: str, _reference: str, _max_bytes: int
    ) -> bytes:
        raise AssertionError("This test has no Jira attachments.")

    def post_status_comment(self, issue_key: str, plain_text: str, *, collection_run_id: str,
                            orchestration_run_id: str, approval_reference: str, idempotency_key: str) -> tuple[str, ...]:
        self.comments.append({
            "issue_key": issue_key, "collection_run_id": collection_run_id,
            "orchestration_run_id": orchestration_run_id, "approval_reference": approval_reference,
            "idempotency_key": idempotency_key, "plain_text": plain_text,
        })
        return ("comment-event",)

    def upload_analysis_report(self, issue_key: str, *, collection_run_id: str,
                               orchestration_run_id: str, approval_reference: str, idempotency_key: str) -> tuple[str, ...]:
        self.uploads.append({
            "issue_key": issue_key, "collection_run_id": collection_run_id,
            "orchestration_run_id": orchestration_run_id, "approval_reference": approval_reference,
            "idempotency_key": idempotency_key,
        })
        return ("attachment-event",)
