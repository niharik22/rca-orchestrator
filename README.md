# RCA Orchestrator

Local CLI for replayable Root Cause Analysis runs. The first implementation
supports the explicit, deterministic Fixture Runner. Ticket 2 still uses real
Jira Intelligence Collection Runs and the configured PolicyCenter KB; only the
analysis result is fixture-backed.

## Ticket 2 setup

Start the sibling Jira Intelligence service first. Then configure the RCA CLI
with its loopback URL and the path to the PolicyCenter `.kb` directory:

```sh
export RCA_ORCHESTRATOR_JIRA_INTELLIGENCE_URL="http://127.0.0.1:8001"
export RCA_ORCHESTRATOR_KB_ROOT="/absolute/path/to/policycenter/.kb"
uv run rca-run PC-123 --model fixture --product-version "50.16.0 P1"
```

`--product-version` is optional. When it is omitted, the local RCA record and
report explicitly mark KB version applicability as `unverified`.

On Windows PowerShell, use:

```powershell
$env:RCA_ORCHESTRATOR_JIRA_INTELLIGENCE_URL = "http://127.0.0.1:8001"
$env:RCA_ORCHESTRATOR_KB_ROOT = "C:\path\to\policycenter\.kb"
uv run rca-run PC-123 --model fixture
```

The KB must begin with `manifest.yaml`. Its domains are a list (or mapping) of
`id`, `path`, and `keywords`; each selected domain has `index.yaml` with a
`passages` list of relative Markdown paths. RCA deterministically selects at
most three matching domains and six cited passages, and rejects any path that
escapes the configured KB root.
