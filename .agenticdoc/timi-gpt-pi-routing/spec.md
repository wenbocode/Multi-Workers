# Spec: Timi GPT Pi Routing

> Key: `timi-gpt-pi-routing`
> Created: 2026-08-14
> Status: approved

## 1. Goal

Make Pi workers use the Timi protocol required by each model, keep standalone Codex workers on their existing user-level TiMiAIHub configuration, and ensure Multi-Workers does not report a healthy service after a managed child process has exited.

## 2. Scope

- Add mixed Anthropic/OpenAI Responses dispatch to Pi's built-in `timi` provider.
- Make `timi/gpt-5.6-sol` the explicit model for Multi-Workers Pi tasks selecting `provider=timi`.
- Preserve the existing empty-provider Pi path through port 7001.
- Keep standalone Codex workers independent of Multi-Workers' proxy ports.
- Remove obsolete Codex port-7002 behavior.
- Make `mw serve` fail and clean up when a managed child exits unexpectedly.
- Regenerate and build runtime artifacts used by the globally linked Pi CLI.

Out of scope:

- Changing the user's Codex `config.toml` or local port-39875 sanitizer.
- Adding a second Timi provider ID.
- Preserving the obsolete port-7002 Codex proxy for compatibility.

## 3. Constraints

- TypeScript production changes use erasable syntax and top-level imports only.
- Generated model files are produced through `packages/ai/scripts/generate-models.ts`.
- Credentials remain environment/config driven and are never logged.
- Existing unrelated worktree changes must be preserved.
- Tests use faux/local transports; no paid provider calls.

## 4. Acceptance Criteria

AC-001: Given the complete static Timi model list, generation assigns `anthropic-messages` to every ID beginning with `claude-`, `kimi-`, `glm-`, or `deepseek-`, and to `hy3`; assigns `openai-responses` to every ID beginning with `gpt-`; and assigns `reasoning=true` to `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5-r3`, and `deepseek-v4-pro-r1`.

AC-002: Given `timiProvider()`, its API implementation map contains both `anthropic-messages` and `openai-responses`, and dispatching one model from each family does not produce a missing-implementation error.

AC-003: Given Pi resolves a default model for provider `timi` without an explicit model, it selects exactly `gpt-5.6-sol`.

AC-004: Given a JSON-compatible Responses payload, normalization removes only object properties named `store`, recursively visits every object property named `tools` whose value is an array, changes only string descriptions whose trimmed value is empty to `Tool <trimmed-name>` or zero-based `Tool <index>`, runs after the caller `onPayload` mutation/replacement, and leaves the caller-owned payload unchanged.

AC-005: Given Timi Responses options, an omitted `maxRetries` becomes `8`, an explicit value including `0` is preserved, retryable HTTP 429/500/502/503/504 failures use the shared provider retry mechanism, cancellation aborts the active request or retry delay, delay-cap failures remain terminal, every terminal error before the delegated stream emits `start` has `provider_retry_boundary.outerRetryEligible=false`, and an error after `start` remains outer-retry-eligible.

AC-006: Given conversation history crosses between `anthropic-messages` and `openai-responses`, target serialization preserves user content, final assistant text, images, tool calls, and tool results while omitting source-protocol thinking/reasoning signatures; same-protocol history continues to replay valid signatures.

AC-007: Given any `gpt-*` Timi model (`openai-responses`), its Responses compatibility equals: developer role enabled, session affinity `openai-nosession`, long cache retention disabled, strict mode disabled, OpenAI grammar tools disabled, tool search disabled, and explicit prompt-cache mode disabled. Given any non-`gpt-*` Timi model (`anthropic-messages`), its Anthropic compatibility equals: long cache retention disabled, eager tool input streaming disabled, cache control on tools disabled.

AC-008: Given a worker entry with `cli=pi` and `provider=timi`, the launcher command equals `pi --provider timi --model gpt-5.6-sol -p <task>`, the child inherits existing `TIMI_API_KEY` and optional `TIMI_BASE_URL`, and the launcher injects no localhost base URL or unrelated provider credential.

AC-009: Given a worker entry with `cli=pi` and an empty provider, the launcher command remains `pi -p <task>` and the child receives `ANTHROPIC_BASE_URL=http://localhost:7001` plus the configured `ANTHROPIC_API_KEY` only.

AC-010: Given a Codex worker with an empty provider or `provider=codex`, the launcher command equals `codex exec -m gpt-5.6-sol <task>`, removes inherited `OPENAI_BASE_URL` and `OPENAI_API_KEY`, and requires neither variable; any other provider value raises a configuration error before spawn.

AC-011: Given the Multi-Workers public surfaces `providers.json`, `launcher.py`, `proxy_multi.py`, `mw.py`, `smoke_test.sh`, and `dispatch-table.md`, none starts, configures, accepts a CLI option for, or documents a Codex proxy on port 7002.

AC-012: Given `mw serve`, a proxy or launcher failure during startup or runtime, including simultaneous child exits, causes nonzero service exit; a cross-platform `.mw/mw.stop` request, foreground `KeyboardInterrupt`, or POSIX `SIGTERM` causes intentional zero exit; service cleanup calls terminate, waits up to 10 seconds, force-kills managed children still alive, removes PID/stop files, and makes `mw status` return not running. If `mw stop` observes the parent still alive after 30 seconds, it returns nonzero without force-terminating the parent or bypassing its child cleanup.

AC-013: Given generation and the user-approved `npm run build` complete, `packages/ai/dist/providers/data/timi.json` classifies every model as in AC-001, `packages/ai/dist/providers/timi.js` contains both API implementations, `pi --list-models timi --offline` reports `yes` in the thinking column for all GPT-5.6 variants and `deepseek-v4-pro-r1`, and every non-GPT model routes to `/v1/messages` (not `/responses`).

AC-014: Given all modified tests, each direct command exits zero; `npm run check` exits zero with no errors, warnings, or infos; and the explicitly user-approved `npm run build` exits zero.

AC-015: Given dry-run, service, provider, generation, test, and build output, no API key, bearer token, or credential value is printed or written into generated model metadata.

## 5. Reusable Assets

- Existing Timi model generator and provider registration.
- Existing OpenAI Responses transport, retry classifier, and faux-provider testing infrastructure.
- Existing Multi-Workers launcher, service manager, and L1 test script.
- Existing design baseline at `docs/superpowers/specs/2026-08-13-timi-mixed-provider-design.md`.

## 6. Pitfalls to Avoid

- Do not treat source changes as active until linked CLI `dist` artifacts are regenerated.
- Do not route GPT models through the Anthropic Messages adapter merely because other Timi models tolerate it.
- Do not let `mw status` rely on a parent PID that remains alive after child failure.
- Do not copy Codex credentials into Multi-Workers environment variables.
