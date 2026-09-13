# 06: Harden Resume and work-laptop demo flow

**What to build:** A demo operator can reliably run, inspect, Resume, and demonstrate the complete RCA workflow on Mac or Windows using the three sibling projects and clear preflight/setup guidance.

**Blocked by:** 03 — Add bounded Attachment Evidence; 05 — Perform terminal-confirmed Jira writeback.

**Status:** completed

- [x] Resume preserves completed external work and never repeats an avoidable Collection Run, model invocation, or Jira mutation.
- [x] Adversarial workflow tests cover Blocked Runs, malformed model output, missing evidence, declined writeback, and idempotent retry behavior without live accounts.
- [x] Setup and demo guidance explains the sibling-project configuration, Copilot authentication prerequisite, fixture fallback, and Windows-compatible execution path.
