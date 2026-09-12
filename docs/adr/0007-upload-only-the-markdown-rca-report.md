# Upload only the Markdown RCA Report to Jira

The RCA Report Markdown file is the sole RCA artifact written to Jira Intelligence's `analysis/` directory because its attachment endpoint uploads all eligible files there. Run records, JSON reports, raw model output, and evaluation details remain in the RCA project's local outputs, and Resume reuses that recorded state.
