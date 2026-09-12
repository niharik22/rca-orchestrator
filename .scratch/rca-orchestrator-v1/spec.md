# RCA Orchestrator V1

Status: ready-for-agent

## Problem Statement

For the demonstration, a user needs to turn one non-production Jira issue into a reviewable Root Cause Analysis without manually assembling Jira context, searching the PolicyCenter knowledge base, or copying a conclusion back into Jira. Jira Intelligence already owns immutable Collection Runs and controlled Jira writeback, while the PolicyCenter KB is a separate local source of guidance. There is no deterministic, evidence-first workflow that joins them, records what the model was shown, distinguishes fact from reported claims, evaluates unsupported conclusions, and controls the Jira mutation.

## Solution

Provide a local Python CLI in the RCA Orchestrator repository. An RCA Run collects or reuses a Jira Intelligence Collection Run, builds a bounded Evidence Package, retrieves a small cited set of KB Passages through manifest-first traversal, and gives that package to an RCA Analyst Model Runner. A fresh Evaluator Model Runner determines the Evaluation Result. The CLI records replayable local state, shows the outcome, then asks for a terminal Writeback Decision. Jira Intelligence remains the sole Jira read/write integration.

The CLI uses Copilot CLI as its V1 live Model Runner, with a deliberate Fixture Runner for deterministic tests and fallback demonstrations. It is not an RCA HTTP service and it is not an autonomous multi-agent system.

## User Stories

1. As a demo operator, I want to start an RCA Run with one Jira issue key, so that I can analyze a specific incident without assembling evidence manually.
2. As a demo operator, I want the CLI to reuse or create a Collection Run through Jira Intelligence, so that RCA analysis is tied to immutable Jira evidence.
3. As a demo operator, I want the CLI to identify the Collection Run used by an RCA Run, so that I can explain the evidence provenance during a demonstration.
4. As a demo operator, I want to choose Copilot CLI or an explicit Fixture Runner, so that I can demonstrate live AI when it is available and deterministic behavior when it is not.
5. As a demo operator, I want a clear preflight failure when Copilot CLI is unavailable or not authenticated, so that a fixture result is never mistaken for a live AI result.
6. As a demo operator, I want the CLI to access only the configured sibling PolicyCenter KB root, so that it cannot inspect arbitrary local files.
7. As a demo operator, I want KB retrieval to begin with the manifest and select a small cited set of relevant material, so that the analysis remains scoped and reproducible.
8. As a demo operator, I want Product Version to be optional, so that a version is not required for the demonstration while missing version applicability remains visible.
9. As a demo operator, I want Jira observations, reported-but-unverified statements, and missing evidence kept distinct, so that the RCA Report does not overstate what Jira proves.
10. As a demo operator, I want text-like log and source attachments included only within configured limits, so that useful evidence is available without unbounded model input.
11. As a demo operator, I want unsupported or oversized attachments listed as unanalysed evidence, so that their exclusion is transparent.
12. As an RCA Analyst, I want a bounded Evidence Package and cited KB Passages, so that I can produce falsifiable Hypotheses rather than an ungrounded narrative.
13. As an RCA Analyst, I want every Hypothesis to include supporting evidence, contradicting evidence, unknowns, and confidence, so that alternative explanations remain visible.
14. As an Evaluator, I want a fresh prompt invocation with the RCA draft and cited evidence, so that the Evaluation Result is independent of the Analyst's hidden reasoning.
15. As a demo operator, I want an Evaluation Result of `passed`, `needs_evidence`, or `escalated`, so that I know whether the RCA Report may be attached to Jira.
16. As a demo operator, I want a distinct Blocked Run when Jira collection or KB access fails, so that an operational failure is not represented as an evaluated RCA conclusion.
17. As a demo operator, I want a `needs_evidence`, `escalated`, or Blocked Run to offer a terminal-confirmed Status Comment, so that Jira visibly records the RCA follow-up without claiming a root cause.
18. As a demo operator, I want a passed RCA Run to offer a terminal-confirmed status comment and RCA Report attachment, so that Jira receives a concise outcome and complete evidence-cited report.
19. As a Jira user, I want any non-passed Jira comment to state its outcome and uncertainty clearly, so that it cannot be misread as a confirmed root cause.
20. As a Jira user, I want Jira mutations performed only through Jira Intelligence with provenance and idempotency, so that duplicate comments and attachments are prevented.
21. As a demo operator, I want to decline the terminal prompt without any Jira mutation, so that viewing an RCA result is safe by default.
22. As a demo operator, I want the Markdown RCA Report to contain outcome, evidence, KB guidance, Hypotheses, unknowns, next actions, and provenance, so that it can stand alone when attached to Jira.
23. As a demo operator, I want local RCA Run records to retain model, prompt, KB revision, passages, evaluation, Writeback Decision, and Jira event identifiers, so that I can inspect or replay the run.
24. As a demo operator, I want to resume an interrupted RCA Run, so that I do not create a new Collection Run or repeat a model call unnecessarily.
25. As a demo operator, I want to inspect a saved RCA Run without rerunning it, so that I can review its report and writeback status during a demonstration.
26. As a developer, I want the work laptop to reproduce the CLI from the sibling repositories and locked dependencies, so that setup does not require a separate RCA deployment.
27. As a developer, I want all automated tests to use fakes and fixtures instead of live Jira, KB, or Copilot accounts, so that tests are repeatable and safe.
28. As a future developer, I want a Model Runner seam that can accommodate Claude or Codex CLI later, so that adding a provider does not alter the evidence, evaluation, or writeback rules.
29. As a future developer, I want a CLI-first workflow with a small interface, so that a later UI can reuse the same RCA workflow without changing its behavior.

