/**
 * Dispatch capability gate tests (mw-vision-role T-06, AC-006 / AC-008,
 * VC-006 / VC-008).
 *
 * The gate refuses a dispatch whose effective model cannot take image input
 * ONLY when the task really needs images (explicit `images: "yes"`, or an
 * existing image file referenced by the description), and ONLY on a definite
 * `"no"` capability — every undecidable registry (unknown) fails open. A
 * refusal must be zero-side-effect: no task dir, no `_workers.parallel` row.
 *
 * Self-contained on purpose: `agent-team-loop.test.ts` is rewritten by a
 * concurrent task, so this file carries its own fixtures and its own
 * `fakeRegistry` (entries MUST set `input`, otherwise the capability is
 * forever "unknown" and every "yes" case would pass vacuously).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { Model } from "@earendil-works/pi-ai";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../src/core/extensions/types.ts";
import type { ModelRegistry } from "../../src/core/model-registry.ts";
import {
	registerWorkerCommands,
	registerWorkerTools,
	windowClaimId,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const TEXT_ID = "glm-5.3";
const VISION_ID = "deepseek-v4-flash-vision-exp";

/** Minimal registry double that carries `input` (the capability fn reads it). */
function fakeRegistry(entries: Array<{ provider: string; id: string; input?: string[] }>): ModelRegistry {
	const models = entries.map((e) => e as unknown as Model<any>);
	return {
		getAll: () => models,
		find: (provider: string, modelId: string) => models.find((m) => m.provider === provider && m.id === modelId),
	} as unknown as ModelRegistry;
}

/** timi text-only + timi vision model, both resolvable through the registry. */
function timiRegistry(): ModelRegistry {
	return fakeRegistry([
		{ provider: "timi", id: TEXT_ID, input: ["text"] },
		{ provider: "timi", id: VISION_ID, input: ["text", "image"] },
	]);
}

const TEXT_MODEL = `timi/${TEXT_ID}`;
const VISION_MODEL = `timi/${VISION_ID}`;

const temporaryDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "atl-vision-gate-"));
	temporaryDirs.push(dir);
	return dir;
}

afterEach(() => {
	while (temporaryDirs.length > 0) {
		const dir = temporaryDirs.pop();
		if (dir) fs.rmSync(dir, { recursive: true, force: true });
	}
});

/** Complete phase-doc set for a key (spec + design >= 500 bytes, an AC, and
 * one research note per phase) so the docs gate never masks the model gate. */
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
	execute: (params: Record<string, unknown>, registry?: ModelRegistry) => Promise<string>;
}

/** dispatch_worker fixture: documented EXECUTE-phase key "k" claimed by this
 * window, projectDir = agenticdocRoot so image tokens resolve under root. */
async function setupTool(): Promise<ToolFixture> {
	const root = mkdtemp();
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
		execute: async (params, registry) => {
			const base = fakeCmdCtx().ctx;
			const ctx =
				registry === undefined ? base : ({ ...base, modelRegistry: registry } as unknown as ExtensionContext);
			return (await tool.execute("id", params, undefined, undefined, ctx)).content[0]?.text ?? "";
		},
	};
}

interface CommandFixture {
	root: string;
	rows: () => number;
	run: (args: string, registry?: ModelRegistry) => Promise<string[]>;
}

