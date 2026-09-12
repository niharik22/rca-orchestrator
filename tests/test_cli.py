from __future__ import annotations

import subprocess
from shutil import which
from pathlib import Path


def test_fixture_commands_start_show_and_resume_a_local_run(tmp_path: Path) -> None:
    started = _run("rca-run", "PC-123", "--model", "fixture", "--output-root", str(tmp_path))

    assert started.returncode == 0, started.stderr
    run_id = _field(started.stdout, "RCA Run")
    assert _field(started.stdout, "Workflow State") == "completed"
    assert _field(started.stdout, "Model Runner") == "fixture"

    shown = _run("rca-show", run_id, "--output-root", str(tmp_path))
    resumed = _run("rca-run", "--resume", run_id, "--output-root", str(tmp_path))

    assert shown.returncode == 0, shown.stderr
    assert resumed.returncode == 0, resumed.stderr
    assert _field(shown.stdout, "RCA Report") == _field(started.stdout, "RCA Report")
    assert _field(resumed.stdout, "RCA Run") == run_id


def _run(command: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    executable = which(command)
    assert executable is not None, f"{command} is not installed in the test environment"
    return subprocess.run(
        [executable, *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def _field(output: str, name: str) -> str:
    prefix = f"{name}: "
    return next(line.removeprefix(prefix) for line in output.splitlines() if line.startswith(prefix))
