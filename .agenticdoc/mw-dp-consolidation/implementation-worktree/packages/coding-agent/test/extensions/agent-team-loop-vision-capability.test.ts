/**
 * Unit tests for the image-capability pure functions (mw-vision-role T-04,
 * AC-008 / VC-008).
 *
 * The contract under test is fail-open: `modelImageCapability` returns
 * "unknown" for every situation the registry cannot decide (NOT "no"), and
 * only a registry hit yields "yes"/"no" from `Model.input`. `detectImageNeed`
 * only reports true for an existing, non-glob, non-URL image token.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { Model } from "@earendil-works/pi-ai";
import { afterEach, describe, expect, it } from "vitest";
import type { ModelRegistry } from "../../src/core/model-registry.ts";
import {
	detectImageNeed,
	type ImageCapability,
	modelImageCapability,
} from "../../src/extensions/agent-team-loop/shared/dispatch-models.ts";

const TIMI = "timi";
const TEXT_ID = "glm-5.3";
const VISION_ID = "deepseek-v4-flash-vision-exp";

/** Minimal registry double: only getAll/find are read by the capability fn. */
function fakeRegistry(entries: Array<{ provider: string; id: string; input?: string[] }>): ModelRegistry {
	const models = entries.map((e) => e as unknown as Model<any>);
	return {
		getAll: () => models,
		find: (provider: string, modelId: string) => models.find((m) => m.provider === provider && m.id === modelId),
	} as unknown as ModelRegistry;
}

const REGISTRY = (): ModelRegistry =>
	fakeRegistry([
		{ provider: TIMI, id: TEXT_ID, input: ["text"] },
		{ provider: TIMI, id: VISION_ID, input: ["text", "image"] },
		{ provider: "unknownprov", id: "some-model", input: ["text"] },
	]);

const temporaryDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "pi-vision-capability-"));
	temporaryDirs.push(dir);
	return dir;
}

afterEach(() => {
	while (temporaryDirs.length > 0) {
		const dir = temporaryDirs.pop();
		if (dir) fs.rmSync(dir, { recursive: true, force: true });
	}
});

describe("modelImageCapability (fail-open, three-state)", () => {
	it("returns unknown for the undecidable early-return branches (never 'no')", () => {
		const registry = REGISTRY();
		const branches: ReadonlyArray<{ label: string; capability: ImageCapability }> = [
			{ label: "empty value", capability: modelImageCapability(registry, "pi", TIMI, "   ") },
			{ label: "registry undefined", capability: modelImageCapability(undefined, "pi", TIMI, "timi/glm-5.3") },
			{ label: "cli != pi", capability: modelImageCapability(registry, "codex", TIMI, "timi/glm-5.3") },
			{ label: "no model id", capability: modelImageCapability(registry, "pi", TIMI, "timi/") },
			{ label: "codex_cli prefix", capability: modelImageCapability(registry, "pi", "", "codex_cli/gpt-5") },
			{ label: "claude_cli prefix", capability: modelImageCapability(registry, "pi", "", "claude_cli/sonnet") },
			{ label: "unknown prefix", capability: modelImageCapability(registry, "pi", "", "nope/model-x") },
			{ label: "no provider (bare id)", capability: modelImageCapability(registry, "pi", "", "glm-5.3") },
			{
				label: "provider absent from registry",
				capability: modelImageCapability(registry, "pi", "unknownprov", "glm-5.3"),
			},
			{
				label: "registry.find miss",
				capability: modelImageCapability(registry, "pi", TIMI, "timi/does-not-exist"),
			},
		];
		for (const branch of branches) {
			expect(branch.capability, `${branch.label} must be "unknown" (fail-open)`).toBe("unknown");
		}
		process.stdout.write(`[VERIFY] VC-008: unknown_branches=${branches.length}\n`);
	});

	it("returns no for a resolvable text-only model", () => {
		expect(modelImageCapability(REGISTRY(), "pi", TIMI, `timi/${TEXT_ID}`)).toBe("no");
	});

	it("returns yes for a resolvable model whose input includes image", () => {
		expect(modelImageCapability(REGISTRY(), "pi", TIMI, `timi/${VISION_ID}`)).toBe("yes");
	});

	it("accepts a case-insensitive pi cli and reads Model.input via the registry hit", () => {
		expect(modelImageCapability(REGISTRY(), "PI", TIMI, `timi/${VISION_ID}`)).toBe("yes");
		expect(modelImageCapability(REGISTRY(), "Pi", TIMI, `timi/${TEXT_ID}`)).toBe("no");
	});
});

describe("detectImageNeed", () => {
	it("returns true for an existing image file token", () => {
		const cwd = mkdtemp();
		fs.mkdirSync(path.join(cwd, "docs", "ui"), { recursive: true });
		fs.writeFileSync(path.join(cwd, "docs", "ui", "login.png"), "x");
		expect(detectImageNeed(cwd, "match docs/ui/login.png against the mock")).toBe(true);
		expect(detectImageNeed(cwd, "or just login.png")).toBe(false);
	});

	it("returns false for an absent image file token", () => {
		const cwd = mkdtemp();
		expect(detectImageNeed(cwd, "match docs/ui/generated.png")).toBe(false);
	});

	it("returns false for a URL token", () => {
		const cwd = mkdtemp();
		expect(detectImageNeed(cwd, "fetch https://x/y.png")).toBe(false);
	});

	it("returns false for a glob token", () => {
		const cwd = mkdtemp();
		expect(detectImageNeed(cwd, "all *.png files")).toBe(false);
	});

	it("returns false for descriptions without image tokens", () => {
		const cwd = mkdtemp();
		expect(detectImageNeed(cwd, "refactor the dispatcher")).toBe(false);
		expect(detectImageNeed(cwd, "")).toBe(false);
	});
});
