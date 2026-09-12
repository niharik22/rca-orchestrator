"""The persisted workflow seam for local RCA runs."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from uuid import uuid4


class WorkflowTransitionError(ValueError):
    """Raised when a persisted RCA Run contains an illegal state change."""


_NEXT_STATES = {
    "created": "collected",
    "collected": "evidence_ready",
    "evidence_ready": "kb_ready",
    "kb_ready": "drafted",
    "drafted": "evaluated",
    "evaluated": "awaiting_decision",
    "awaiting_decision": "completed",
}


@dataclass(frozen=True)
class RcaRun:
    """One locally persisted RCA Run."""

    run_id: str
    issue_key: str
    model: str
    state: str
    state_history: tuple[str, ...]
    report_path: Path
    writeback_decision: str


class _LocalRunStore:
    def __init__(self, output_root: Path) -> None:
        self._output_root = output_root

    def create(self, issue_key: str, model: str) -> RcaRun:
        run_id = str(uuid4())
        run = RcaRun(
            run_id=run_id,
            issue_key=issue_key,
            model=model,
            state="created",
            state_history=("created",),
            report_path=self._output_root / run_id / "rca-report.md",
            writeback_decision="not_requested",
        )
        self.save(run)
        return run

    def load(self, run_id: str) -> RcaRun:
        record_path = self._output_root / run_id / "run.json"
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise FileNotFoundError(f"RCA Run not found: {run_id}") from error
        return RcaRun(
            run_id=record["run_id"],
            issue_key=record["issue_key"],
            model=record["model"],
            state=record["state"],
            state_history=tuple(record["state_history"]),
            report_path=self._output_root / run_id / record["report_file"],
            writeback_decision=record["writeback_decision"],
        )

    def save(self, run: RcaRun) -> None:
        run_directory = self._output_root / run.run_id
        run_directory.mkdir(parents=True, exist_ok=True)
        record = {
            "run_id": run.run_id,
            "issue_key": run.issue_key,
            "model": run.model,
            "state": run.state,
            "state_history": list(run.state_history),
            "report_file": run.report_path.name,
            "writeback_decision": run.writeback_decision,
        }
        (run_directory / "run.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )


class RcaWorkflow:
    """Coordinates the state machine exposed to the CLI and tests."""

    def __init__(self, output_root: Path) -> None:
        self._store = _LocalRunStore(output_root)

    def run(self, issue_key: str, model: str) -> RcaRun:
        """Start and finish one deterministic Fixture Runner RCA Run."""
        if model != "fixture":
            raise ValueError("Ticket 1 supports only the explicit fixture model")
        if not issue_key.strip():
            raise ValueError("issue_key must not be empty")
        return self._complete_fixture_run(self._store.create(issue_key, model))

    def resume(self, run_id: str) -> RcaRun:
        """Continue a saved Fixture Runner run without creating another run."""
        run = self._store.load(run_id)
        self._validate_history(run)
        if run.model != "fixture":
            raise ValueError("Ticket 1 can resume only fixture runs")
        return self._complete_fixture_run(run)

    def get(self, run_id: str) -> RcaRun:
        """Read one persisted RCA Run without advancing it."""
        run = self._store.load(run_id)
        self._validate_history(run)
        return run

    def _complete_fixture_run(self, run: RcaRun) -> RcaRun:
        while run.state != "completed":
            run = self._advance(run)
        self._render_report(run)
        self._store.save(run)
        return run

    def _advance(self, run: RcaRun) -> RcaRun:
        try:
            next_state = _NEXT_STATES[run.state]
        except KeyError as error:
            raise WorkflowTransitionError(
                f"Fixture run cannot advance from terminal or unknown state: {run.state}"
            ) from error
        advanced = replace(
            run,
            state=next_state,
            state_history=(*run.state_history, next_state),
        )
        self._store.save(advanced)
        return advanced

    def _validate_history(self, run: RcaRun) -> None:
        if not run.state_history or run.state_history[0] != "created":
            raise WorkflowTransitionError("Workflow State history must begin at created")
        if run.state_history[-1] != run.state:
            raise WorkflowTransitionError("Workflow State must match the persisted state history")
        for current, next_state in zip(run.state_history, run.state_history[1:]):
            if _NEXT_STATES.get(current) != next_state:
                raise WorkflowTransitionError(
                    f"Illegal Workflow State transition: {current} -> {next_state}"
                )

    def _render_report(self, run: RcaRun) -> None:
        run.report_path.write_text(
            "# RCA Report: " + run.issue_key + "\n\n"
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
            "- Writeback Decision: not requested\n",
            encoding="utf-8",
        )
