from pathlib import Path

import pytest

from rca_orchestrator.workflow import RcaWorkflow, WorkflowTransitionError


def test_fixture_run_persists_completed_run_and_markdown_report(tmp_path: Path) -> None:
    workflow = RcaWorkflow(output_root=tmp_path)

    run = workflow.run(issue_key="PC-123", model="fixture")

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
    assert run.issue_key == "PC-123"
    assert run.model == "fixture"
    assert run.writeback_decision == "not_requested"
    assert run.report_path == tmp_path / run.run_id / "rca-report.md"
    assert run.report_path.read_text(encoding="utf-8") == (
        "# RCA Report: PC-123\n\n"
        "## Outcome and confidence\n\n"
        "Fixture analysis completed with demo-only confidence.\n\n"
        "## Jira observations\n\n"
        "- Fixture evidence only; Jira collection has not run.\n\n"
        "## KB guidance and citations\n\n"
        "- Fixture guidance only; KB retrieval has not run.\n\n"
        "## Hypotheses\n\n"
        "- Fixture hypothesis: confirm the live evidence before concluding root cause.\n\n"
        "## Unknowns and missing evidence\n\n"
        "- Jira and KB evidence are intentionally unavailable in fixture mode.\n\n"
        "## Next actions\n\n"
        "- Re-run with live adapters in a later ticket.\n\n"
        "## Provenance\n\n"
        f"- RCA Run: {run.run_id}\n"
        "- Model Runner: fixture\n"
        "- Collection Run: not collected\n"
        "- KB revision: not retrieved\n"
        "- Writeback Decision: not requested\n"
    )
    assert (tmp_path / run.run_id / "run.json").is_file()


def test_resume_returns_existing_fixture_run_without_creating_another_report(tmp_path: Path) -> None:
    workflow = RcaWorkflow(output_root=tmp_path)
    original = workflow.run(issue_key="PC-123", model="fixture")
    original_report = original.report_path.read_text(encoding="utf-8")

    resumed = workflow.resume(original.run_id)

    assert resumed == original
    assert resumed.report_path.read_text(encoding="utf-8") == original_report
    assert sorted(path.name for path in tmp_path.iterdir()) == [original.run_id]


def test_resume_rejects_a_persisted_illegal_workflow_transition(tmp_path: Path) -> None:
    workflow = RcaWorkflow(output_root=tmp_path)
    run = workflow.run(issue_key="PC-123", model="fixture")
    record_path = tmp_path / run.run_id / "run.json"
    record_path.write_text(
        record_path.read_text(encoding="utf-8").replace(
            '"state_history": [\n    "created",',
            '"state_history": [\n    "created",\n    "evaluated",',
        ),
        encoding="utf-8",
    )

    with pytest.raises(WorkflowTransitionError, match="created -> evaluated"):
        workflow.resume(run.run_id)
