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

## Terminal-confirmed Jira writeback

After a completed evaluation, `rca-run` displays the run and asks:

```text
Write this RCA evaluation back to Jira? [y/N]:
```

Pressing Enter or entering anything other than `y` records `declined` locally
and makes no Jira mutation. Entering `y` records `approved` first, then asks
Jira Intelligence to make the permitted idempotent writeback. The Jira
Intelligence service must be configured with its separately scoped write
credential and allowed project keys.

For `needs_evidence` and `escalated`, RCA writes only a clearly labelled status
comment. For `passed`, it writes that comment and uploads the Markdown RCA
report. Set the following path to the *same directory* that Jira Intelligence
uses as `JIRA_INTELLIGENCE_UPLOAD_SOURCE_ROOT` (or its workspace root when that
setting is omitted):

```powershell
$env:RCA_ORCHESTRATOR_JIRA_INTELLIGENCE_UPLOAD_SOURCE_ROOT = "C:\path\to\jira-intelligence-workspace"
```

RCA places only `rca-report.md` in the required
`<upload-root>/<issue>/runs/<collection-run>/analysis/` directory. If the
directory contains another file, it refuses the passed writeback rather than
risk uploading an unrelated artifact. The local RCA record persists the
terminal decision and Jira Intelligence Writeback Event IDs; replaying an
approved run uses the same independent comment and attachment idempotency keys.

## Windows demo rehearsal

Keep the three repositories as siblings. The PolicyCenter repository is the
only one that contains the real `.kb`; RCA never copies it into its own
repository.

```text
C:\development\
  jira-mcp\
  policycenter\
    .kb\
  rca-orchestrator\
```

Open two PowerShell terminals. In the first, start Jira Intelligence. Configure
the Jira read and (only if demonstrating writeback) separately scoped write
credentials following the sibling project's README. Use a non-production Jira
project for this rehearsal.

```powershell
Set-Location C:\development\jira-mcp
$env:JIRA_INTELLIGENCE_WORKSPACE_ROOT = "C:\development\jira-intelligence-workspace"
$env:JIRA_INTELLIGENCE_UPLOAD_SOURCE_ROOT = $env:JIRA_INTELLIGENCE_WORKSPACE_ROOT
$env:JIRA_INTELLIGENCE_DATABASE_URL = "postgresql://localhost/jira_intelligence"
# Set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN for collection.
# To permit writeback, also set JIRA_WRITE_EMAIL, JIRA_WRITE_API_TOKEN,
# and JIRA_INTELLIGENCE_WRITEBACK_ALLOWED_PROJECT_KEYS.
uv sync
uv run jira-intelligence
```

In the second terminal, prepare RCA. `fixture` proves the local Jira
Intelligence + KB wiring without using model output; it does **not** bypass Jira
collection or KB retrieval. `copilot` is the live demo mode and performs an
actionable preflight before collection.

```powershell
Set-Location C:\development\rca-orchestrator
uv sync
uv run pytest -q

$env:RCA_ORCHESTRATOR_JIRA_INTELLIGENCE_URL = "http://127.0.0.1:8001"
$env:RCA_ORCHESTRATOR_KB_ROOT = "C:\development\policycenter\.kb"
$env:RCA_ORCHESTRATOR_JIRA_INTELLIGENCE_UPLOAD_SOURCE_ROOT = "C:\development\jira-intelligence-workspace"
$env:RCA_ORCHESTRATOR_OUTPUTS_ROOT = "C:\development\rca-outputs"

uv run rca-run PC-123 --model fixture
```

For live analysis, install and authenticate Copilot CLI once, then rerun using
the same issue (replace `PC-123` with an allowed non-production Jira issue):

```powershell
winget install GitHub.Copilot
copilot login
uv run rca-run PC-123 --model copilot --product-version "50.16.0 P1"
```

At `Write this RCA evaluation back to Jira? [y/N]:`, press Enter to rehearse a
declined decision: it must create no Jira comment or attachment. Enter `y` only
when the Jira Intelligence writeback credentials and allowed project are set.
`needs_evidence` and `escalated` create only a status comment; `passed` also
uploads `rca-report.md`.

Copy the printed RCA Run ID to inspect or resume it:

```powershell
uv run rca-show <RCA_RUN_ID> --output-root $env:RCA_ORCHESTRATOR_OUTPUTS_ROOT
uv run rca-run --resume <RCA_RUN_ID> --output-root $env:RCA_ORCHESTRATOR_OUTPUTS_ROOT
```

Resume uses the saved Collection Run and saved model output. A completed run
does not recollect Jira or reinvoke Copilot. An already-approved writeback is
replayed only with the same Jira Intelligence idempotency keys, so Jira
Intelligence returns its recorded Writeback Events rather than creating another
Jira mutation.
