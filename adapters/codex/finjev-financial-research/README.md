# FinJev Financial Research plugin

This local Codex plugin implements one bounded workflow:

```text
Codex retrieves financial data
  -> FinJev/Jev returns structured judgments
    -> Codex writes the final cited natural-language analysis
```

Install the Python backend from the repository root using `uv tool install .`.
The adapter launches `finjev` from PATH. Provide `TYPESAFE_API_KEY` or
`FINJEV_API_KEY_FILE` through the MCP client's environment. No credentials are
included in this adapter. If the desktop client does not inherit your PATH,
configure the absolute path to the installed `finjev` executable locally.

This is the Codex adapter source. The previous local installation was verified;
this portable PATH-based configuration still requires validation on the target
machine. Other Agent adapters and the shared MCP workflow prompt are pending.

The plugin does not provide a separate search engine. Codex uses its available
web, browser, file, or connected-data capabilities for retrieval. FinJev provides
source evaluation, evidence verification, event classification, materiality
judgment, result reranking, and research continuation decisions.

All FinJev results are advisory. Codex owns the final prose and must preserve
`VERIFY`, `ABSTAIN`, and `HUMAN_REVIEW` limitations.
