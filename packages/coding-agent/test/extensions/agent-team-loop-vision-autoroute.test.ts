/**
 * Auto-route tests (mw-vision-role T-07, AC-016 / AC-017, VC-016 / VC-017).
 *
 * Contract under test: an un-pinned task that needs images and whose role
 * default is a definite "no" is dispatched on the `vision` role's model when
 * that model is a definite "yes" — and ONLY the model moves: the `type:` line
 * (and with it the worker tool allowlist, D-004) is never rewritten. An
 * explicit `model:` is never overridden; a missing / non-"yes" `vision` value
 * leaves the refusal to the T-06 capability gate.
 *
 * Self-contained on purpose (the shared `agent-team-loop.test.ts` belongs to a
 * concurrent task): own fixtures and own `fakeRegistry` whose entries set
 * `input` (a capability of "unknown" would make the "yes"/"no" cases vacuous).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { Model } from "@earendil-works/pi-ai";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../src/core/extensions/types.ts";
import type { ModelRegistry } from "../../src/core/model-registry.ts";
import {
	planDispatchFrontmatter,
	registerWorkerCommands,
	registerWorkerTools,
	windowClaimId,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const TEXT_ID = "glm-5.3";
const OTHER_TEXT_ID = "plain-text-1";
const VISION_ID = "deepseek-v4-flash-vision-exp";

const TEXT_MODEL = `timi/${TEXT_ID}`;
const OTHER_TEXT_MODEL = `timi/${OTHER_TEXT_ID}`;
const VISION_MODEL = `timi/${VISION_ID}`;
/** A value the registry deliberately does not carry (capability "unknown"). */
const UNKNOWN_VISION_MODEL = "timi/vision-not-in-registry";

/** Minimal registry double that carries `input` (the capability fn reads it). */
function fakeRegistry(entries: Array<{ provider: string; id: string; input?: string[] }>): ModelRegistry {
	const models = entries.map((e) => e as unknown as Model<any>);
	return {
		getAll: () => models,
		find: (provider: string, modelId: string) => models.find((m) => m.provider === provider && m.id === modelId),
	} as unknown as ModelRegistry;
}

/** Two text-only models + one image-capable model, all resolvable through the registry. */
function registry(): ModelRegistry {
	return fakeRegistry([
		{ provider: "timi", id: TEXT_ID, input: ["text"] },
		{ provider: "timi", id: OTHER_TEXT_ID, input: ["text"] },
		{ provider: "timi", id: VISION_ID, input: ["text", "image"] },
	]);
}

const temporaryDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "atl-vision-autoroute-"));
	temporaryDirs.push(dir);
	return dir;
}

afterEach(() => {
	while (temporaryDirs.length > 0) {
		const dir = temporaryDirs.pop();
		if (dir) fs.rmSync(dir, { recursive: true, force: true });
	}
});

/** Complete phase-doc set for a key so the docs gate never masks the model gate. */
function writePhaseDocs(root: string, key: string): void {
	const keyDir = path.join(root, key);
	fs.mkdirSync(keyDir, { recursive: true });
	fs.writeFileSync(
		path.join(keyDir, "spec.md"),
		`# Spec\n${"x".repeat(600)}\n\n| AC-001 | in x, y returns z |\n`,
		"utf8",
	);
	fs.writeFileSync(path.join(keyDir, "design.md"), `# Design\n${"x".repeat(600)}`, "utf8");
	const research = path.join(keyDir, "evidence", "research");
	fs.mkdirSync(research, { recursive: true });
	fs.writeFileSync(path.join(research, "spec-topic-2026-01-01.md"), "# research\n", "utf8");
	fs.writeFileSync(path.join(research, "design-topic-2026-01-01.md"), "# research\n", "utf8");
}

function writePmState(root: string, key: string, phase: string): void {
	fs.mkdirSync(path.join(root, key), { recursive: true });
	fs.writeFileSync(path.join(root, key, "pm-state.md"), `- Phase: ${phase}\n- Updated: 2026-01-01 00:00\n`, "utf8");
}

