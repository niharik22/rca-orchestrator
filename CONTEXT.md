# RCA Orchestrator

The RCA Orchestrator turns one Jira issue into an evidence-cited root-cause analysis report using Jira Intelligence, the PolicyCenter knowledge base, and a model runner.

## Runs and Evidence

**RCA Run**:
One replayable execution of the RCA workflow for a Jira issue. It records the linked Collection Run, selected KB passages, model/evaluation metadata, and any writeback decision.
_Avoid_: analysis, job, session

**Collection Run**:
The immutable Jira evidence snapshot created by Jira Intelligence for one issue collection. It is owned by Jira Intelligence, not by the RCA Orchestrator.
_Avoid_: RCA run, Jira snapshot

**Evidence Package**:
The bounded set of observations and references from a Collection Run that may be given to a model runner. It distinguishes confirmed Jira observations, reported-but-unverified claims, and missing evidence.
_Avoid_: context dump, issue data

**Model Runner**:
An analysis-only adapter that turns an Evidence Package into validated structured findings. Copilot CLI is the V1 live runner; a Fixture Runner provides deterministic fallback.
_Avoid_: agent, orchestrator, Jira client

**RCA Analyst**:
The first Model Runner role. It produces falsifiable hypotheses and an RCA draft from the bounded Evidence Package and KB Passages.
_Avoid_: coordinator, retrieval agent

**Evaluator**:
A fresh model invocation that judges an RCA draft against its Evidence Package and KB Passages. It does not receive the coordinator's hidden reasoning.
_Avoid_: coordinator, reviewer prompt

**KB Passage**:
A bounded, cited excerpt retrieved from the configured PolicyCenter knowledge base through manifest-first traversal.
_Avoid_: knowledge result, document chunk

**KB Selection**:
The deterministic first-pass choice of at most three KB domains and six KB Passages using Jira components, labels, title, description, and recognized error names. It does not depend on a model hypothesis in V1.
_Avoid_: agent search, open-ended retrieval

**Attachment Evidence**:
A text-like Jira attachment admitted to the Evidence Package within the configured file, aggregate, and prompt-excerpt limits. Unsupported or oversized attachments remain visible but unanalysed.
_Avoid_: attachment bytes, document analysis

**Product Version**:
An optional PolicyCenter version supplied for an RCA Run. When absent, a report must label KB version applicability as unverified.
_Avoid_: inferred version, current version

## Conclusions and Mutation

**Hypothesis**:
A falsifiable possible explanation for an issue, with supporting and contradicting evidence references, unknowns, and confidence.
_Avoid_: root cause, finding

**Evaluation Result**:
The independent decision that a draft is `passed`, `needs_evidence`, or `escalated`. A passed result may write a report attachment and summary comment; the other outcomes may write only an explicit status comment.
_Avoid_: validation, approval

**Blocked Run**:
An RCA Run that cannot enter evaluation because a technical prerequisite, such as Jira collection or KB manifest access, failed. It contains no model-generated RCA report.
_Avoid_: needs evidence, failed evaluation

**Writeback Decision**:
The terminal user's final `y` or `N` response after an evaluation result is displayed. A `y` is persisted and permits the controlled writeback allowed by that result.
_Avoid_: automatic writeback, separate approval workflow

**Status Comment**:
A Jira comment that reports the RCA evaluation outcome without asserting an unsupported root cause. It is the only Jira mutation allowed for a `needs_evidence` or `escalated` result.
_Avoid_: RCA result, failed report

**RCA Report**:
The human-readable, evidence-cited Markdown result of a passed RCA Run. Only this artifact is placed in Jira Intelligence's `analysis/` directory for attachment writeback.
_Avoid_: run record, raw model output

**Resume**:
Continuation of an existing RCA Run using its recorded Collection Run and state rather than beginning a new collection or model call.
_Avoid_: rerun, retry from scratch

**Workflow State**:
The persisted lifecycle position of an RCA Run. Only the RCA workflow may advance it after validating the prior stage's recorded output.
_Avoid_: agent status, task status
