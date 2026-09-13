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

## Attachment Evidence

Jira Intelligence downloads the issue attachments and serves them through
opaque loopback artifact references. RCA can admit only `.txt`, `.log`,
`.json`, `.xml`, `.csv`, `.md`, `.js`, `.yaml`, and `.yml` files. All other
artifacts, unavailable attachments, and those outside the limits are recorded
as unanalysed evidence in the local run record and report.

The defaults are 2 MiB per file, 8 MiB total, and 200,000 text characters for
the model-facing excerpts. Change them for a demo session without committing
local settings:

```sh
export RCA_ORCHESTRATOR_ATTACHMENT_PER_FILE_BYTES=2097152
export RCA_ORCHESTRATOR_ATTACHMENT_AGGREGATE_BYTES=8388608
export RCA_ORCHESTRATOR_ATTACHMENT_MODEL_CHARACTERS=200000
```

```powershell
$env:RCA_ORCHESTRATOR_ATTACHMENT_PER_FILE_BYTES = "2097152"
$env:RCA_ORCHESTRATOR_ATTACHMENT_AGGREGATE_BYTES = "8388608"
$env:RCA_ORCHESTRATOR_ATTACHMENT_MODEL_CHARACTERS = "200000"
```

## Live Copilot mode

Install and authenticate GitHub Copilot CLI on the work laptop first:

```powershell
winget install GitHub.Copilot
copilot login
```

Then select live analysis explicitly. This invokes a bounded Analyst prompt and
a separate Evaluator prompt; it never falls back to fixture output.

```powershell
uv run rca-run PC-123 --model copilot
```

To pin an available Copilot model or use a non-default command location for a
demo session, set `RCA_ORCHESTRATOR_COPILOT_MODEL` or
`RCA_ORCHESTRATOR_COPILOT_COMMAND`. The orchestrator invokes Copilot with its
available tools, built-in MCPs, custom instructions, and remote session access
disabled. It provides the prompt through standard input and retains the prompt
and raw structured output only in the local RCA Run record.
