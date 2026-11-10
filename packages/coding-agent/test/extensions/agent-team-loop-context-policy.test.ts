import fs from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	CONTEXT_POLICY_FIELDS,
	ContextPolicyError,
	DELEGATED_CONTEXT_FIELDS,
	readContextPolicyDocument,
	resolveContextPolicy,
	updateContextPolicy,
} from "../../src/extensions/agent-team-loop/shared/context-policy.ts";

let root: string;
let homeDir: string;
let controlRoot: string;
let globalPath: string;
let projectPath: string;

beforeEach(() => {
	root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-context-policy-"));
	homeDir = path.join(root, "home");
	controlRoot = path.join(root, "control");
	globalPath = path.join(homeDir, ".mw", "context.json");
	projectPath = path.join(controlRoot, ".mw", "context.json");
});
afterEach(() => {
	vi.restoreAllMocks();
	syncBuiltinESMExports();
	fs.rmSync(root, { recursive: true, force: true });
});

function write(filePath: string, document: unknown): void {
	fs.mkdirSync(path.dirname(filePath), { recursive: true });
	fs.writeFileSync(filePath, JSON.stringify(document), "utf8");
}

describe("context policy resolution", () => {
	it("uses removable initial type entries only when global configuration is absent, without writing", () => {
		for (const [taskType, maxTokens, level] of [
			["pm", 512000, "defaults"],
			["default", 512000, "defaults"],
			["coding", 256000, "type"],
			["research", 256000, "type"],
			["review", 512000, "type"],
			["phase-writer", 512000, "defaults"],
			["verifier", 512000, "defaults"],
			["my-custom", 512000, "defaults"],
		] as const) {
			const policy = resolveContextPolicy({ controlRoot, homeDir, taskType });
			expect(policy.maxTokens).toBe(maxTokens);
			expect(policy.taskType).toBe(taskType);
			expect(policy.sources.maxTokens).toMatchObject({ scope: "global", path: globalPath, level, builtin: true });
			expect(policy.compaction).toEqual({
				enabled: true,
				triggerRatio: 0.8,
				targetRatio: 0.5,
				keepRecentTokens: 20000,
				maxSummaryTokens: 4096,
				timeoutMs: 120000,
			});
			expect(Object.keys(policy.sources).sort()).toEqual([...CONTEXT_POLICY_FIELDS].sort());
		}
		expect(fs.existsSync(homeDir)).toBe(false);
		expect(fs.existsSync(controlRoot)).toBe(false);
	});

	it.each([undefined, {}])("treats an existing global types table %j as complete instead of reseeding", (types) => {
		write(globalPath, { version: 1, defaults: { maxTokens: 400000 }, ...(types ? { types } : {}) });
		for (const taskType of ["coding", "research", "review", "custom"]) {
			const policy = resolveContextPolicy({ controlRoot, homeDir, taskType });
			expect(policy.maxTokens).toBe(400000);
			expect(policy.sources.maxTokens).toEqual({
				scope: "global",
				level: "defaults",
				path: globalPath,
				builtin: false,
			});
			expect(policy.sources["compaction.enabled"].builtin).toBe(true);
		}
	});

	it("project empty types preserves global type entries", () => {
		write(projectPath, { version: 1, types: {} });
		expect(resolveContextPolicy({ controlRoot, homeDir, taskType: "coding" }).maxTokens).toBe(256000);
	});

	it("resolves every field separately through all four layers and sequential clear operations", async () => {
		write(globalPath, {
			version: 1,
			defaults: { maxTokens: 410000, compaction: { timeoutMs: 111000, enabled: false } },
			types: { coding: { maxTokens: 310000, compaction: { timeoutMs: 112000, targetRatio: 0.4 } } },
		});
		write(projectPath, {
			version: 1,
			defaults: { maxTokens: 210000, compaction: { timeoutMs: 113000, maxSummaryTokens: 3000 } },
			types: { coding: { maxTokens: 110000, compaction: { triggerRatio: 0.7, timeoutMs: 114000 } } },
		});
		const options = { controlRoot, homeDir, taskType: "coding" };
		let policy = resolveContextPolicy(options);
		expect(policy.maxTokens).toBe(110000);
		expect(policy.compaction).toEqual({
			enabled: false,
			triggerRatio: 0.7,
			targetRatio: 0.4,
			keepRecentTokens: 20000,
			maxSummaryTokens: 3000,
			timeoutMs: 114000,
		});
		expect(policy.sources["compaction.enabled"]).toMatchObject({
			scope: "global",
			level: "defaults",
			builtin: false,
		});
		expect(policy.sources["compaction.targetRatio"]).toMatchObject({
			scope: "global",
			level: "type",
			taskType: "coding",
		});
		expect(policy.sources["compaction.maxSummaryTokens"]).toMatchObject({ scope: "project", level: "defaults" });
		expect(policy.sources["compaction.keepRecentTokens"]).toMatchObject({
			scope: "global",
			level: "defaults",
			builtin: true,
		});
		for (const [scope, type, maxTokens, timeoutMs, expectedScope, expectedLevel] of [
			["project", "coding", 210000, 113000, "project", "defaults"],
			["project", undefined, 310000, 112000, "global", "type"],
			["global", "coding", 410000, 111000, "global", "defaults"],
		] as const) {
			await updateContextPolicy({ ...options, operation: "clear", scope, type, field: "maxTokens" });
			policy = await updateContextPolicy({
				...options,
				operation: "clear",
				scope,
				type,
				field: "compaction.timeoutMs",
			});
			expect(policy.maxTokens).toBe(maxTokens);
			expect(policy.compaction.timeoutMs).toBe(timeoutMs);
			for (const field of ["maxTokens", "compaction.timeoutMs"] as const)
				expect(policy.sources[field]).toMatchObject({ scope: expectedScope, level: expectedLevel, builtin: false });
		}
	});

	it("global type removal is durable across rereads and preserves other entries", async () => {
		const options = { controlRoot, homeDir, taskType: "coding" };
		await updateContextPolicy({ ...options, scope: "global", operation: "clear", field: "type", type: "coding" });
		expect(readContextPolicyDocument(globalPath)?.types).toEqual({
			research: { maxTokens: 256000 },
			review: { maxTokens: 512000 },
		});
		await updateContextPolicy({ ...options, scope: "global", operation: "set", field: "maxTokens", value: 333000 });
		for (const taskType of ["coding", "custom", "phase-writer"])
			expect(resolveContextPolicy({ ...options, taskType }).maxTokens).toBe(333000);
		expect(resolveContextPolicy({ ...options, taskType: "research" }).maxTokens).toBe(256000);
		expect(fs.readFileSync(globalPath, "utf8").startsWith("\uFEFF")).toBe(false);
	});

	it("clearing project type restores global inheritance and preserves unrelated overrides", async () => {
		write(projectPath, {
			version: 1,
			defaults: { compaction: { enabled: false } },
			types: { coding: { maxTokens: 100000 }, custom: { maxTokens: 230000 } },
		});
		const policy = await updateContextPolicy({
			controlRoot,
			homeDir,
			taskType: "coding",
			scope: "project",
			operation: "clear",
			field: "type",
			type: "coding",
		});
		expect(policy.maxTokens).toBe(256000);
		expect(policy.compaction.enabled).toBe(false);
		expect(readContextPolicyDocument(projectPath)).toEqual({
			version: 1,
			defaults: { compaction: { enabled: false } },
			types: { custom: { maxTokens: 230000 } },
		});
	});

	it("uses task header type and control path despite target configuration or body type", () => {
		write(projectPath, { version: 1, types: { research: { maxTokens: 321000 } } });
		const target = path.join(root, "target");
		write(path.join(target, ".mw", "context.json"), { version: 1, defaults: { maxTokens: 1 } });
		const taskFile = path.join(controlRoot, ".agenticdoc", "key", "workers", "task", "task.md");
		fs.mkdirSync(path.dirname(taskFile), { recursive: true });
		fs.writeFileSync(taskFile, "type: research\n\ntype: coding\n");
		const policy = resolveContextPolicy({ controlRoot: target, homeDir, taskFile });
		expect(policy.controlRoot).toBe(controlRoot);
		expect(policy.taskType).toBe("research");
		expect(policy.maxTokens).toBe(321000);
		expect(policy.paths.project).toBe(projectPath);
		fs.writeFileSync(taskFile, "title: missing-type\n\ntype: coding\n");
		expect(resolveContextPolicy({ controlRoot: target, homeDir, taskFile }).taskType).toBe("default");
		expect(resolveContextPolicy({ controlRoot: target, homeDir, taskFile }).maxTokens).toBe(512000);
	});

	it("accepts one leading UTF8 BOM without mutating the file", () => {
		fs.mkdirSync(path.dirname(globalPath), { recursive: true });
		const text = '\uFEFF{"version":1,"defaults":{"maxTokens":123000}}';
		fs.writeFileSync(globalPath, text, "utf8");
		expect(resolveContextPolicy({ controlRoot, homeDir, taskType: "coding" }).maxTokens).toBe(123000);
		expect(fs.readFileSync(globalPath, "utf8")).toBe(text);
	});
});

