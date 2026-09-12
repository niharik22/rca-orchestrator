# Use bounded deterministic KB selection in V1

The PolicyCenter adapter begins with the KB manifest, then selects at most three domains and six cited passages from Jira metadata and recognized error names. Product Version is optional, and no model hypothesis may expand this first-pass retrieval in V1; this keeps RCA evidence bounded, reproducible, and explicit about unverified KB applicability.
