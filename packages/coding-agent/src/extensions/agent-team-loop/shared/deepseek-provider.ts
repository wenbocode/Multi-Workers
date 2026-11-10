import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { Model } from "@earendil-works/pi-ai";
import { deepseekProvider } from "@earendil-works/pi-ai/providers/deepseek";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { controlRootFromTaskPath } from "./paths.ts";

/** Project config overrides user-wide defaults; workers resolve the control project. */
export function configureDeepSeek(pi: ExtensionAPI, project?: string): boolean {
	const root =
		project ?? (process.env.PI_WORKER_TASK ? controlRootFromTaskPath(process.env.PI_WORKER_TASK) : process.cwd());
	let file = "";
	let text: string | undefined;
	for (const candidate of [path.join(root, ".mw", "deepseek.json"), path.join(os.homedir(), ".mw", "deepseek.json")]) {
		try {
			text = fs.readFileSync(candidate, "utf8");
			file = candidate;
			break;
		} catch (error) {
			if (error instanceof Error && "code" in error && error.code === "ENOENT") continue;
			throw new Error(`Cannot read DeepSeek config: ${candidate}`, { cause: error });
		}
	}
	if (text === undefined) return false;
	let value: unknown;
	try {
		value = JSON.parse(text.replace(/^\uFEFF/, ""));
	} catch {
		throw new Error(`Invalid JSON in ${file}`);
	}
	if (!value || typeof value !== "object" || Array.isArray(value))
		throw new Error(`Invalid DeepSeek config object: ${file}`);
	const config = value as Record<string, unknown>;
	if (
		config.version !== 1 ||
		typeof config.baseUrl !== "string" ||
		!Array.isArray(config.models) ||
		!config.models.length ||
		Object.keys(config).some((key) => !["version", "baseUrl", "models"].includes(key)) ||
		config.models.some((id: unknown) => id !== "deepseek-flash" && id !== "deepseek-v4-pro") ||
		new Set(config.models).size !== config.models.length
	)
		throw new Error(
			`Invalid ${file}: expected version=1, baseUrl and models [deepseek-flash, deepseek-v4-pro]; store keys via DEEPSEEK_API_KEY or pi /login`,
		);
	let url: URL;
	try {
		url = new URL(config.baseUrl);
	} catch {
		throw new Error(`Invalid DeepSeek baseUrl in ${file}`);
	}
	if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) {
		throw new Error(`DeepSeek baseUrl in ${file} must be HTTPS without credentials, query or fragment`);
	}
	const models = [...deepseekProvider().getModels()];
	for (const id of config.models as string[]) {
		const template = models.find((model) => model.id === (id === "deepseek-flash" ? "deepseek-v4-flash" : id));
		if (!template) throw new Error(`Missing built-in DeepSeek template for ${id}`);
		const model: Model<"openai-completions"> = {
			...template,
			id,
			name: id === "deepseek-flash" ? "DeepSeek Flash" : "DeepSeek V4 Pro",
			input: id === "deepseek-flash" ? ["text", "image"] : ["text"],
			thinkingLevelMap: { minimal: "low", low: "low", medium: "high", high: "high", xhigh: "high", max: "max" },
		};
		const index = models.findIndex((entry) => entry.id === id);
		if (index < 0) models.push(model);
		else models[index] = model;
	}
	// Preserve the native provider's env / credential-store authentication and streaming API.
	const baseUrl = url.href.replace(/\/$/, "");
	pi.registerProvider("deepseek", { baseUrl, models: models.map((model) => ({ ...model, baseUrl })) });
	return true;
}
