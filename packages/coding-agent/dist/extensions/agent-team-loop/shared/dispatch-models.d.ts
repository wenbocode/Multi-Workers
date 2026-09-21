import type { Model } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionContext } from "../../../core/extensions/types.ts";
import type { ModelRegistry } from "../../../core/model-registry.ts";
/** pi provider id -> user-facing prefix (mirror of the Python-side map). */
export declare const PROVIDER_ID_TO_PREFIX: Record<string, string>;
/** User-facing prefix -> pi provider id (inverse of PROVIDER_ID_TO_PREFIX). */
export declare const PREFIX_TO_PROVIDER_ID: Record<string, string>;
/** (prefix, modelId) of a "prefix/model-id" value; ("", value) when bare. */
export declare function parseModelValue(value: string): {
    prefix: string;
    modelId: string;
};
export declare function windowModelPath(cwd: string): string;
/** Task type -> dispatch role (mirror of mw_common.TASK_TYPE_TO_ROLE). An
 * unknown type falls back to `coding`, matching resolve_dispatch_model's
 * `.get(task_type, "coding")`. The Python side owns the actual resolution;
 * this map only selects which configured role a dispatch must compare
 * against and justify itself for (keep both sides in sync). */
export declare const DISPATCH_ROLE_BY_TYPE: Record<string, string>;
/** The role-level types the PM dispatch surface accepts (`type:` in task.md).
 * Every entry has a tool allowlist entry in worker-mode.ts. */
export declare const DISPATCHABLE_TYPES: readonly ["coding", "review", "research"];
/** Role for a declared task type (unknown -> coding, same as the Python chain). */
export declare function roleForTaskType(taskType: string): string;
/** Record the current window model for the launcher's inheritance chain
 * (.mw/window-model, "prefix/model-id", last writer wins). No-op outside
 * framework projects or for providers outside the mapped namespace (an
 * unmapped provider would be an inert value on the Python side anyway). */
export declare function recordWindowModel(cwd: string, model: Model<any> | undefined): void;
/** One role's value out of .mw/dispatch.yml, or null.
 * Hand-parses the narrow mw-model-owned format (flat `models:` mapping
 * written by `mw model set`) — the file is machine-written, so a strict
 * reader keeps the bundle yaml-free. Missing file, missing role, and a role
 * outside the `models:` block all return null (the chain just falls through). */
export declare function readRoleModel(cwd: string, role: string): string | null;
/** The configured `main` role from .mw/dispatch.yml, or null. */
export declare function readMainModelConfig(cwd: string): string | null;
/** Result of dispatch-time model-value validation. */
export interface ModelValidation {
    ok: boolean;
    message: string;
}
/** Validate one dispatch model value against pi's model registry (design D-004).
 *
 * Only pi tasks with a known provider prefix (or a bare id) are checked: the
 * CLI executors (codex/claude) and the *_cli prefixes own their catalogs. A
 * missing registry, a provider pi does not know at all, or an empty value are
 * all `ok` — route/credential checks own those failures, and this gate must
 * never invent one. A value that IS resolvable-but-wrong (e.g. timi/gpt-5.6.sol)
 * is refused: pi would otherwise silently treat it as a custom model id
 * (core/model-resolver.ts buildFallbackModel) and issue requests with it. */
export declare function validateModelValue(registry: ModelRegistry | undefined, cli: string, taskProvider: string, value: string): ModelValidation;
/** pi's settings.json defaultModel, when the user pinned one (agent dir
 * resolution mirrors core getAgentDir(); the bundle must stay self-contained
 * and not import core config). */
export declare function settingsDefaultModel(): string | null;
/** Did the user launch pi with an explicit --model flag? */
export declare function hasCliModelFlag(): boolean;
/** Apply the configured `main` model to this window. Explicit user choices
 * always win: a --model flag or a settings.json defaultModel skips the
 * application entirely. */
export declare function applyMainModelConfig(pi: ExtensionAPI, ctx: ExtensionContext): Promise<void>;
/** Register the main-window model hooks: record the window model on
 * session_start / model_select, and apply a configured main role once per
 * session. Only the non-worker (PM/interactive) branch calls this — worker
 * windows get their model from the launcher's --model flag and must not
 * poison the inheritance file. */
export declare function registerMainWindowModel(pi: ExtensionAPI): void;
//# sourceMappingURL=dispatch-models.d.ts.map