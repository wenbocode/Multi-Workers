import type { Model } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionContext } from "../../../core/extensions/types.ts";
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
/** Record the current window model for the launcher's inheritance chain
 * (.mw/window-model, "prefix/model-id", last writer wins). No-op outside
 * framework projects or for providers outside the mapped namespace (an
 * unmapped provider would be an inert value on the Python side anyway). */
export declare function recordWindowModel(cwd: string, model: Model<any> | undefined): void;
/** The configured `main` role from .mw/dispatch.yml, or null.
 * Hand-parses the narrow mw-model-owned format (flat `models:` mapping
 * written by `mw model set`) — the file is machine-written, so a strict
 * reader keeps the bundle yaml-free. */
export declare function readMainModelConfig(cwd: string): string | null;
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