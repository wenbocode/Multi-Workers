# Timi Mixed-Protocol Provider Design

## Goal

Make Pi and Multi-Workers access Timi models through the protocol appropriate to each model while leaving standalone Codex workers on Codex's existing, working Timi provider path.

## Requirements

- Keep one built-in provider ID: `timi`.
- Route model IDs beginning with `claude-` through `anthropic-messages`.
- Route every other Timi model through `openai-responses`.
- Make `timi/gpt-5.6-sol` the default Timi model in Pi.
- Treat the GPT-5.6 family as reasoning-capable models.
- Normalize empty OpenAI Responses tool descriptions before sending requests to Timi, matching the compatibility behavior of the existing Codex-side sanitizer.
- Retry retryable Timi OpenAI Responses request failures, including HTTP 429, 500, 502, 503, and 504, using Pi's provider retry mechanism. Explicit caller settings override the Timi default; otherwise the Timi Responses path uses eight retries.
- Do not route standalone `codex exec` workers through Multi-Workers' port 7002 proxy. They must continue to use Codex's own `config.toml`, TiMiAIHub provider, local sanitizer, and retry handling.
- Do not preserve the obsolete Codex 7002 behavior for compatibility.

## Architecture

### Pi Timi provider

The existing `timi` provider becomes a multi-API provider. Its model catalog contains both `anthropic-messages` and `openai-responses` models, and `createProvider` dispatches each request using `model.api`.

The provider exposes two stream implementations:

- `anthropic-messages`: the existing Anthropic implementation, used only for `claude-*` models.
- `openai-responses`: a Timi-specific wrapper around Pi's existing OpenAI Responses implementation.

The wrapper owns only Timi compatibility policy:

- supply a default of eight provider request retries when the caller does not provide `maxRetries`;
- preserve caller-provided retry and timeout settings;
- compose with the caller's `onPayload` hook by running the caller hook first, taking its replacement payload when one is returned, cloning that final JSON-compatible payload, and then applying Timi normalization;
- recursively inspect every object property named `tools` whose value is an array, including top-level and nested tool-search collections;
- replace only string descriptions whose trimmed value is empty, matching the Codex sanitizer; missing or non-string descriptions are left unchanged;
- use `Tool <name>` when `name` is a non-empty string after trimming and `Tool <index>` otherwise, where the index is zero-based within that `tools` array.

It does not reimplement OpenAI Responses serialization, streaming, error normalization, or retry classification. Those remain owned by the existing Pi API implementation.

### Cross-protocol model switching

Pi retains one normalized conversation when the user switches between Timi Claude and GPT models. Each new request serializes that history for the selected model's API. User messages, final assistant text, images, tool calls, and tool results remain available across the switch.

Thinking payloads are protocol-specific and never cross the API boundary:

- Anthropic thinking blocks and signatures are replayed only when the historical assistant message also used `anthropic-messages`.
- OpenAI Responses reasoning items and encrypted signatures are replayed only when the historical assistant message also used `openai-responses`.
- When the historical assistant API differs from the target API, thinking/reasoning blocks are omitted rather than converted to visible text. Final assistant text and tool history remain.

This rule belongs in the shared Anthropic and OpenAI Responses history converters, not in the Timi provider wrapper, so switching providers or models elsewhere cannot attempt to parse or send a foreign signature.

The wrapper distinguishes failures before and after stream establishment by observing whether the delegated stream has emitted its `start` event. Any terminal error emitted before `start` receives this diagnostic:

```text
type: "provider_retry_boundary"
details.outerRetryEligible: false
```

The shared `isRetryableAssistantError` classifier consumes this contract and returns false when the diagnostic is present. The wrapper does not need to infer whether the underlying failure was retry exhaustion, a delay-cap error, or a non-retryable request error: all pre-stream errors stop at the provider retry boundary. Errors after `start` do not receive the diagnostic and remain eligible for Pi's session-level recovery, because provider request retries cannot resume a partial stream.

The effective provider retry budget is authoritative. The default budget is eight retries, for at most nine HTTP attempts. When a caller explicitly supplies another value, including zero, that value replaces the default and a resulting pre-stream failure still opts out of the outer assistant retry layer.

### Model catalog

The Timi catalog assigns API type by model family:

- IDs starting with `claude-`: `anthropic-messages`.
- All other IDs: `openai-responses`.

The GPT-5.6 variants are marked as reasoning-capable and retain their existing context and output limits unless a verified Timi capability requires a correction. Their OpenAI Responses compatibility is explicit:

- developer role enabled;
- session affinity uses `openai-nosession`, avoiding the proxy-incompatible `session_id` header while retaining `x-client-request-id`;
- long cache retention disabled;
- strict tools, OpenAI grammar tools, deferred tool search, and explicit prompt-cache mode disabled until verified against Timi.

`packages/ai/scripts/generate-models.ts` becomes the source of the static Timi catalog and its protocol, reasoning, limits, and compatibility metadata. Running the generator must reproduce `data/timi.json`, `timi.models.ts`, `models.generated.ts`, and the manifest. Generated files are never edited directly.

### Multi-Workers routing

Multi-Workers treats Pi and Codex as different integration boundaries.

For a Pi worker using Timi:

```text
pi worker
  -> Pi built-in provider timi
  -> openai-responses for gpt-5.6-sol
  -> Timi endpoint
```

The `_workers.parallel` entry must set `cli=pi` and `provider=timi`. The launcher then executes:

