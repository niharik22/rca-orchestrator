# Keep model runners analysis-only

Model runners receive only the generated bounded Evidence Package and return structured analysis. They receive no workspace paths, filesystem or shell capability, Jira credentials, or mutation authority; deterministic RCA code owns all I/O, validation, report writing, and controlled Jira writeback.
