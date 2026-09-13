from __future__ import annotations

import json
from pathlib import Path

import pytest

from rca_orchestrator.evidence import CollectionEvidence, EvidencePackage
from rca_orchestrator.knowledge_base import KBPassage, KBSelection
from rca_orchestrator.model_runner import ModelInvocation, ModelRunnerError
from rca_orchestrator.workflow import RcaWorkflow


def test_copilot_run_persists_an_analyst_draft_and_fresh_evaluator_outcome(tmp_path: Path) -> None:
    model_runner = _FakeModelRunner(
        analyst_output={
            "hypotheses": [
                {
                    "title": "A runtime dependency is missing.",
                    "supporting_evidence": ["jira:observation:1", "runtime:concepts.md"],
                    "contradicting_evidence": [],
                    "unknowns": ["The deployed dependency manifest was not attached."],
                    "confidence": 0.62,
                }
            ],
            "most_likely_explanation": "The runtime dependency is absent from the deployment.",
            "unknowns": ["The deployment manifest is unavailable."],
            "recommended_actions": ["Compare the deployment manifest with the working environment."],
        },
        evaluator_output={
            "result": "needs_evidence",
            "citation_gaps": ["No deployment manifest citation is available."],
            "contradictions": [],
            "unknowns": ["The production manifest remains unavailable."],
            "rationale": "The hypothesis is plausible but requires the manifest.",
        },
    )
    workflow = RcaWorkflow(
        output_root=tmp_path,
        jira_intelligence_client=_FakeJiraIntelligence(),
        knowledge_base=_FakeKnowledgeBase(),
        model_runner=model_runner,
    )

    run = workflow.run("PC-123", "copilot")

    assert run.state == "completed"
    assert run.state_history == (
        "created",
        "collected",
        "evidence_ready",
        "kb_ready",
        "drafted",
        "evaluated",
        "awaiting_decision",
        "completed",
    )
    assert model_runner.calls == ["preflight", "analyst", "evaluator"]
    assert run.evaluation_result == "needs_evidence"
    assert run.analyst_draft is not None
    assert run.analyst_draft.hypotheses[0].supporting_evidence == (
        "jira:observation:1",
        "runtime:concepts.md",
    )
    assert run.evaluation is not None
    assert run.evaluation.citation_gaps == ("No deployment manifest citation is available.",)
    assert run.analyst_prompt == "analyst prompt"
    assert run.evaluator_prompt == "evaluator prompt"
    assert run.analyst_raw_output
    assert run.evaluator_raw_output
    report = run.report_path.read_text(encoding="utf-8")
    assert "Evaluation Result: needs_evidence." in report
    assert "## Hypotheses" in report
    assert "A runtime dependency is missing." in report
    assert "## Most likely explanation" in report
    assert "## Evaluation evidence gaps and contradictions" in report
    assert "No deployment manifest citation is available." in report
    assert "- KB version applicability: unverified" in report
    record = json.loads((tmp_path / run.run_id / "run.json").read_text(encoding="utf-8"))
    assert record["evaluation"]["result"] == "needs_evidence"
    assert record["model_invocations"]["analyst"]["model"] == "copilot-cli"
    assert record["model_invocations"]["evaluator"]["prompt"] == "evaluator prompt"


def test_copilot_preflight_failure_is_actionable_and_does_not_collect_jira_evidence(tmp_path: Path) -> None:
    jira = _FakeJiraIntelligence()
    workflow = RcaWorkflow(
        output_root=tmp_path,
        jira_intelligence_client=jira,
        knowledge_base=_FakeKnowledgeBase(),
        model_runner=_PreflightFailureRunner(),
    )

    with pytest.raises(ModelRunnerError, match="Run `copilot login`"):
        workflow.run("PC-123", "copilot")

    assert jira.collection_requests == []
    assert list(tmp_path.iterdir()) == []


def test_malformed_copilot_analysis_blocks_the_run_without_fixture_fallback(tmp_path: Path) -> None:
    model_runner = _FakeModelRunner(
        analyst_output={
            "hypotheses": [
                {
                    "title": "Unsupported conclusion",
                    "supporting_evidence": ["not-a-citation"],
                    "contradicting_evidence": [],
                    "unknowns": [],
                    "confidence": 0.8,
                }
            ],
            "most_likely_explanation": "Unsupported conclusion",
            "unknowns": [],
            "recommended_actions": [],
        },
        evaluator_output={
            "result": "passed",
            "citation_gaps": [],
            "contradictions": [],
            "unknowns": [],
            "rationale": "unused",
        },
    )
    run = RcaWorkflow(
        output_root=tmp_path,
        jira_intelligence_client=_FakeJiraIntelligence(),
        knowledge_base=_FakeKnowledgeBase(),
        model_runner=model_runner,
    ).run("PC-123", "copilot")

    assert run.state == "blocked"
    assert "unknown evidence reference: not-a-citation" in run.blocked_reason
    assert run.evaluation_result is None
    assert run.model_prompt == ""
    assert run.analyst_prompt is None
    assert not run.report_path.exists()
    assert model_runner.calls == ["preflight", "analyst"]


def test_malformed_evaluator_output_persists_a_resumable_blocked_run(tmp_path: Path) -> None:
    model_runner = _FakeModelRunner(
        analyst_output=_valid_analyst_output(),
        evaluator_output={
            "result": "passed", "citation_gaps": ["Missing source"], "contradictions": [],
            "unknowns": [], "rationale": "This cannot pass.",
        },
    )
    workflow = RcaWorkflow(output_root=tmp_path, jira_intelligence_client=_FakeJiraIntelligence(),
                           knowledge_base=_FakeKnowledgeBase(), model_runner=model_runner)

    run = workflow.run("PC-123", "copilot")

    assert run.state == "blocked"
    assert run.state_history[-2:] == ("drafted", "blocked")
    assert workflow.get(run.run_id) == run