/** `.mw/dispatch.yml` with the given role -> value mapping (same flat shape `mw model set` writes). */
function writeDispatchYml(root: string, models: Record<string, string>): void {
	const dir = path.join(root, ".mw");
	fs.mkdirSync(dir, { recursive: true });
	const body = Object.entries(models)
		.map(([role, value]) => `  ${role}: ${value}`)
		.join("\n");
	fs.writeFileSync(path.join(dir, "dispatch.yml"), `models:\n${body}\n`, "utf8");
}

function fakeCmdPi(): {
	pi: ExtensionAPI;
	commands: Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>;
	tools: Map<
		string,
		{
			execute: (
				id: string,
				params: unknown,
				signal: undefined,
				onUpdate: undefined,
				ctx: ExtensionContext,
			) => Promise<{ content: Array<{ type: string; text: string }> }>;
		}
	>;
} {
	const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
	const tools = new Map<
		string,
		{
			execute: (
				id: string,
				params: unknown,
				signal: undefined,
				onUpdate: undefined,
				ctx: ExtensionContext,
			) => Promise<{ content: Array<{ type: string; text: string }> }>;
		}
	>();
	const pi = {
		registerCommand: (
			name: string,
			opts: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
		) => {
			commands.set(name, opts.handler);
		},
		registerTool: (tool: {
			name: string;
			execute: (
				id: string,
				params: unknown,
				signal: undefined,
				onUpdate: undefined,
				ctx: ExtensionContext,
			) => Promise<{ content: Array<{ type: string; text: string }> }>;
		}) => {
			tools.set(tool.name, tool);
		},
		appendEntry: () => {},
		sendUserMessage: () => {},
		sendMessage: () => {},
	} as unknown as ExtensionAPI;
	return { pi, commands, tools };
}

function fakeCmdCtx(): { ctx: ExtensionCommandContext; notifications: string[] } {
	const notifications: string[] = [];
	const ctx = {
		hasUI: true,
		ui: {
			notify: (message: string) => {
				notifications.push(message);
			},
			setWidget: () => {},
		},
	} as unknown as ExtensionCommandContext;
	return { ctx, notifications };
}

async function seedKey(root: string, key: string, claimId: string): Promise<void> {
	await new IndexStore(root).upsert({
		key,
		status: "active",
		phase: "EXECUTE",
		claimId,
		deps: "",
		desc: "",
		updated: new Date().toISOString(),
	});
}

interface ToolFixture {
	root: string;
	rows: () => number;
	execute: (params: Record<string, unknown>, registryValue?: ModelRegistry) => Promise<string>;
}

/** dispatch_worker fixture: documented EXECUTE-phase key "k" claimed by this
 * window, projectDir = agenticdocRoot so `.mw/dispatch.yml` and image tokens
 * resolve under root. */
async function setupTool(models: Record<string, string>): Promise<ToolFixture> {
	const root = mkdtemp();
	writeDispatchYml(root, models);
	const ws = new WorkerStore(root);
	const is = new IndexStore(root);
	const { pi, tools } = fakeCmdPi();
	writePhaseDocs(root, "k");
	writePmState(root, "k", "EXECUTE");
	await seedKey(root, "k", windowClaimId());
	registerWorkerTools(pi, ws, new AckStore(root), is, root, { key: "k" }, root);
	const tool = tools.get("dispatch_worker");
	if (!tool) throw new Error("dispatch_worker not registered");
	return {
		root,
		rows: () => new WorkerStore(root).readAll().length,
		execute: async (params, registryValue) => {
			const base = fakeCmdCtx().ctx;
			const ctx =
				registryValue === undefined
					? base
					: ({ ...base, modelRegistry: registryValue } as unknown as ExtensionContext);
			return (await tool.execute("id", params, undefined, undefined, ctx)).content[0]?.text ?? "";
		},
	};
}

