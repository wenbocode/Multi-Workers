# Worker thinking level

Set thinking separately from the model in the **control project's** `.mw/dispatch.yml`:

```yaml
models:
  coding: toa/hy4
  research: toa/hy4
  vision: toa/hy4
thinking:
  default: high
  roles:
    research: "off"
```

`thinking.roles.<role>` overrides `thinking.default`. Supported worker roles are `coding`, `review`, `research`, `vision`, and `decide_prepare`. Existing task-type buckets apply: for example, `verifier` and `reviewer` use `review`, while `rag-research` uses `research`. `main` is not a worker role and is not accepted here; this configuration does not change the PM window.

Both `default` and `roles` are optional. Without a matching role or a default, MW omits `--thinking` and leaves pi's native selection unchanged. Setting this project's default to `high` does not change other projects or global pi settings.

## Levels and validation

Values must be strings: `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max`. **Quote `"off"`**: YAML otherwise parses it as boolean false. Unknown fields, unknown roles, nulls, booleans and unsupported level names invalidate the whole thinking block. An unreadable or malformed configuration emits a launcher warning and omits the thinking override; it does not inject an invalid CLI argument or silently substitute `high`.

MW passes the requested level using pi's native `--thinking LEVEL`. Model-specific capability mapping and clamping remain pi's responsibility; a supported configuration level is not a promise that every model supports it. `toa/hy4` currently supports `off` and `high`. The explicit flag takes precedence over a thinking suffix on a model pattern, following pi's CLI behavior. This does not change the configured model or provider.

## When settings take effect

- Only **new pi Worker processes** consume the setting. Existing workers and the PM window are unchanged.
- The launcher reads the control project's configuration on each spawn, including retries and model-fallback spawns. A game or partition working directory is not the configuration root.
- Native `codex` and `claude` CLI workers do not receive pi's `--thinking` argument. A pi worker using the Codex provider is still a pi worker and receives it.
- Launcher output records `thinking` and `thinking-source`; dry-run output includes the same configured argument.
- Once the launcher code is loaded, editing this YAML applies at the next spawn without a restart. **An already-running service with older Python code needs a separately authorized `/mw restart` first.** Writing configuration alone cannot update code held in that process. No TypeScript bundle rebuild is needed for this feature.

There is no new `dispatch_worker` parameter or `mw model` thinking subcommand. Edit this project-local YAML; existing model configuration commands preserve the top-level thinking block.

## Offline checks

From the repository root:

```text
python -m pytest -q packages/multi-workers/test_worker_thinking.py packages/multi-workers/test_launcher_thinking.py
```

These tests use temporary projects and fake subprocesses, not real provider calls.
