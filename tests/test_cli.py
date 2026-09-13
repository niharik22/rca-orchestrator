from __future__ import annotations

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


def _run(command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    executable = which(command)
    assert executable is not None, f"{command} is not installed in the test environment"
    return subprocess.run(
        [executable, *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
