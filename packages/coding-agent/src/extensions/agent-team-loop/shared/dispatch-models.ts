// Dispatch model config (mw-dispatch-models): the shared model-value
// namespace + the main-window side of the chain.
//
// A model value is "prefix/model-id" (e.g. timi/glm-5.3). The prefix is the
// user-facing serving-channel namespace, deliberately NOT raw pi provider ids:
//
//   timi     -> pi provider "timi"          (direct)
//   claude   -> pi provider "anthropic"     (direct, no mw proxy)
//   codex    -> pi provider "openai-codex"  (codex' own config)
//   deepseek -> pi provider "deepseek"      (direct, no mw proxy)
//   codex_cli / claude_cli                  (CLI executors, spawn-side only)
//
// The Python side owns resolution (mw_common.MODEL_PREFIX_TO_PI_PROVIDER +
// launcher._effective_entry): task.md `model:` > .mw/dispatch.yml role >
// .mw/window-model > per-cli default. This module only (a) records the
// current window model into .mw/window-model so unset roles inherit it, and
// (b) applies a configured `main` role to the PM window when the user has not
// made an explicit model choice. The maps here mirror mw_common.py — keep
// both sides in sync.

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { Model } from "@earendil-works/pi-ai";
import type { ExtensionAPI, ExtensionContext } from "../../../core/extensions/types.ts";
/** pi provider id -> user-facing prefix (mirror of the Python-side map). */
export const PROVIDER_ID_TO_PREFIX: Record<string, string> = {
	timi: "timi",
	anthropic: "claude",
	"openai-codex": "codex",
	deepseek: "deepseek",
};

/** User-facing prefix -> pi provider id (inverse of PROVIDER_ID_TO_PREFIX). */
export const PREFIX_TO_PROVIDER_ID: Record<string, string> = Object.fromEntries(
	Object.entries(PROVIDER_ID_TO_PREFIX).map(([provider, prefix]) => [prefix, provider]),
);

/** (prefix, modelId) of a "prefix/model-id" value; ("", value) when bare. */
export function parseModelValue(value: string): { prefix: string; modelId: string } {
	const idx = value.indexOf("/");
	if (idx < 0) return { prefix: "", modelId: value.trim() };
	return { prefix: value.slice(0, idx).trim(), modelId: value.slice(idx + 1).trim() };
}

export function windowModelPath(cwd: string): string {
	return path.join(cwd, ".mw", "window-model");
}

function dispatchYmlPath(cwd: string): string {
	return path.join(cwd, ".mw", "dispatch.yml");
}

function isFrameworkProject(cwd: string): boolean {
	// Gate on the mw init marker: the extension is globally installed, so a
	// bare value must never create .mw/ dirs in unrelated projects.
	return fs.existsSync(path.join(cwd, ".agenticdoc"));
}

/** Record the current window model for the launcher's inheritance chain
 * (.mw/window-model, "prefix/model-id", last writer wins). No-op outside
 * framework projects or for providers outside the mapped namespace (an
 * unmapped provider would be an inert value on the Python side anyway). */
export function recordWindowModel(cwd: string, model: Model<any> | undefined): void {
	if (!model || !isFrameworkProject(cwd)) return;
	const prefix = PROVIDER_ID_TO_PREFIX[model.provider];
	if (!prefix) return;
	try {
		fs.mkdirSync(path.join(cwd, ".mw"), { recursive: true });
		fs.writeFileSync(windowModelPath(cwd), `${prefix}/${model.id}\n`, "utf8");
	} catch {
		// Best-effort telemetry: a failed write only means workers fall back
		// to the per-cli default.
	}
}

/** The configured `main` role from .mw/dispatch.yml, or null.
 * Hand-parses the narrow mw-model-owned format (flat `models:` mapping
 * written by `mw model set`) — the file is machine-written, so a strict
 * reader keeps the bundle yaml-free. */
export function readMainModelConfig(cwd: string): string | null {
	let text: string;
	try {
		text = fs.readFileSync(dispatchYmlPath(cwd), "utf8");
	} catch {
		return null;
	}
	let inModels = false;
	for (const raw of text.split(/\r?\n/)) {
		const line = raw.trimEnd();
		if (/^models:\s*$/.test(line)) {
			inModels = true;
			continue;
		}
		if (inModels) {
			// End of the models block: a new top-level key (no indentation).
			if (line && !/^\s/.test(line)) break;
			const m = /^\s+main:\s*(\S+)\s*$/.exec(line);
			if (m) return m[1];
		}
	}
	return null;
}

/** pi's settings.json defaultModel, when the user pinned one (agent dir
 * resolution mirrors core getAgentDir(); the bundle must stay self-contained
 * and not import core config). */
export function settingsDefaultModel(): string | null {
	const base = process.env.PI_CODING_AGENT_DIR ?? path.join(os.homedir(), ".pi", "agent");
	try {
		const settings = JSON.parse(fs.readFileSync(path.join(base, "settings.json"), "utf8")) as {
			defaultModel?: unknown;
		};
		return typeof settings.defaultModel === "string" && settings.defaultModel ? settings.defaultModel : null;
	} catch {
		return null;
	}
}

/** Did the user launch pi with an explicit --model flag? */
export function hasCliModelFlag(): boolean {
	return process.argv.some((a) => a === "--model" || a.startsWith("--model="));
}

/** Apply the configured `main` model to this window. Explicit user choices
 * always win: a --model flag or a settings.json defaultModel skips the
 * application entirely. */
export async function applyMainModelConfig(pi: ExtensionAPI, ctx: ExtensionContext): Promise<void> {
	if (hasCliModelFlag() || settingsDefaultModel()) return;
	const value = readMainModelConfig(ctx.cwd);
	if (!value) return;
	const { prefix, modelId } = parseModelValue(value);
	if (!prefix || !modelId) return;
	const provider = PREFIX_TO_PROVIDER_ID[prefix];
	if (!provider) return;
	const model = ctx.modelRegistry.find(provider, modelId);
	if (!model) {
		ctx.ui.notify(
			`dispatch.yml main=${value} not found in the model registry — leaving the window model unchanged`,
			"error",
		);
		return;
	}
	if (ctx.model?.provider === model.provider && ctx.model?.id === model.id) return;
	const ok = await pi.setModel(model);
	if (ok) {
		ctx.ui.notify(`model set to ${value} (dispatch.yml main)`, "info");
	}
}

/** Register the main-window model hooks: record the window model on
 * session_start / model_select, and apply a configured main role once per
 * session. Only the non-worker (PM/interactive) branch calls this — worker
 * windows get their model from the launcher's --model flag and must not
 * poison the inheritance file. */
export function registerMainWindowModel(pi: ExtensionAPI): void {
	pi.on("session_start", (_event, ctx) => {
		recordWindowModel(ctx.cwd, ctx.model);
		void applyMainModelConfig(pi, ctx);
	});
	pi.on("model_select", (event) => {
		recordWindowModel(process.cwd(), event.model);
	});
}
