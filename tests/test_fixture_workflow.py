import json
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
        "- Prompt: fixture-v1\n"
        "- Writeback Decision: not requested\n"
    )
    assert (tmp_path / run.run_id / "run.json").is_file()


def test_fixture_run_persists_explicit_local_provenance(tmp_path: Path) -> None:
    run = RcaWorkflow(output_root=tmp_path).run(issue_key="PC-123", model="fixture")

    record = json.loads((tmp_path / run.run_id / "run.json").read_text(encoding="utf-8"))

    assert record["collection_run_id"] == "not_collected"
    assert record["kb_revision"] == "not_retrieved"
    assert record["kb_passage_ids"] == []
    assert record["evaluation_result"] == "fixture_completed"
    assert record["model_prompt"] == "fixture-v1"
    assert record["jira_event_ids"] == []


def test_resume_returns_existing_fixture_run_without_creating_another_report(tmp_path: Path) -> None:
    workflow = RcaWorkflow(output_root=tmp_path)
    original = workflow.run(issue_key="PC-123", model="fixture")
    original_report = original.report_path.read_text(encoding="utf-8")

    resumed = workflow.resume(original.run_id)

    assert resumed == original
    assert resumed.report_path.read_text(encoding="utf-8") == original_report
    assert sorted(path.name for path in tmp_path.iterdir()) == [original.run_id]


@pytest.mark.parametrize(
    "state_history",
    [
        ("created",),
        ("created", "collected"),
        ("created", "collected", "evidence_ready"),
        ("created", "collected", "evidence_ready", "kb_ready"),
        ("created", "collected", "evidence_ready", "kb_ready", "drafted"),
        (
            "created",
            "collected",
            "evidence_ready",
            "kb_ready",
            "drafted",
            "evaluated",
        ),
        (
            "created",
            "collected",
            "evidence_ready",
            "kb_ready",
            "drafted",
            "evaluated",
            "awaiting_decision",
        ),
        (
            "created",
            "collected",
            "evidence_ready",
            "kb_ready",
            "drafted",
            "evaluated",
            "awaiting_decision",
            "written_back",
        ),
    ],
)
def test_resume_accepts_each_legal_persisted_workflow_state(
    tmp_path: Path, state_history: tuple[str, ...]
) -> None:
    workflow = RcaWorkflow(output_root=tmp_path)
    run = workflow.run(issue_key="PC-123", model="fixture")
    _persist_state_history(tmp_path / run.run_id / "run.json", state_history)

    resumed = workflow.resume(run.run_id)

    assert resumed.state == ("written_back" if state_history[-1] == "written_back" else "completed")


@pytest.mark.parametrize(
    "state_history",
    [
        ("created", "evidence_ready"),
        ("created", "collected", "kb_ready"),
        ("created", "collected", "evidence_ready", "drafted"),
        ("created", "collected", "evidence_ready", "kb_ready", "evaluated"),
        (
            "created",
            "collected",
            "evidence_ready",
            "kb_ready",
            "drafted",
            "awaiting_decision",
        ),
        (
            "created",
            "collected",
            "evidence_ready",
            "kb_ready",
            "drafted",
            "evaluated",
            "completed",
        ),
        (
            "created",
            "collected",
            "evidence_ready",
            "kb_ready",
            "drafted",
            "evaluated",
            "awaiting_decision",
            "completed",
            "collected",
        ),
    ],
)
def test_resume_rejects_each_illegal_persisted_workflow_transition(
    tmp_path: Path, state_history: tuple[str, ...]
) -> None:
    workflow = RcaWorkflow(output_root=tmp_path)
    run = workflow.run(issue_key="PC-123", model="fixture")
    _persist_state_history(tmp_path / run.run_id / "run.json", state_history)

    with pytest.raises(WorkflowTransitionError, match="Illegal Workflow State transition"):
        workflow.resume(run.run_id)


def _persist_state_history(record_path: Path, state_history: tuple[str, ...]) -> None:
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["state"] = state_history[-1]
    record["state_history"] = list(state_history)
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
