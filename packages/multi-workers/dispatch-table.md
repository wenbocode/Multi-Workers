# Dispatch Table — agent-team-loop Worker Routing

Maps task types and use cases to the worker CLI + provider.

| Task Type | CLI | Provider | Port | API Key Env | Notes |
|-----------|-----|----------|------|-------------|-------|
| General coding / AgenticTask execution | pi | claude | 7001 | ANTHROPIC_API_KEY | Default for pi workers |
| Goal elicitation dialogue | pi | claude | 7001 | ANTHROPIC_API_KEY | PM uses pi for goal.md creation |
| General coding / AgenticTask execution (Pi/Timi) | pi | timi | - | TIMI_API_KEY | Direct Timi credentials; GPT-5.6-sol default; no proxy |
| Code completion / refactoring | codex | codex | - | Codex config | Uses Codex TiMiAIHub provider (user configuration) |
| Long-text analysis (>200k tokens) | claude | claude-cli | 7003 | ANTHROPIC_AUTH_TOKEN | claude binary with oauth token |
| Code review / multi-file audit | claude | claude-cli | 7003 | ANTHROPIC_AUTH_TOKEN | claude binary with oauth token |
| Low-cost summarisation / routing | pi | deepseek | 7004 | DEEPSEEK_API_KEY | Optional: override provider |

## Routing Logic

1. `_workers.parallel` `Cli` column selects the binary: `pi` → pi CLI, `codex` → codex binary, `claude` → claude binary.
2. `Provider` column (optional) overrides the default provider for that CLI.
3. Default mapping: `cli=pi` → `claude` provider (port 7001); `cli=claude` → `claude-cli` provider (port 7003).
4. All worker subprocesses receive a `BASE_URL=http://localhost:{port}` pointing to the local proxy.

## AC-014 Verification

```
grep -c "| pi |" dispatch-table.md        # >= 2
grep -c "| codex |" dispatch-table.md     # >= 1
grep -c "| claude |" dispatch-table.md    # >= 2
```
