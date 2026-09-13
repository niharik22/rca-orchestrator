from __future__ import annotations

import os
import subprocess
from shutil import which
from pathlib import Path


def test_fixture_run_requires_jira_intelligence_and_kb_configuration(tmp_path: Path) -> None:
    started = _run("rca-run", "PC-123", "--model", "fixture", "--output-root", str(tmp_path))

    assert started.returncode == 2
    assert "RCA_ORCHESTRATOR_JIRA_INTELLIGENCE_URL must be configured" in started.stderr


def test_starting_a_run_requires_an_explicit_model_choice(tmp_path: Path) -> None:
    started = _run("rca-run", "PC-123", "--output-root", str(tmp_path))

    assert started.returncode == 2
    assert "--model is required" in started.stderr


def test_attachment_evidence_limits_can_be_configured_from_the_environment(tmp_path: Path) -> None:
    started = _run(
        "rca-run",
        "PC-123",
        "--model",
        "fixture",
        "--output-root",
        str(tmp_path),
        environment={
            "RCA_ORCHESTRATOR_JIRA_INTELLIGENCE_URL": "http://127.0.0.1:8001",
            "RCA_ORCHESTRATOR_KB_ROOT": str(tmp_path / "kb"),
            "RCA_ORCHESTRATOR_ATTACHMENT_PER_FILE_BYTES": "zero",
        },
    )

    assert started.returncode == 2
    assert "RCA_ORCHESTRATOR_ATTACHMENT_PER_FILE_BYTES must be a positive integer" in started.stderr


def test_copilot_preflight_failure_is_reported_without_falling_back_to_fixture(tmp_path: Path) -> None:
    started = _run(
        "rca-run", "PC-123", "--model", "copilot", "--output-root", str(tmp_path),
        environment={
            "RCA_ORCHESTRATOR_JIRA_INTELLIGENCE_URL": "http://127.0.0.1:8001",
            "RCA_ORCHESTRATOR_KB_ROOT": str(tmp_path / "kb"),
            "RCA_ORCHESTRATOR_COPILOT_COMMAND": "missing-copilot-for-test",
        },
    )

    assert started.returncode == 2
    assert "Copilot CLI is unavailable" in started.stderr
    assert "Fixture Runner" not in started.stderr


def _run(
    command: str, *arguments: str, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    executable = which(command)
    assert executable is not None, f"{command} is not installed in the test environment"
    return subprocess.run(
        [executable, *arguments],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **(environment or {})},
    )
