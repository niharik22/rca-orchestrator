# 04: Run live Copilot analysis and independent evaluation

**What to build:** A demo operator can select Copilot CLI for a live RCA Run. The RCA Analyst creates structured Hypotheses from a bounded Evidence Package; a fresh Evaluator determines `passed`, `needs_evidence`, or `escalated`, with all model and prompt provenance persisted.

**Blocked by:** 02 — Collect Jira evidence and retrieve cited KB guidance.

**Status:** completed

- [ ] Copilot CLI preflight failures are actionable and never silently switch to Fixture Runner behavior.
- [ ] Model Runner inputs are analysis-only and structured output is validated before Workflow State advances.
- [ ] Evaluated outcomes make citation gaps, contradictions, unknowns, and unverified KB applicability visible.
