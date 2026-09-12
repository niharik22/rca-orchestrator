# Use two AI roles and a deterministic workflow

V1 has exactly two AI roles: RCA Analyst and Evaluator. The RCA workflow is the single deep module that owns the persisted state machine and invokes those roles in order; Jira collection, KB retrieval, storage, terminal confirmation, report writing, and Jira writeback remain deterministic adapters rather than agents.
