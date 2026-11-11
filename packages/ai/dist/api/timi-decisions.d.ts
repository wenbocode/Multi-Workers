/**
 * timi-decisions API implementation.
 *
 * The timiai gateway's `POST /v1/decisions` endpoint (see `jev接入.md`) answers a
 * set of structured questions about the `state` supplied with them. It is not a
 * chat endpoint: there is no stream, no box, and no free-form text output — only
 * per-question `noul` / `choice` / `score` answers.
 * pi's stream contract is chat-shaped, so this module defines one explicit
 * input convention instead of inventing a lossy mapping:
 *
 * - The last user message text must be a JSON object carrying `state` and
 *   `questions`, e.g. `{"state": "I was charged twice", "questions": {...}}`.
 *   Anything else (plain prose, non-JSON, a JSON object missing either key)
 *   fails fast with an `error` event before any request is made.
 * - The request is a single `POST <baseUrl>/v1/decisions` with only
 *   `{ model, state, questions }` in the body; no chat fields (messages,
 *   tools, stream, sampling parameters) are forwarded. Authentication is the
 *   platform API key sent verbatim in `Authorization` (no `Bearer` prefix).
 * - The one-shot JSON response's `answers` object becomes the assistant text
 *   as compact JSON, `usage.input_tokens`/`usage.output_tokens` become the
 *   assistant message usage, and the upstream `model` names the assistant
 *   message model.
 *
 * 429/5xx responses are surfaced as errors without client-side retries.
 */
import type { ProviderStreams } from "../types.ts";
export declare function timiDecisionsApi(): ProviderStreams;
//# sourceMappingURL=timi-decisions.d.ts.map