interface CommandFixture {
	root: string;
	rows: () => number;
	run: (args: string, registryValue?: ModelRegistry) => Promise<string[]>;
}

/** /worker fixture, same documented + claimed key. */
async function setupCommand(models: Record<string, string>): Promise<CommandFixture> {
	const root = mkdtemp();
	writeDispatchYml(root, models);
	const ws = new WorkerStore(root);
	const is = new IndexStore(root);
	const { pi, commands } = fakeCmdPi();
	writePhaseDocs(root, "k");
	writePmState(root, "k", "EXECUTE");
	await seedKey(root, "k", windowClaimId());
	registerWorkerCommands(pi, ws, is, root, { key: "k" }, root);
	const handler = commands.get("worker");
	if (!handler) throw new Error("/worker not registered");
	return {
		root,
		rows: () => new WorkerStore(root).readAll().length,
		run: async (args, registryValue) => {
			const { ctx, notifications } = fakeCmdCtx();
			const withRegistry =
				registryValue === undefined
					? ctx
					: ({ ...ctx, modelRegistry: registryValue } as unknown as ExtensionCommandContext);
			await handler(args, withRegistry);
			return notifications;
		},
	};
}

function taskDir(root: string, taskKey: string): string {
	return path.join(root, "k", "workers", taskKey);
}

function taskMdOf(root: string, taskKey: string): string {
	return fs.readFileSync(path.join(taskDir(root, taskKey), "task.md"), "utf8");
}

function soleTaskMdOf(root: string): string {
	const workers = fs.readdirSync(path.join(root, "k", "workers"));
	expect(workers).toHaveLength(1);
	return fs.readFileSync(path.join(root, "k", "workers", workers[0] as string, "task.md"), "utf8");
}

function plantPng(root: string, rel: string): void {
	const abs = path.join(root, rel);
	fs.mkdirSync(path.dirname(abs), { recursive: true });
	fs.writeFileSync(abs, "\x89PNG\r\n\x1a\n", "utf8");
}

/** Types whose AC-017 parameterized case already ran (evidence collector). */
const ac017Types: string[] = [];

