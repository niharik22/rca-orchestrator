# RCA Orchestrator V1 Implementation Plan

## Outcome

Deliver a local Python CLI that analyzes one Jira issue using a bounded PolicyCenter KB retrieval and Copilot CLI, records an evidence-cited RCA Run, and performs only terminal-confirmed Jira writeback through Jira Intelligence.

## Non-negotiable seams

`RcaWorkflow` is the single deep module. Its public interface is `run(issue_key, model)` and `resume(rca_run_id)`. It owns the state machine and hides the following adapters:

- Jira Intelligence client — collection, run lookup, and controlled writeback;
- KB adapter — manifest-first traversal and bounded cited passages;
- Model Runner — `CopilotCliRunner` and explicit `FixtureRunner`;
- run store — local JSON records under `outputs/rca-runs/`;
- report writer — local record plus one Markdown report in Jira Intelligence's `analysis/` directory.

Only the RCA Analyst and Evaluator are AI roles. They receive no filesystem, shell, Jira credential, or mutation authority.

## State machine

```text
created → collected → evidence_ready → kb_ready → drafted → evaluated
        → awaiting_decision → written_back | completed
created | collected | evidence_ready | kb_ready → blocked
```

`passed` permits a terminal-confirmed status comment and Markdown attachment. `needs_evidence` and `escalated` permit only a terminal-confirmed Status Comment. A `blocked` run has no model report and may offer a status comment only when Jira collection succeeded.

## Build slices

1. **Package foundation**
   - Initialize the independent repository and Python 3.12 package.
   - Add `pyproject.toml`, `uv.lock`, `src/`, `tests/`, `.gitignore`, README, configuration loading, Pydantic models, and local JSON run store.
   - Implement the persisted transition guard and unit tests for legal/illegal state changes.

2. **Jira Intelligence adapter**
   - Implement collection/reuse, collection-run lookup, and error mapping against the existing loopback endpoints.
   - Add fixed workspace-root resolution for the selected Collection Run's `analysis/` directory.
   - Use fakes in unit tests; no live Jira or Copilot calls in the test suite.

3. **Bounded evidence and KB retrieval**
   - Build the evidence package from the Intelligence Envelope.
   - Admit only `.txt`, `.log`, `.json`, `.xml`, `.csv`, `.md`, `.js`, `.yaml`, and `.yml` attachment evidence.
   - Enforce configurable 2 MiB-per-file, 8 MiB-total, and 200,000-character model-package limits.
   - Implement manifest-first KB traversal, deterministic selection of at most three domains and six cited passages, containment checks, and optional Product Version provenance.

4. **Model and evaluation**
   - Implement the explicit fixture runner first.
   - Add Copilot CLI runner with preflight checks, bounded standard-input prompt, structured-output parsing, prompt/model metadata, and clear failure behavior.
   - Add a fresh evaluator invocation that validates claims, citation coverage, contradictions, uncertainty, and KB applicability.

5. **Report and controlled writeback**
   - Render the approved fixed Markdown RCA report.
   - Save local JSON audit artifacts only under the RCA project outputs.
   - Place only `rca-report.md` under the Collection Run `analysis/` directory.
   - Present `[y/N]`; persist the Writeback Decision and call Jira Intelligence with unique idempotency keys.

6. **CLI and demo hardening**
   - Provide `rca-run <issue-key>` and `rca-show <rca-run-id>`, plus `rca-run --resume <rca-run-id>`.
   - Make `--model fixture` explicit; fail clearly when Copilot CLI is unavailable.
   - Add README work-laptop setup, preflight diagnostics, demo walkthrough, expected result fixtures, and adversarial tests.

## Demonstration exit criteria

- A non-production Jira issue can be collected or reused through Jira Intelligence.
- The CLI produces a cited report using Copilot CLI or an explicit fixture.
- Every outcome and writeback decision is persisted locally and inspectable with `rca-show`.
- Unsupported conclusions cannot attach a report; they can only produce a labelled status comment after confirmation.
- A passed report writes exactly one Jira comment and one Markdown attachment on confirmed writeback.
- The work laptop can recreate the runtime using only the RCA repository, sibling Jira Intelligence and PolicyCenter clones, configured environment variables, and `uv sync`.