## Implementation Decisions

- `RcaWorkflow` is the single deep module and the primary interface for callers and tests. It exposes run and Resume behavior; it owns all Workflow State transitions and hides adapter coordination.
- The Workflow State lifecycle is `created → collected → evidence_ready → kb_ready → drafted → evaluated → awaiting_decision → written_back | completed`. A prerequisite failure before evaluation creates a Blocked Run.
- Only two AI roles exist in V1: RCA Analyst and Evaluator. Jira collection, KB selection, state persistence, report rendering, terminal confirmation, and Jira writeback are deterministic modules.
- The Jira Intelligence client uses the existing loopback collection, run-discovery, and controlled writeback contracts. The RCA Orchestrator makes no direct Jira REST calls.
- The workspace root used to place an RCA Report in a Collection Run is fixed server-side configuration. It is not caller input.
- KB retrieval loads the configured manifest first, rejects paths outside the configured KB root, and deterministically selects no more than three domains and six KB Passages from Jira components, labels, title, description, and recognized error names.
- Product Version is optional. When absent, the RCA Report and Evaluation Result explicitly identify KB-version applicability as unverified.
- Attachment Evidence is restricted to `.txt`, `.log`, `.json`, `.xml`, `.csv`, `.md`, `.js`, `.yaml`, and `.yml`. Limits are configurable with V1 defaults of 2 MiB per file, 8 MiB aggregate, and 200,000 characters delivered to a Model Runner. Excluded attachments remain visible in provenance.
- Model Runners are analysis-only adapters. They receive a generated Evidence Package and prompt over standard input; they receive no workspace paths, filesystem/shell authority, Jira credentials, or mutation authority.
- Copilot CLI is the live V1 Model Runner. It must preflight successfully and fail clearly when unavailable. Fixture Runner use is explicit and must be visible in run provenance.
- The Evaluator is a second fresh Model Runner invocation with the draft, Evidence Package, and KB Passages, but not the Analyst's hidden reasoning.
- All Model Runner output is validated against structured contracts before it can advance a Workflow State.
- A passed Evaluation Result may offer terminal-confirmed comment and attachment writeback. `needs_evidence` and `escalated` may offer only a labelled Status Comment. A Blocked Run may offer a Status Comment only after successful Jira collection.
- The Writeback Decision is persisted before a Jira mutation is requested. Every request uses a unique idempotency key and includes Collection Run, RCA Run, and approval provenance.
- The RCA Report is Markdown with fixed sections for outcome/confidence, Jira observations, KB guidance/citations, Hypotheses, most likely explanation when passed, unknowns, recommended actions, and provenance.
- Only the Markdown RCA Report is placed in Jira Intelligence's `analysis/` location. Machine-readable report data, run records, raw Model Runner output, and evaluation records remain in local RCA outputs.
- The human-facing CLI surface is `rca-run <issue-key>`, `rca-show <rca-run-id>`, and resume through `rca-run --resume <rca-run-id>`.
- The project is an independent, local Git repository with a locked Python dependency environment. Jira Intelligence and PolicyCenter remain sibling repositories and are not packaged inside it.

