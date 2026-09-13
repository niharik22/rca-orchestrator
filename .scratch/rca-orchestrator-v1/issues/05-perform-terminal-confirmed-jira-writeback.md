# 05: Perform terminal-confirmed Jira writeback

**What to build:** A demo operator can decide `[y/N]` after an Evaluation Result. The CLI persists the Writeback Decision and uses Jira Intelligence to create the allowed idempotent Jira Status Comment and, for a passed result, attach the Markdown RCA Report.

**Blocked by:** 04 — Run live Copilot analysis and independent evaluation.

**Status:** completed

- [x] A declined decision produces no Jira mutation.
- [x] `needs_evidence` and `escalated` outcomes write only a clearly labelled Status Comment after confirmation.
- [x] A passed result posts one provenance-rich comment and uploads only the Markdown RCA Report using Jira Intelligence idempotency.
