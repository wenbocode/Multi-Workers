import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { openaiCodexProvider } from "@earendil-works/pi-ai/providers/openai-codex";
import { LOCAL_CODEX_PROVIDER } from "./codex-proxy.js";
/** Copy only model metadata. Never read credentials or expose cached model instructions. */
export function readLocalCodexModels(baseUrl, codexHome = process.env.CODEX_HOME || path.join(os.homedir(), ".codex")) {
    const models = new Map(openaiCodexProvider()
        .getModels()
        .map((model) => [
        model.id,
        {
            ...model,
            provider: LOCAL_CODEX_PROVIDER,
            baseUrl,
            name: `${model.name} (local CLI)`,
            input: ["text"],
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
            compat: undefined,
        },
    ]));
    const cachePath = path.join(codexHome, "models_cache.json");
    try {
        if (fs.statSync(cachePath).size > 4 * 1024 * 1024)
            throw new Error("catalog exceeds 4 MiB");
        const cache = JSON.parse(fs.readFileSync(cachePath, "utf8"));
        if (!cache || typeof cache !== "object" || !("models" in cache) || !Array.isArray(cache.models)) {
            throw new Error("missing models array");
        }
        let visible = 0;
        let invalid = 0;
        for (const entry of cache.models) {
            if (!entry || typeof entry !== "object") {
                invalid++;
                continue;
            }
            const value = entry;
            if (value.visibility === "hide" && typeof value.slug === "string")
                models.delete(value.slug);
            if (value.visibility !== "list")
                continue;
            if (typeof value.slug !== "string" ||
                !/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(value.slug) ||
                typeof value.display_name !== "string" ||
                !value.display_name.trim() ||
                typeof value.context_window !== "number" ||
                !Number.isSafeInteger(value.context_window) ||
                value.context_window < 1) {
                invalid++;
                continue;
            }
            const previous = models.get(value.slug);
            models.set(value.slug, {
                id: value.slug,
                name: `${value.display_name} (local CLI)`,
                api: "openai-codex-responses",
                provider: LOCAL_CODEX_PROVIDER,
                baseUrl,
                reasoning: Array.isArray(value.supported_reasoning_levels) && value.supported_reasoning_levels.length > 0,
                input: ["text"],
                cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
                contextWindow: value.context_window,
                // Adapter budget, not a claim about the service's maximum output length.
                maxTokens: Math.min(previous?.maxTokens ?? 32768, value.context_window),
            });
            visible++;
        }
        return {
            models: [...models.values()],
            source: `${cachePath} (${visible} visible models) + built-in fallback`,
            warning: invalid || !visible ? `Skipped ${invalid} invalid entries; found ${visible} visible models.` : undefined,
        };
    }
    catch (error) {
        return {
            models: [...models.values()],
            source: "built-in fallback",
            warning: `Cannot load ${cachePath}: ${error instanceof Error ? error.message : String(error)}`,
        };
    }
}
//# sourceMappingURL=codex-models.js.map