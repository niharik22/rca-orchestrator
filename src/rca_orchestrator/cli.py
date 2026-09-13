"""Console entry points for the local RCA Orchestrator."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .jira_intelligence import JiraIntelligenceHttpClient
from .knowledge_base import ManifestKnowledgeBase
from .model_runner import CopilotCliRunner, ModelRunnerError
from .workflow import AttachmentLimits, RcaRun, RcaWorkflow


def _output_root(value: str | None) -> Path:
    configured_root = value or os.environ.get("RCA_ORCHESTRATOR_OUTPUTS_ROOT")
    return Path(configured_root) if configured_root else Path("outputs") / "rca-runs"


def _print_run(run: RcaRun) -> None:
    print(f"RCA Run: {run.run_id}")
    print(f"Issue: {run.issue_key}")
    print(f"Workflow State: {run.state}")
    print(f"Model Runner: {run.model}")
    print(f"RCA Report: {run.report_path}")


def _configured_workflow(output_root: Path) -> RcaWorkflow:
    jira_intelligence_url = os.environ.get("RCA_ORCHESTRATOR_JIRA_INTELLIGENCE_URL")
    kb_root = os.environ.get("RCA_ORCHESTRATOR_KB_ROOT")
    if not jira_intelligence_url:
        raise ValueError("RCA_ORCHESTRATOR_JIRA_INTELLIGENCE_URL must be configured")
    if not kb_root:
        raise ValueError("RCA_ORCHESTRATOR_KB_ROOT must be configured")
    return RcaWorkflow(
        output_root,
        jira_intelligence_client=JiraIntelligenceHttpClient(jira_intelligence_url),
        knowledge_base=ManifestKnowledgeBase(Path(kb_root)),
        attachment_limits=_attachment_limits_from_environment(),
        model_runner=CopilotCliRunner(
            executable=os.environ.get("RCA_ORCHESTRATOR_COPILOT_COMMAND", "copilot"),
            model=os.environ.get("RCA_ORCHESTRATOR_COPILOT_MODEL"),
        ),
    )


def _attachment_limits_from_environment() -> AttachmentLimits:
    return AttachmentLimits(
        per_file_bytes=_positive_environment_integer(
            "RCA_ORCHESTRATOR_ATTACHMENT_PER_FILE_BYTES", 2 * 1024 * 1024
        ),
        aggregate_bytes=_positive_environment_integer(
            "RCA_ORCHESTRATOR_ATTACHMENT_AGGREGATE_BYTES", 8 * 1024 * 1024
        ),
        model_characters=_positive_environment_integer(
            "RCA_ORCHESTRATOR_ATTACHMENT_MODEL_CHARACTERS", 200_000
        ),
    )


def _positive_environment_integer(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def run_main() -> None:
    parser = argparse.ArgumentParser(prog="rca-run")
    parser.add_argument("issue_key", nargs="?")
    parser.add_argument("--resume", metavar="RCA_RUN_ID")
    parser.add_argument("--model", choices=("fixture", "copilot"))
    parser.add_argument("--output-root")
    parser.add_argument("--product-version")
    arguments = parser.parse_args()
    if arguments.resume and arguments.issue_key:
        parser.error("issue_key cannot be used with --resume")
    if not arguments.resume and not arguments.issue_key:
        parser.error("issue_key is required unless --resume is used")
    if not arguments.resume and not arguments.model:
        parser.error("--model is required when starting an RCA Run")
    if arguments.resume and arguments.model:
        parser.error("--model cannot be used with --resume")

    try:
        workflow = _configured_workflow(_output_root(arguments.output_root))
        run = (
            workflow.resume(arguments.resume)
            if arguments.resume
            else workflow.run(arguments.issue_key, arguments.model, arguments.product_version)
        )
    except (ModelRunnerError, ValueError) as error:
        parser.error(str(error))
    _print_run(run)


def show_main() -> None:
    parser = argparse.ArgumentParser(prog="rca-show")
    parser.add_argument("run_id")
    parser.add_argument("--output-root")
    arguments = parser.parse_args()
    _print_run(RcaWorkflow(_output_root(arguments.output_root)).get(arguments.run_id))