def test_resume_preflights_a_copilot_run_before_another_model_invocation(tmp_path: Path) -> None:
    completed_runner = _FakeModelRunner(analyst_output=_valid_analyst_output(), evaluator_output=_valid_evaluator_output())
    original = RcaWorkflow(output_root=tmp_path, jira_intelligence_client=_FakeJiraIntelligence(),
                            knowledge_base=_FakeKnowledgeBase(), model_runner=completed_runner).run("PC-123", "copilot")
    record_path = tmp_path / original.run_id / "run.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record.update({"state": "kb_ready", "state_history": ["created", "collected", "evidence_ready", "kb_ready"],
                   "analyst_draft": None, "evaluation": None, "evaluation_result": None,
                   "model_invocations": {"analyst": None, "evaluator": None}})
    record_path.write_text(json.dumps(record), encoding="utf-8")
    workflow = RcaWorkflow(output_root=tmp_path, jira_intelligence_client=_FakeJiraIntelligence(),
                           knowledge_base=_FakeKnowledgeBase(), model_runner=_PreflightFailureRunner())

    with pytest.raises(ModelRunnerError, match="Run `copilot login`"):
        workflow.resume(original.run_id)

    assert workflow.get(original.run_id).state == "kb_ready"


def test_resuming_a_completed_copilot_run_does_not_repeat_collection_or_model_work(tmp_path: Path) -> None:
    jira = _FakeJiraIntelligence()
    model_runner = _FakeModelRunner(
        analyst_output=_valid_analyst_output(), evaluator_output=_valid_evaluator_output()
    )
    workflow = RcaWorkflow(
        output_root=tmp_path,
        jira_intelligence_client=jira,
        knowledge_base=_FakeKnowledgeBase(),
        model_runner=model_runner,
    )
    original = workflow.run("PC-123", "copilot")

    resumed = workflow.resume(original.run_id)

    assert resumed == original
    assert jira.collection_requests == [("PC-123", original.run_id)]
    assert model_runner.calls == ["preflight", "analyst", "evaluator"]


class _FakeJiraIntelligence:
    def __init__(self) -> None:
        self.collection_requests: list[tuple[str, str]] = []

    def collect_or_reuse(self, issue_key: str, rca_run_id: str) -> CollectionEvidence:
        self.collection_requests.append((issue_key, rca_run_id))
        return CollectionEvidence(
            collection_run_id="collection-123",
            evidence=EvidencePackage(
                collection_run_id="collection-123",
                confirmed_observations=("Summary: Binding fails at startup",),
                reported_claims=("Description: Runtime reports a missing dependency",),
                missing_evidence=("Deployment manifest was not attached.",),
                components=("runtime",),
                labels=("binding",),
            ),
        )

    def list_artifacts(self, issue_key: str, collection_run_id: str) -> tuple[object, ...]:
        return ()

    def read_artifact(
        self, issue_key: str, collection_run_id: str, reference: str, max_bytes: int
    ) -> bytes:
        raise AssertionError("No attachments should be read in this test")


class _FakeKnowledgeBase:
    def retrieve(self, evidence: EvidencePackage, product_version: str | None) -> KBSelection:
        return KBSelection(
            kb_revision="pc-50.16.0-p1",
            version_applicability="unverified",
            domain_ids=("runtime",),
            passages=(
                KBPassage(
                    citation_id="runtime:concepts.md",
                    domain_id="runtime",
                    relative_path="domains/runtime/concepts.md",
                    text="A missing runtime dependency prevents startup.",
                ),
            ),
        )


class _FakeModelRunner:
    def __init__(self, *, analyst_output: dict[str, object], evaluator_output: dict[str, object]) -> None:
        self._analyst_output = analyst_output
        self._evaluator_output = evaluator_output
        self.calls: list[str] = []

    def preflight(self) -> None:
        self.calls.append("preflight")

    def run_analyst(self, evidence: EvidencePackage, passages: tuple[KBPassage, ...], product_version: str | None,
                    kb_version_applicability: str) -> ModelInvocation:
        self.calls.append("analyst")
        return ModelInvocation(
            model="copilot-cli",
            prompt="analyst prompt",
            raw_output=json.dumps(self._analyst_output),
        )

    def run_evaluator(self, draft: object, evidence: EvidencePackage, passages: tuple[KBPassage, ...],
                      product_version: str | None, kb_version_applicability: str) -> ModelInvocation:
        self.calls.append("evaluator")
        return ModelInvocation(
            model="copilot-cli",
            prompt="evaluator prompt",
            raw_output=json.dumps(self._evaluator_output),
        )


class _PreflightFailureRunner:
    def preflight(self) -> None:
        raise ModelRunnerError("Copilot CLI is not authenticated. Run `copilot login` and retry.")


def _valid_analyst_output() -> dict[str, object]:
    return {
        "hypotheses": [{"title": "Runtime dependency missing", "supporting_evidence": ["jira:observation:1"],
                          "contradicting_evidence": [], "unknowns": [], "confidence": 0.6}],
        "most_likely_explanation": "Dependency absent", "unknowns": [], "recommended_actions": [],
    }


def _valid_evaluator_output() -> dict[str, object]:
    return {"result": "needs_evidence", "citation_gaps": [], "contradictions": [], "unknowns": [], "rationale": "Need more evidence."}
