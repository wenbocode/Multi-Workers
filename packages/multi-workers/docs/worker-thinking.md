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

## Commands

Terminal commands (run from the control project, or append `--project <control-dir>`):

```text
mw thinking show
mw thinking set default high
mw thinking set research low
mw thinking set review xhigh
mw thinking set coding off
mw thinking clear research
mw thinking clear default
mw thinking clear all
```

If `mw` is not on PATH, use `python <repo>/packages/multi-workers/mw.py thinking ...` instead. The equivalent window commands are:

```text
/mw thinking show
/mw thinking set default high
/mw thinking set research low
/mw thinking clear research
/mw thinking clear all
```

Bare `mw thinking` or `/mw thinking` means `show`. The window always uses its **control project**, even when workers run in a game or partition workspace. `show` reports the configuration path, configured default and all five worker roles' effective values and sources (`config:<role>`, `config:default`, or `unset` for pi's native selection), without creating or changing files.

`set` accepts `default` or one supported worker role and one level from the list below. `clear <role>` removes only that override, restoring inheritance from the default; `clear default` keeps role overrides; `clear all` removes the entire thinking block, restoring native selection for every role. Clearing an absent field does not rewrite the file. `main` and task-type aliases such as `verifier` are not command targets: configure their worker role instead.

Writes validate the existing YAML and thinking block, preserve unrelated configuration **data** (including models, fallback chains and RAG), then replace the file atomically. Comments, key order and formatting are not preserved. Invalid input, malformed configuration, or a read/write error fails without replacing the original file; even `clear all` refuses a malformed configuration. The command serializes `off` as a string, so no manual quoting is needed in the command. Atomic replacement prevents partial files, but does not coordinate simultaneous read-modify-write operations with other configuration commands; avoid concurrent edits.

## Levels and validation

Values must be strings: `off`, `minimal`, `low`, `medium`, `high`, `xhigh`, or `max`. **Quote `"off"`**: YAML otherwise parses it as boolean false. Unknown fields, unknown roles, nulls, booleans and unsupported level names invalidate the whole thinking block. An unreadable or malformed configuration emits a launcher warning and omits the thinking override; it does not inject an invalid CLI argument or silently substitute `high`.

MW passes the requested level using pi's native `--thinking LEVEL`. Model-specific capability mapping and clamping remain pi's responsibility; a supported configuration level is not a promise that every model supports it. `toa/hy4` currently supports `off` and `high`. The explicit flag takes precedence over a thinking suffix on a model pattern, following pi's CLI behavior. This does not change the configured model or provider.

## When settings take effect

- Only **new pi Worker processes** consume the setting. Existing workers and the PM window are unchanged.
- The launcher reads the control project's configuration on each spawn, including retries and model-fallback spawns. A game or partition working directory is not the configuration root.
- Native `codex` and `claude` CLI workers do not receive pi's `--thinking` argument. A pi worker using the Codex provider is still a pi worker and receives it.
- Launcher output records `thinking` and `thinking-source`; dry-run output includes the same configured argument.
- Once the launcher code is loaded, configuration changes apply at the next spawn without a restart. **An already-running service with older Python code needs `/mw restart` first.** Writing configuration alone cannot update code held in that process.
- The terminal command runs the Python source directly. The new `/mw thinking` window entry also requires an extension bundle containing it: use the project's normal build/install procedure and reload or restart pi as required by that installation. A serve restart alone does **not** update the window extension. No build or install is performed by `thinking` itself.

There is no new `dispatch_worker` parameter or `mw model` thinking subcommand. Thinking remains independent of model configuration; existing model configuration commands preserve its top-level YAML block.

## Offline checks

From the repository root:

```text
python -m pytest -q packages/multi-workers/test_thinking_cli.py packages/multi-workers/test_worker_thinking.py packages/multi-workers/test_launcher_thinking.py
```

From `packages/coding-agent`:

```text
node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-thinking.test.ts
```

These tests use temporary projects and fake subprocesses, not real provider calls.