## Testing Decisions

- Good tests exercise the `RcaWorkflow` interface and assert observable Workflow State, persisted RCA Run data, generated RCA Report content, and requested Jira mutations. They do not assert private adapter calls or prompt-string construction details.
- The test suite will drive `run` and Resume with fake Jira Intelligence, KB, Model Runner, local run-store, clock, terminal decision, and writeback adapters. The same seam supports unit and end-to-end workflow tests without live services.
- Tests cover every legal and illegal Workflow State transition, including the inability to write back before evaluation or without a persisted Writeback Decision.
- Tests cover Collection Run reuse, deterministic KB selection, manifest-first traversal, path containment, absent Product Version, citation provenance, attachment allow-listing, file/aggregate/character limits, and visible treatment of unanalysed attachments.
- Tests cover valid Analyst and Evaluator structured output, malformed output rejection, unsupported claims, missing citations, contradictions, and unverified KB applicability.
- Tests cover passed, `needs_evidence`, `escalated`, and Blocked Run behavior, including the allowed Jira mutation scope for each outcome.
- Tests cover idempotent comment/attachment requests, declined Writeback Decisions, resumed runs, and the rule that only the Markdown RCA Report enters the Jira upload location.
- Fixture Runner tests are the prior art for deterministic model behavior. Existing Jira Intelligence tests and its REST contracts are the prior art for Jira client fakes and controlled writeback assertions.
- No automated test requires live Jira credentials, a live PolicyCenter clone, a Copilot entitlement, or network access.

## Out of Scope

- A deployed RCA web application, browser UI, REST API, separate RCA port, service authentication, or multi-user access.
- Direct Jira REST use, autonomous Jira mutations, and any mutation that bypasses Jira Intelligence.
- A Knowledge Service, vector database, embeddings, document ingestion pipeline, chunking service, or general semantic search.
- PDF, Office, image, OCR, archive, binary, or unrestricted attachment parsing.
- Model-driven recursive retrieval, autonomous sub-agent delegation, or more than the RCA Analyst and Evaluator AI roles.
- Automatic fallback from Copilot CLI to Fixture Runner.
- A required Product Version, a separate Code Analysis Service, or automatic source-code inspection outside the configured KB.
- Publishing to a package registry, production deployment, or work beyond the local Git/`uv` handoff used for the demonstration.
- Claude CLI, Codex CLI, or other provider implementations; the Model Runner seam is retained for later additions.

## Further Notes

- The RCA Orchestrator is a single-context repository. `CONTEXT.md` is the canonical glossary, and the accepted ADRs record the architectural decisions this spec implements.
- The local issue tracker convention publishes this specification as `.scratch/rca-orchestrator-v1/spec.md` with `ready-for-agent` status. Future implementation tickets belong under the same feature directory.
- The implementation must preserve the Windows-compatible Jira Intelligence V2 behavior already delivered. The RCA project itself must remain portable across the work laptop and Mac.
- Demo setup requires sibling Jira Intelligence and PolicyCenter clones, their configured local paths, Jira Intelligence running on its existing loopback endpoint, and an approved Copilot CLI login for live-model mode.