```text
pi --provider timi --model gpt-5.6-sol -p <task>
```

An empty provider retains the existing Pi default and port-7001 behavior; it does not silently select Timi. A Pi entry with `provider=timi` bypasses the port-7001 proxy, inherits `TIMI_API_KEY` and optional `TIMI_BASE_URL` from the `mw serve` environment, and relies on Pi's built-in provider authentication.

For a standalone Codex worker:

```text
codex exec -m gpt-5.6-sol
  -> Codex user config model_provider=TiMiAIHub
  -> Codex local sanitizer on port 39875
  -> Timi endpoint
```

The launcher must remove inherited `OPENAI_BASE_URL` and `OPENAI_API_KEY` from a Codex child's environment, must not require either value, and must not select port 7002 for `cli=codex`. It executes `codex exec -m gpt-5.6-sol <task>`. Empty provider and `provider=codex` are accepted for Codex entries; any other provider value is rejected as a configuration error. Provider endpoint, authorization, sanitization, and retry behavior remain controlled by Codex.

The obsolete Codex proxy instance on port 7002 is removed from the Multi-Workers service lifecycle and public interface. The removal covers `mw.py` arguments and process wiring, `launcher.py` overrides and environment construction, `proxy_multi.py`, `providers.json`, `smoke_test.sh`, `dispatch-table.md`, and affected Agentic acceptance/evidence documents. Pi, Claude CLI, and optional DeepSeek proxy behavior remain unchanged except where Pi explicitly selects the built-in `timi` provider.

## Configuration and credentials

Pi's Timi provider continues to resolve `TIMI_API_KEY` through the existing provider authentication system and uses `TIMI_BASE_URL` when set. Its default base URL remains the Timi LLM proxy endpoint.

Codex credentials remain in Codex configuration and are not copied into worker environment variables by Multi-Workers.

No credential values are logged or embedded in generated model metadata.

## Error handling

- Retryable HTTP failures before a stream is established use the shared provider retry classifier and exponential backoff, with at most nine total HTTP attempts under the default Timi policy. Caller-supplied provider retry limits define the complete pre-stream retry budget.
- Caller cancellation aborts retry sleep and the active request.
- Retry delays that exceed Pi's configured maximum remain terminal and opt out of the outer assistant retry layer.
- Errors after streaming has begun are surfaced to Pi's agent/session retry layer; the provider wrapper does not attempt to splice or replay a partial SSE stream.
- Non-retryable authentication, validation, and malformed-request errors are returned immediately.
- Tool-description normalization must not mutate the conversation context or tool definitions stored by the agent; it operates on the outgoing payload.

## Testing

### Provider tests

- Verify `claude-*` Timi models use `anthropic-messages`.
- Verify every non-Claude Timi model uses `openai-responses`.
- Verify `gpt-5.6-sol` is reasoning-capable and is Pi's default Timi model.
- Verify the provider dispatches both API types without a missing-implementation error.
- Verify empty and whitespace-only tool descriptions are normalized in nested and top-level Responses tool collections.
- Verify non-empty descriptions are unchanged.
- Verify the Timi Responses wrapper supplies eight retries only when the caller does not specify a value.
- Verify an explicit caller retry value, including zero, is preserved.
- Verify a retryable 502 is retried and a non-retryable 400 is not.
- Verify every pre-stream terminal error carries `provider_retry_boundary` with `outerRetryEligible: false` and opts out of the shared outer assistant retry classifier.
- Verify explicit provider retry budgets, including zero, remain authoritative and do not fall through to outer retries.
- Verify a partial-stream failure remains eligible for the outer assistant retry layer.
- Verify caller `onPayload` mutation and replacement returns are preserved before normalization.
- Verify the outgoing payload is cloned and caller-owned objects are not mutated.
- Verify missing/non-string descriptions and non-empty descriptions are unchanged.
- Verify fallback indexing and whitespace-only tool names.
- Verify the explicit OpenAI Responses compatibility flags for non-Claude Timi models.
- Verify the model generator reproduces every Timi model with the required prefix-based API classification.
- Verify Anthropic-to-Responses history conversion omits Anthropic thinking signatures while preserving final text and tool history.
- Verify Responses-to-Anthropic history conversion omits Responses reasoning signatures while preserving final text and tool history.
- Verify same-API history continues to replay valid thinking/reasoning signatures.

### Multi-Workers tests

- Verify a Codex worker command includes `-m gpt-5.6-sol`.
- Verify the Codex worker environment removes parent `OPENAI_BASE_URL` and `OPENAI_API_KEY` values and succeeds when no OpenAI API key is configured.
- Verify empty/`codex` Codex provider values are accepted and other values are rejected.
- Verify `cli=pi, provider=timi` produces the explicit Pi provider/model command and inherits Timi configuration.
- Verify an empty Pi provider retains the existing port-7001 path.
- Verify service startup and all public CLI/documentation surfaces no longer start, accept, or report a Codex port-7002 proxy.

### Validation

- Run every modified test file directly.
- Run `npm run check` after code changes and resolve all reported errors, warnings, and infos.
- Do not run the full test suite, `npm test`, or `npm run build` unless explicitly requested.

## Non-goals

- Replacing Codex's existing Timi configuration or sanitizer.
- Sharing the Codex port-39875 process with Pi.
- Adding a second `timi-responses` provider ID.
- Implementing custom SSE resume or partial-stream replay inside the Timi provider.
- Changing Claude model behavior beyond retaining the existing Anthropic protocol.