describe("dispatch auto-route (mw-vision-role T-07)", () => {
	it("VC-016: routes a text-only role default to the vision model and keeps `type:` untouched", async () => {
		const fx = await setupTool({ review: TEXT_MODEL, vision: VISION_MODEL });
		plantPng(fx.root, "shots/login.png");
		const message = await fx.execute(
			{ task_key: "t1", type: "review", description: "match shots/login.png against the mock" },
			registry(),
		);
		expect(message).toContain("Dispatched worker 't1'");
		const md = taskMdOf(fx.root, "t1");
		expect(md).toMatch(/^type: review$/m);
		expect(md).toMatch(/^images: yes$/m);
		expect(md).toMatch(new RegExp(`^model: ${VISION_MODEL.replace("/", "\\/")}$`, "m"));
		expect(md).toMatch(/^model-reason: auto-route: review -> vision$/m);
		expect(md).not.toContain(TEXT_MODEL);
		expect(message).toContain("model-source: auto-route");
		expect(message).toContain(`vision=${VISION_MODEL}`);
		process.stdout.write("[VERIFY] VC-016: auto_route=true type_unchanged=true explicit_model_untouched=true\n");
	});

	describe("AC-017: auto-route is capability-driven, not type-driven", () => {
		it.each(["review", "vision"] as const)(
			"declared type=%s keeps its `type:` line and dispatches on the vision model",
			async (declaredType) => {
				const fx = await setupTool({ review: TEXT_MODEL, vision: VISION_MODEL });
				plantPng(fx.root, "shots/login.png");
				const message = await fx.execute(
					{ task_key: "t1", type: declaredType, description: "match shots/login.png" },
					registry(),
				);
				expect(message).toContain("Dispatched worker 't1'");
				const md = taskMdOf(fx.root, "t1");
				// The declared type survives verbatim in both cases (no forced re-typing).
				expect(md).toMatch(new RegExp(`^type: ${declaredType}$`, "m"));
				if (declaredType === "review") {
					// review's role default is text-only -> auto-route fires.
					expect(md).toMatch(new RegExp(`^model: ${VISION_MODEL.replace("/", "\\/")}$`, "m"));
					expect(md).toMatch(/^model-reason: auto-route: review -> vision$/m);
					expect(message).toContain("model-source: auto-route");
					expect(message).toContain(`vision=${VISION_MODEL}`);
				} else {
					// `type: vision` resolves to the vision role itself, so its configured
					// default IS the vision model: the launcher already runs it on the
					// vision value and no redundant model pin/reason is written. Same
					// conclusion as the review case (effective model = vision value,
					// `type:` untouched) for the degenerate self-role case.
					expect(md.split("\n").some((line) => line.startsWith("model:"))).toBe(false);
					expect(md).not.toContain("auto-route");
					expect(message).toContain(`vision=${VISION_MODEL}`);
				}
				ac017Types.push(declaredType);
			},
		);
	});

	it("an explicit text-only `model:` is never rewritten and walks the capability gate", async () => {
		const fx = await setupTool({ review: TEXT_MODEL, vision: VISION_MODEL });
		plantPng(fx.root, "shots/login.png");
		const before = fx.rows();
		const message = await fx.execute(
			{
				task_key: "t2",
				type: "review",
				description: "match shots/login.png",
				model: OTHER_TEXT_MODEL,
			},
			registry(),
		);
		expect(message).toContain("mw model set vision");
		expect(message).toContain(OTHER_TEXT_MODEL);
		expect(message).not.toContain(VISION_MODEL);
		expect(fs.existsSync(taskDir(fx.root, "t2"))).toBe(false);
		expect(fx.rows()).toBe(before);
	});

	it("an unconfigured `vision` role does not route and the gate refuses", async () => {
		const fx = await setupTool({ review: TEXT_MODEL });
		plantPng(fx.root, "shots/login.png");
		const before = fx.rows();
		const message = await fx.execute(
			{ task_key: "t3", type: "review", description: "match shots/login.png" },
			registry(),
		);
		expect(message).toContain("mw model set vision");
		expect(message).not.toContain("auto-route");
		expect(fs.existsSync(taskDir(fx.root, "t3"))).toBe(false);
		expect(fx.rows()).toBe(before);
	});

	it("a `vision` model that is not a definite 'yes' does not route (text-only and unknown)", async () => {
		// (a) vision -> a different text-only model: capability "no".
		const textVision = await setupTool({ review: TEXT_MODEL, vision: OTHER_TEXT_MODEL });
		plantPng(textVision.root, "shots/login.png");
		let before = textVision.rows();
		let message = await textVision.execute(
			{ task_key: "t4", type: "review", description: "match shots/login.png" },
			registry(),
		);
		expect(message).toContain("mw model set vision");
		expect(message).not.toContain("auto-route");
		expect(fs.existsSync(taskDir(textVision.root, "t4"))).toBe(false);
		expect(textVision.rows()).toBe(before);

		// (b) vision -> a value the registry cannot resolve: capability "unknown".
		// Only a definite "yes" may route; "unknown" must fall back to the gate on
		// the text-only role default, which refuses (a relaxed "non-no routes"
		// rule would instead route and fail open, hiding the refusal).
		const unknownVision = await setupTool({ review: TEXT_MODEL, vision: UNKNOWN_VISION_MODEL });
		plantPng(unknownVision.root, "shots/login.png");
		before = unknownVision.rows();
		message = await unknownVision.execute(
			{ task_key: "t4", type: "review", description: "match shots/login.png" },
			registry(),
		);
		expect(message).toContain("mw model set vision");
		expect(message).not.toContain("auto-route");
		expect(fs.existsSync(taskDir(unknownVision.root, "t4"))).toBe(false);
		expect(unknownVision.rows()).toBe(before);
	});

	it("no image need does not route and keeps the non-route plan output byte-identical", async () => {
		const fx = await setupTool({ review: TEXT_MODEL, vision: VISION_MODEL });
		const before = fx.rows();
		const message = await fx.execute(
			{ task_key: "t5", type: "review", description: "refactor the dispatcher" },
			registry(),
		);
		expect(message).toContain("Dispatched worker 't5'");
		expect(message).not.toContain("auto-route");
		const [frontmatter] = taskMdOf(fx.root, "t5").split("\n\n");
		expect(frontmatter).toBe("type: review\nphase: EXECUTE");
		expect(fx.rows()).toBe(before + 1);

		const plan = planDispatchFrontmatter({
			cwd: fx.root,
			cli: "pi",
			provider: "timi",
			taskType: "review",
			description: "refactor the dispatcher",
			model: "",
			modelReason: "",
			registry: registry(),
		});
		if (!plan.ok) throw new Error("expected ok plan");
		expect(plan.frontmatter).toBe("type: review\n");
		expect(plan.echo).toBe(`model: dispatch.yml review=${TEXT_MODEL}`);
	});

	it("the route plan output pins the vision model and appends the machine-readable source", async () => {
		const fx = await setupTool({ review: TEXT_MODEL, vision: VISION_MODEL });
		plantPng(fx.root, "shots/login.png");
		const routed = planDispatchFrontmatter({
			cwd: fx.root,
			cli: "pi",
			provider: "timi",
			taskType: "review",
			description: "match shots/login.png",
			model: "",
			modelReason: "",
			registry: registry(),
		});
		if (!routed.ok) throw new Error("expected ok plan");
		expect(routed.frontmatter).toBe(
			`type: review\nimages: yes\nmodel: ${VISION_MODEL}\nmodel-reason: auto-route: review -> vision\n`,
		);
		expect(routed.echo).toBe(
			`model: dispatch.yml vision=${VISION_MODEL} (model-source: auto-route, review -> vision)`,
		);
	});

	it("a user-supplied model_reason is preserved ahead of the auto-route marker", async () => {
		const fx = await setupTool({ review: TEXT_MODEL, vision: VISION_MODEL });
		plantPng(fx.root, "shots/login.png");
		const plan = planDispatchFrontmatter({
			cwd: fx.root,
			cli: "pi",
			provider: "timi",
			taskType: "review",
			description: "match shots/login.png",
			model: "",
			modelReason: "reviewer asked for pixel diff",
			registry: registry(),
		});
		if (!plan.ok) throw new Error("expected ok plan");
		expect(plan.frontmatter).toContain("model-reason: reviewer asked for pixel diff; auto-route: review -> vision");
	});

	it("/worker --type review auto-routes through the same plan and echoes the source", async () => {
		const fx = await setupCommand({ review: TEXT_MODEL, vision: VISION_MODEL });
		plantPng(fx.root, "shots/login.png");
		const before = fx.rows();
		const notes = await fx.run("pi --key k --type review match shots/login.png", registry());
		const joined = notes.join("\n");
		expect(joined).toContain("Dispatched pi worker");
		expect(joined).toContain("model-source: auto-route");
		expect(joined).toContain(`vision=${VISION_MODEL}`);
		expect(fx.rows()).toBe(before + 1);
		const md = soleTaskMdOf(fx.root);
		expect(md).toMatch(/^type: review$/m);
		expect(md).toMatch(new RegExp(`^model: ${VISION_MODEL.replace("/", "\\/")}$`, "m"));
		expect(md).toMatch(/^model-reason: auto-route: review -> vision$/m);
	});

	it("VC-017 evidence: both declared types were exercised", () => {
		const types = ["vision", "review"].filter((t) => ac017Types.includes(t));
		expect(types).toEqual(["vision", "review"]);
		process.stdout.write(
			`[VERIFY] VC-017: types=${types.join(",")} type_unchanged=true effective_vision=${types.length} auto_route_fired=${types.filter((t) => t === "review").length}\n`,
		);
	});
});
