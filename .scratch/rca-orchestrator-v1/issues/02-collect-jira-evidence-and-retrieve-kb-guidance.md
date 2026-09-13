# 02: Collect Jira evidence and retrieve cited KB guidance

**What to build:** A demo operator can run a fixture-backed RCA analysis for a Jira issue using Jira Intelligence to create or reuse a Collection Run and the configured PolicyCenter KB to retrieve manifest-first cited KB Passages. The resulting Evidence Package and report make Jira observations, reported claims, and missing evidence visible.

**Blocked by:** 01 — Fixture RCA Run from CLI.

**Status:** completed

- [x] The RCA Run records the linked immutable Collection Run and uses no direct Jira REST calls.
- [x] KB retrieval stays within the configured root, starts with the manifest, and selects no more than three domains and six KB Passages.
- [x] Optional Product Version and unverified version applicability are visible in provenance and the report.
