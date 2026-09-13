"""Console entry points for the local RCA Orchestrator."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .workflow import RcaRun, RcaWorkflow


def _output_root(value: str | None) -> Path:
    configured_root = value or os.environ.get("RCA_ORCHESTRATOR_OUTPUTS_ROOT")
    return Path(configured_root) if configured_root else Path("outputs") / "rca-runs"


def _print_run(run: RcaRun) -> None:
    print(f"RCA Run: {run.run_id}")
    print(f"Issue: {run.issue_key}")
    print(f"Workflow State: {run.state}")
    print(f"Model Runner: {run.model}")
    print(f"RCA Report: {run.report_path}")


def run_main() -> None:
    parser = argparse.ArgumentParser(prog="rca-run")
    parser.add_argument("issue_key", nargs="?")
    parser.add_argument("--resume", metavar="RCA_RUN_ID")
    parser.add_argument("--model", choices=("fixture",))
    parser.add_argument("--output-root")
    arguments = parser.parse_args()
    if arguments.resume and arguments.issue_key:
        parser.error("issue_key cannot be used with --resume")
    if not arguments.resume and not arguments.issue_key:
        parser.error("issue_key is required unless --resume is used")
    if not arguments.resume and not arguments.model:
        parser.error("--model is required when starting an RCA Run")
    if arguments.resume and arguments.model:
        parser.error("--model cannot be used with --resume")

    workflow = RcaWorkflow(_output_root(arguments.output_root))
    run = (
        workflow.resume(arguments.resume)
        if arguments.resume
        else workflow.run(arguments.issue_key, arguments.model)
    )
    _print_run(run)


def show_main() -> None:
    parser = argparse.ArgumentParser(prog="rca-show")
    parser.add_argument("run_id")
    parser.add_argument("--output-root")
    arguments = parser.parse_args()
    _print_run(RcaWorkflow(_output_root(arguments.output_root)).get(arguments.run_id))
