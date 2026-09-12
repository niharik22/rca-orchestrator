# Use a fresh evaluator invocation

After the coordinator produces a draft, V1 invokes Copilot CLI again with a distinct evaluator prompt, the draft, and its cited evidence. This second invocation does not receive the coordinator's hidden reasoning, providing an independent check before determining the Evaluation Result.
