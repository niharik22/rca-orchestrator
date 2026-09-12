# 01: Fixture RCA Run from CLI

**What to build:** A demo operator can run and inspect a deterministic Fixture Runner RCA Run from the CLI. The run persists its Workflow State and local RCA Run record, renders the fixed local Markdown RCA Report, and can Resume without live Jira, KB, or Copilot dependencies.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] `rca-run`, `rca-show`, and Resume produce observable local RCA Run behavior through the single RcaWorkflow seam.
- [ ] Legal and illegal Workflow State transitions are persisted and verified with fixture-driven tests.
- [ ] The fixed Markdown RCA Report and local provenance record are created without any Jira mutation.
