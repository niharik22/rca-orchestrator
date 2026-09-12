# Keep blocked runs distinct from evaluation outcomes

Jira collection and KB-access failures create a Blocked Run before any model call; they may offer a terminal-confirmed Jira status comment when Jira collection succeeded. Evaluated drafts instead use `passed`, `needs_evidence`, or `escalated`, and Copilot CLI failures are surfaced rather than silently replaced by fixture output.