/** /worker fixture, same documented + claimed key. */
async function setupCommand(): Promise<CommandFixture> {
	const root = mkdtemp();
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
		run: async (args, registry) => {
			const { ctx, notifications } = fakeCmdCtx();
			const withRegistry =
				registry === undefined ? ctx : ({ ...ctx, modelRegistry: registry } as unknown as ExtensionCommandContext);
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

/** Line index of an exact frontmatter line, or -1. */
function lineIndex(md: string, exact: string): number {
	return md.split("\n").indexOf(exact);
}

function plantPng(root: string, rel: string): void {
	const abs = path.join(root, rel);
	fs.mkdirSync(path.dirname(abs), { recursive: true });
	fs.writeFileSync(abs, "\x89PNG\r\n\x1a\n", "utf8");
}

describe("dispatch capability gate (mw-vision-role T-06)", () => {
	it("VC-006: input:text + images:yes is refused with zero side effects", async () => {
		const fx = await setupTool();
		const before = fx.rows();
		const message = await fx.execute(
			{
				task_key: "t1",
				description: "inspect the failing screenshot",
				images: "yes",
				model: TEXT_MODEL,
			},
			timiRegistry(),
		);
		const dirExists = fs.existsSync(taskDir(fx.root, "t1"));
		expect(message).toContain("images");
		expect(message).toContain("mw model set vision");
		expect(message).toContain("images: no");
		expect(dirExists).toBe(false);
		expect(fx.rows()).toBe(before);
		process.stdout.write(`[VERIFY] VC-006: refused=true queue_delta=${fx.rows() - before} dir_exists=${dirExists}\n`);
	});

	it("input:text,image + images:yes dispatches and writes the ordered head", async () => {
		const fx = await setupTool();
		const before = fx.rows();
		const message = await fx.execute(
			{
				task_key: "t2",
				description: "compare the mock against the render",
				images: "yes",
				model: VISION_MODEL,
			},
			timiRegistry(),
		);
		expect(message).toContain("Dispatched worker 't2'");
		expect(fx.rows()).toBe(before + 1);
		const md = taskMdOf(fx.root, "t2");
		expect(md).toMatch(/^images: yes$/m);
		const order = {
			type: lineIndex(md, "type: coding"),
			phase: lineIndex(md, "phase: EXECUTE"),
			images: lineIndex(md, "images: yes"),
			model: lineIndex(md, `model: ${VISION_MODEL}`),
		};
		expect(order.type).toBeGreaterThanOrEqual(0);
		expect(order.type).toBeLessThan(order.phase);
		expect(order.phase).toBeLessThan(order.images);
		expect(order.images).toBeLessThan(order.model);
	});

	it("auto-detects an existing png reference with a text-only model and refuses", async () => {
		const fx = await setupTool();
		plantPng(fx.root, path.join("shots", "login.png"));
		const before = fx.rows();
		const message = await fx.execute(
			{
				task_key: "t3",
				description: "match shots/login.png against the mock",
				model: TEXT_MODEL,
			},
			timiRegistry(),
		);
		expect(message).toContain("mw model set vision");
		expect(fs.existsSync(taskDir(fx.root, "t3"))).toBe(false);
		expect(fx.rows()).toBe(before);
	});

	it("auto-detected image need writes images:yes on a capable model (D-013)", async () => {
		const fx = await setupTool();
		plantPng(fx.root, path.join("shots", "login.png"));
		const before = fx.rows();
		const message = await fx.execute(
			{
				task_key: "t4",
				description: "match shots/login.png against the mock",
				model: VISION_MODEL,
			},
			timiRegistry(),
		);
		expect(message).toContain("Dispatched worker 't4'");
		expect(fx.rows()).toBe(before + 1);
		expect(taskMdOf(fx.root, "t4")).toMatch(/^images: yes$/m);
	});

	it("explicit images:no exempts a png reference on a text-only model", async () => {
		const fx = await setupTool();
		plantPng(fx.root, path.join("shots", "login.png"));
		const before = fx.rows();
		const message = await fx.execute(
			{
				task_key: "t5",
				description: "match shots/login.png against the mock",
				images: "no",
				model: TEXT_MODEL,
			},
			timiRegistry(),
		);
		expect(message).toContain("Dispatched worker 't5'");
		expect(fx.rows()).toBe(before + 1);
		expect(taskMdOf(fx.root, "t5")).toMatch(/^images: no$/m);
	});

	it("VC-008: undecidable registry lookups fail open (unknown is not no)", async () => {
		// (a) registry undefined
		const missingRegistry = await setupTool();
		let before = missingRegistry.rows();
		let message = await missingRegistry.execute({
			task_key: "t1",
			description: "inspect the screenshot",
			images: "yes",
			model: TEXT_MODEL,
		});
		expect(message).toContain("Dispatched worker 't1'");
		expect(missingRegistry.rows()).toBe(before + 1);
		before = missingRegistry.rows();

		// (b) non-pi cli (codex owns its own catalog)
		const codexCli = await setupTool();
		before = codexCli.rows();
		message = await codexCli.execute(
			{
				task_key: "t1",
				description: "inspect the screenshot",
				images: "yes",
				cli: "codex",
				model: TEXT_MODEL,
			},
			timiRegistry(),
		);
		expect(message).toContain("Dispatched worker 't1'");
		expect(codexCli.rows()).toBe(before + 1);

		// (c) CLI-executor model prefix
		const cliExecutor = await setupTool();
		before = cliExecutor.rows();
		message = await cliExecutor.execute(
			{
				task_key: "t1",
				description: "inspect the screenshot",
				images: "yes",
				model: "codex_cli/gpt-5",
			},
			// registry present on purpose: an executor prefix must stay unknown
			// even when the registry could resolve other values.
			timiRegistry(),
		);
		expect(message).toContain("Dispatched worker 't1'");
		expect(cliExecutor.rows()).toBe(before + 1);

		process.stdout.write("[VERIFY] VC-008: failopen_ok=true queue_delta=1\n");
	});

	it("writes no images: line when undeclared and no image is referenced", async () => {
		const fx = await setupTool();
		await fx.execute({ task_key: "t7", description: "refactor the dispatcher", model: TEXT_MODEL }, timiRegistry());
		const md = taskMdOf(fx.root, "t7");
		expect(md.split("\n").some((line) => line.startsWith("images:"))).toBe(false);
	});

	it("/worker --images wires the same gate (refuse, exempt, invalid value)", async () => {
		const refused = await setupCommand();
		const before = refused.rows();
		const notes = await refused.run(
			`pi --key k --images yes --model ${TEXT_MODEL} inspect the screenshot`,
			timiRegistry(),
		);
		expect(notes.join("\n")).toContain("mw model set vision");
		expect(fs.existsSync(path.join(refused.root, "k", "workers"))).toBe(false);
		expect(refused.rows()).toBe(before);

		const exempt = await setupCommand();
		plantPng(exempt.root, path.join("shots", "login.png"));
		const okNotes = await exempt.run(
			`pi --key k --images no --model ${TEXT_MODEL} match shots/login.png`,
			timiRegistry(),
		);
		expect(okNotes.join("\n")).toContain("Dispatched pi worker");
		const workers = fs.readdirSync(path.join(exempt.root, "k", "workers"));
		expect(workers).toHaveLength(1);
		expect(taskMdOf(exempt.root, workers[0] as string)).toMatch(/^images: no$/m);

		const invalid = await setupCommand();
		const invalidNotes = await invalid.run(`pi --key k --images maybe do work`, timiRegistry());
		expect(invalidNotes.join("\n")).toContain("--images must be 'yes' or 'no'");
		expect(fs.existsSync(path.join(invalid.root, "k", "workers"))).toBe(false);
	});
});

describe("vision pass-through evidence (mw-vision-role T-18, VC-007)", () => {
	it("VC-007: images:yes on a capable model adds exactly one row with an ordered head", async () => {
		const fx = await setupTool();
		const before = fx.rows();
		const message = await fx.execute(
			{
				task_key: "t1",
				description: "compare the mock against the render",
				images: "yes",
				model: VISION_MODEL,
			},
			timiRegistry(),
		);
		const dispatched = message.includes("Dispatched worker 't1'");
		const queueDelta = fx.rows() - before;
		const taskMdPath = path.join(taskDir(fx.root, "t1"), "task.md");
		const taskMdExists = fs.existsSync(taskMdPath);
		// Exact-line match, not a substring: `images: yes-ish` must not pass.
		const lines = taskMdExists ? fs.readFileSync(taskMdPath, "utf8").split("\n") : [];
		const imagesLine = lines.includes("images: yes");
		const typeIdx = lines.indexOf("type: coding");
		const phaseIdx = lines.indexOf("phase: EXECUTE");
		const imagesIdx = lines.indexOf("images: yes");
		const modelIdx = lines.indexOf(`model: ${VISION_MODEL}`);
		// Missing lines are -1, which fails every strict-increase comparison.
		const orderOk = typeIdx >= 0 && typeIdx < phaseIdx && phaseIdx < imagesIdx && imagesIdx < modelIdx;

		// Soft assertions: one control run reports every broken fact at once.
		expect.soft(dispatched).toBe(true);
		expect.soft(queueDelta).toBe(1);
		expect.soft(taskMdExists).toBe(true);
		expect.soft(imagesLine).toBe(true);
		expect.soft(orderOk).toBe(true);

		process.stdout.write(
			`[VERIFY] VC-007: queue_delta=${queueDelta} images_line=${imagesLine ? "yes" : "no"} order_ok=${orderOk}\n`,
		);
	});
});