describe("context policy invalid inputs and atomic updates", () => {
	it("first global write creates only active MW fields without legacy generation overrides", async () => {
		await updateContextPolicy({
			controlRoot,
			homeDir,
			scope: "global",
			operation: "set",
			field: "maxTokens",
			value: 400000,
		});
		expect(readContextPolicyDocument(globalPath)?.defaults).toEqual({
			maxTokens: 400000,
			compaction: { enabled: true, triggerRatio: 0.8 },
		});
	});
	it.each([
		["[]", "$"],
		["null", "$"],
		["{", "$"],
		['{"version":2}', "version"],
		['{"version":1,"unknown":1}', "unknown"],
		['{"version":1,"types":[]}', "types"],
		['{"version":1,"types":{"coding":null}}', "types.coding"],
		['{"version":1,"defaults":{"typo":1}}', "defaults.typo"],
		['{"version":1,"defaults":{"maxTokens":0}}', "defaults.maxTokens"],
		['{"version":1,"defaults":{"maxTokens":-1}}', "defaults.maxTokens"],
		['{"version":1,"defaults":{"maxTokens":1.5}}', "defaults.maxTokens"],
		['{"version":1,"defaults":{"maxTokens":9007199254740992}}', "defaults.maxTokens"],
		['{"version":1,"defaults":{"maxTokens":true}}', "defaults.maxTokens"],
		['{"version":1,"defaults":{"maxTokens":""}}', "defaults.maxTokens"],
		['{"version":1,"defaults":{"compaction":null}}', "defaults.compaction"],
		['{"version":1,"defaults":{"compaction":{"enabled":"false"}}}', "compaction.enabled"],
		['{"version":1,"defaults":{"compaction":{"keepRecentTokens":0}}}', "keepRecentTokens"],
		['{"version":1,"defaults":{"compaction":{"maxSummaryTokens":-1}}}', "maxSummaryTokens"],
		['{"version":1,"defaults":{"compaction":{"timeoutMs":true}}}', "timeoutMs"],
		['{"version":1,"defaults":{"compaction":{"targetRatio":0}}}', "targetRatio"],
		['{"version":1,"defaults":{"compaction":{"triggerRatio":1}}}', "triggerRatio"],
	])("rejects malformed document %s with path and field %s", (text, field) => {
		fs.mkdirSync(path.dirname(projectPath), { recursive: true });
		fs.writeFileSync(projectPath, text);
		expect(() => resolveContextPolicy({ controlRoot, homeDir })).toThrow(ContextPolicyError);
		try {
			resolveContextPolicy({ controlRoot, homeDir });
			throw new Error("expected rejection");
		} catch (error) {
			expect(error).toBeInstanceOf(ContextPolicyError);
			expect(String(error)).toContain(field);
			// A resolved cross-layer ratio can reference the inherited global value.
			expect(String(error)).toMatch(/context\.json/);
		}
		expect(fs.readFileSync(projectPath, "utf8")).toBe(text);
	});

	it("does not reuse a previous permissive snapshot after config becomes unreadable", () => {
		write(projectPath, { version: 1, defaults: { maxTokens: 500000 } });
		expect(resolveContextPolicy({ controlRoot, homeDir }).maxTokens).toBe(500000);
		fs.unlinkSync(projectPath);
		fs.mkdirSync(projectPath);
		expect(() => resolveContextPolicy({ controlRoot, homeDir })).toThrow(projectPath);
	});

	it("legacy target ratios cannot constrain the active native trigger", async () => {
		write(globalPath, { version: 1, defaults: { compaction: { targetRatio: 0.6 } } });
		write(projectPath, { version: 1, types: { custom: { maxTokens: 100000 } } });
		const policy = await updateContextPolicy({
			controlRoot,
			homeDir,
			taskType: "custom",
			scope: "project",
			operation: "set",
			type: "custom",
			field: "compaction.triggerRatio",
			value: 0.55,
		});
		expect(policy.compaction.triggerRatio).toBe(0.55);
		expect(policy.compaction.targetRatio).toBe(0.6);
		expect(fs.readdirSync(path.dirname(projectPath))).toEqual(["context.json"]);
	});

	it.each(DELEGATED_CONTEXT_FIELDS)(
		"refuses setting delegated %s without writing but permits clearing old values",
		async (field) => {
			write(projectPath, {
				version: 1,
				defaults: {
					compaction: { targetRatio: 0.9, keepRecentTokens: 20000, maxSummaryTokens: 4096, timeoutMs: 120000 },
				},
			});
			const original = fs.readFileSync(projectPath, "utf8");
			await expect(
				updateContextPolicy({
					controlRoot,
					homeDir,
					scope: "project",
					operation: "set",
					field,
					value: field === "compaction.targetRatio" ? 0.4 : 1000,
				}),
			).rejects.toThrow("MW_CONTEXT_NATIVE_PARAMETER");
			expect(fs.readFileSync(projectPath, "utf8")).toBe(original);
			await updateContextPolicy({ controlRoot, homeDir, scope: "project", operation: "clear", field });
			expect(readContextPolicyDocument(projectPath)?.defaults?.compaction).not.toHaveProperty(
				field.slice("compaction.".length),
			);
		},
	);

	it("does not steal an existing lock or alter config during lock conflict", async () => {
		write(projectPath, { version: 1, types: {} });
		fs.writeFileSync(`${projectPath}.lock`, "other-owner");
		const original = fs.readFileSync(projectPath, "utf8");
		await expect(
			updateContextPolicy({
				controlRoot,
				homeDir,
				scope: "project",
				operation: "set",
				field: "maxTokens",
				value: 123000,
			}),
		).rejects.toThrow("MW_CONTEXT_CONFIG_LOCK");
		expect(fs.readFileSync(projectPath, "utf8")).toBe(original);
		expect(fs.readFileSync(`${projectPath}.lock`, "utf8")).toBe("other-owner");
	});

	it("keeps original bytes and removes temporary/lock files when atomic rename fails", async () => {
		write(projectPath, { version: 1, defaults: { maxTokens: 200000 } });
		const original = fs.readFileSync(projectPath, "utf8");
		vi.spyOn(fs, "renameSync").mockImplementation(() => {
			throw new Error("injected rename failure");
		});
		syncBuiltinESMExports();
		await expect(
			updateContextPolicy({
				controlRoot,
				homeDir,
				scope: "project",
				operation: "set",
				field: "maxTokens",
				value: 123000,
			}),
		).rejects.toThrow("MW_CONTEXT_CONFIG_WRITE");
		expect(fs.readFileSync(projectPath, "utf8")).toBe(original);
		expect(fs.readdirSync(path.dirname(projectPath))).toEqual(["context.json"]);
	});

	it("supports prototype-shaped exact types without polluting global objects", async () => {
		await updateContextPolicy({
			controlRoot,
			homeDir,
			scope: "project",
			operation: "set",
			type: "__proto__",
			field: "maxTokens",
			value: 123000,
		});
		expect(resolveContextPolicy({ controlRoot, homeDir, taskType: "__proto__" }).maxTokens).toBe(123000);
		expect(resolveContextPolicy({ controlRoot, homeDir, taskType: "constructor" }).maxTokens).toBe(512000);
		expect(Object.hasOwn(Object.prototype, "maxTokens")).toBe(false);
	});
});
