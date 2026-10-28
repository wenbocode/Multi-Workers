/**
 * mwds-t01-worker-guard.test.ts — AC-003 (VC-009/VC-010/VC-011):
 * `/worker` now goes through the SAME `foreignLiveClaimRefusal` guard as
 * `dispatch_worker` / `advance_phase`, placed BEFORE the single write point
 * `writeDispatchTaskMd` (contract C4). A refused dispatch therefore creates no
 * task dir, writes no task.md and enqueues no queue row.
 *
 * The guard set and the refusal text share one declaration source
 * (`CROSS_KEY_READ_ONLY_SURFACES`); the coverage test below asserts the text
 * and the real call sites cannot drift apart again (the pre-AC-003 gap: the
 * text named `/worker` while the command never called the guard).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../src/core/extensions/types.ts";
import {
	CROSS_KEY_READ_ONLY,
	CROSS_KEY_READ_ONLY_ACK_NOTE,
	CROSS_KEY_READ_ONLY_SURFACES,
	foreignLiveClaimRefusal,
	registerAdvancePhaseTool,
	registerWorkerCommands,
	registerWorkerTools,
	windowClaimId,
	writeDispatchTaskMd,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const UI_BRIDGE_SOURCE_PATH = new URL("../../src/extensions/agent-team-loop/pm/ui-bridge.ts", import.meta.url);
const UI_BRIDGE_SOURCE = fs.readFileSync(UI_BRIDGE_SOURCE_PATH, "utf8");
const UI_BRIDGE_LINES = UI_BRIDGE_SOURCE.split(/\r?\n/);

const FOREIGN = "mw-foreign";

const tempDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mwds-t01-"));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

// ── fakes ───────────────────────────────────────────────────────────────────

interface NotifyRecord {
	message: string;
	level: string;
}

type CommandHandler = (args: string, ctx: ExtensionCommandContext) => Promise<void> | void;
type ToolExecute = (
	id: string,
	params: unknown,
	signal: undefined,
	onUpdate: undefined,
	ctx: ExtensionContext,
) => Promise<{ content: Array<{ type: string; text: string }>; details: unknown }>;

interface FakePi {
	pi: ExtensionAPI;
	commands: Map<string, CommandHandler>;
	tools: Map<string, { execute: ToolExecute }>;
	notifications: NotifyRecord[];
	ctx: ExtensionCommandContext;
}

function fakePi(): FakePi {
	const commands = new Map<string, CommandHandler>();
	const tools = new Map<string, { execute: ToolExecute }>();
	const notifications: NotifyRecord[] = [];
	const pi = {
		registerTool: (tool: { name: string; execute: ToolExecute }) => {
			tools.set(tool.name, tool);
		},
		registerCommand: (name: string, command: { handler: CommandHandler }) => {
			commands.set(name, command.handler);
		},
		sendMessage: () => {},
		appendEntry: () => {},
	} as unknown as ExtensionAPI;
	const ctx = {
		hasUI: true,
		ui: {
			notify: (message: string, level?: string) => {
				notifications.push({ message, level: level ?? "info" });
			},
			setWidget: () => {},
		},
		modelRegistry: undefined,
	} as unknown as ExtensionCommandContext;
	return { pi, commands, tools, notifications, ctx };
}

// ── fixtures ────────────────────────────────────────────────────────────────

/** A `_index.parallel` row whose claim cannot be this process: another host
 * makes `claimState` report "held-live" deterministically. */
function writeForeignClaim(root: string, key: string, claim = "other-host:4242"): void {
	fs.writeFileSync(
		path.join(root, "_index.parallel"),
		`| ${key} | active | EXECUTE | ${claim} | - | another window's key | 2026-10-10T00:00:00Z |\n`,
		"utf8",
	);
}

function writeOwnClaim(root: string, key: string): void {
	fs.writeFileSync(
		path.join(root, "_index.parallel"),
		`| ${key} | active | TASKS | ${windowClaimId()} | - | mine | 2026-10-10T00:00:00Z |\n`,
		"utf8",
	);
}

/** Spec-tier docs so a real key passes `dispatchDocGaps` (temp roots have no
 * goal.md, so the §0 Goal Alignment check is skipped). */
function writePhaseDocs(root: string, key: string): void {
	const keyDir = path.join(root, key);
	fs.mkdirSync(path.join(keyDir, "evidence", "research"), { recursive: true });
	fs.writeFileSync(
		path.join(keyDir, "spec.md"),
		`# Spec\n${"x".repeat(600)}\n\n| AC-001 | in x, y returns z |\n`,
		"utf8",
	);
	fs.writeFileSync(path.join(keyDir, "evidence", "research", "spec-topic-2026-01-01.md"), "# research\n", "utf8");
}

/** Sorted `<rel>=<content>` listing of the whole tree — refusal must be
 * byte-identical before/after (zero side effects). */
function snapshotTree(root: string): string[] {
	const out: string[] = [];
	const walk = (dir: string): void => {
		const entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
		for (const entry of entries) {
			const full = path.join(dir, entry.name);
			const rel = path.relative(root, full);
			if (entry.isDirectory()) {
				out.push(`${rel}/`);
				walk(full);
			} else {
				out.push(`${rel}=${fs.readFileSync(full, "utf8")}`);
			}
		}
	};
	walk(root);
	return out;
}

function workerTaskDirs(root: string, key: string): string[] {
	const workers = path.join(root, key, "workers");
	try {
		return fs.readdirSync(workers);
	} catch {
		return [];
	}
}

async function runWorkerCommand(
	root: string,
	args: string,
	watchKey: string | undefined = undefined,
	cardKey?: string,
): Promise<{ notifications: NotifyRecord[]; store: WorkerStore; tools: Map<string, { execute: ToolExecute }> }> {
	const { pi, commands, tools, notifications, ctx } = fakePi();
	const store = new WorkerStore(root);
	registerWorkerCommands(pi, store, new IndexStore(root), root, { key: watchKey }, root);
	const handler = commands.get("worker");
	if (!handler) throw new Error("/worker not registered");
	// T-02: allowed-key fixtures opt in with a compliant card + --card flag; the
	// refusal fixtures must stay card-free so their before/after tree snapshot is
	// untouched by fixture setup.
	let effectiveArgs = args;
	if (cardKey !== undefined) {
		const taskDir = path.join(root, cardKey, "tasks");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(
			path.join(taskDir, "T-00-fixture.md"),
			[
				"type: research",
				"",
				"## 上下文",
				"",
				"worker guard fixture。种子锚点 .agenticdoc/goal.md；作用点 pm/ui-bridge.ts:82 的只读守卫。",
				"",
				"## 要求",
				"",
				"AC-001 成立。",
				"",
				"## 交付格式",
				"",
				"report.md。",
				"",
				"## 唯一证据文件",
				"",
				"evidence/research/spec-worker-guard-2026-01-01.md。",
				"",
			].join("\n"),
			"utf8",
		);
		effectiveArgs = args.replace(/^(\S+)\s*/, `$1 --card ${cardKey}/tasks/T-00-fixture.md `);
	}
	await handler(effectiveArgs, ctx);
	return { notifications, store, tools };
}

// ── VC-009: refusal + zero side effects ─────────────────────────────────────

describe("AC-003 /worker cross-key guard (VC-009)", () => {
	it("refuses another window's live key with zero side effects (no taskDir, no task.md, no queue row)", async () => {
		const root = mkdtemp();
		writeForeignClaim(root, FOREIGN);
		const before = snapshotTree(root);
		const { notifications, store } = await runWorkerCommand(root, `pi --type research --key ${FOREIGN} work`);

		expect(notifications).toHaveLength(1);
		expect(notifications[0]?.level).toBe("warning");
		const text = notifications[0]?.message ?? "";
		expect(text).toContain(`[${CROSS_KEY_READ_ONLY}]`);
		expect(text).toContain(FOREIGN);
		expect(text).toContain("switch_key");

		// Zero side effects: no mkdir, no task.md, no enqueue, byte-identical tree.
		expect(workerTaskDirs(root, FOREIGN)).toEqual([]);
		expect(fs.existsSync(path.join(root, FOREIGN))).toBe(false);
		expect(store.readAll()).toEqual([]);
		expect(fs.existsSync(path.join(root, "_workers.parallel"))).toBe(false);
		const after = snapshotTree(root);
		expect(after).toEqual(before);
		console.log(
			`[VERIFY] VC-009: refused=${text.includes(`[${CROSS_KEY_READ_ONLY}]`)} side_effects=${
				JSON.stringify(after) === JSON.stringify(before) ? "none" : "changed"
			} taskdir_created=${fs.existsSync(path.join(root, FOREIGN))} queued=${store.readAll().length > 0}`,
		);
	});
});

// ── VC-010: allowed keys ────────────────────────────────────────────────────

describe("AC-003 allowed keys (VC-010)", () => {
	it("own live claim passes and dispatches", async () => {
		const root = mkdtemp();
		writeOwnClaim(root, "mw-mine");
		writePhaseDocs(root, "mw-mine");
		const { notifications, store } = await runWorkerCommand(
			root,
			"pi --type research --key mw-mine work",
			"mw-mine",
			"mw-mine",
		);

		expect(notifications.some((n) => n.message.includes(CROSS_KEY_READ_ONLY))).toBe(false);
		expect(notifications.some((n) => n.message.includes("Dispatched pi worker"))).toBe(true);
		expect(workerTaskDirs(root, "mw-mine")).toHaveLength(1);
		expect(store.readAll()).toHaveLength(1);
		expect(store.readAll()[0]?.status).toBe("pending");
		console.log("[VERIFY] VC-010: own=allow");
	});

	it("unclaimed key passes (new-key bootstrap)", async () => {
		const root = mkdtemp();
		writePhaseDocs(root, "mw-new");
		const { notifications, store } = await runWorkerCommand(
			root,
			"pi --type research --key mw-new work",
			undefined,
			"mw-new",
		);

		expect(notifications.some((n) => n.message.includes(CROSS_KEY_READ_ONLY))).toBe(false);
		expect(notifications.some((n) => n.message.includes("Dispatched pi worker"))).toBe(true);
		expect(workerTaskDirs(root, "mw-new")).toHaveLength(1);
		expect(store.readAll()).toHaveLength(1);
		console.log("[VERIFY] VC-010: unclaimed=allow");
	});

	it("_scratch passes", async () => {
		const root = mkdtemp();
		const { notifications, store } = await runWorkerCommand(
			root,
			"pi --type research --key _scratch work",
			undefined,
			"_scratch",
		);

		expect(notifications.some((n) => n.message.includes(CROSS_KEY_READ_ONLY))).toBe(false);
		expect(notifications.some((n) => n.message.includes("Dispatched pi worker"))).toBe(true);
		expect(workerTaskDirs(root, "_scratch")).toHaveLength(1);
		expect(store.readAll()).toHaveLength(1);
		console.log("[VERIFY] VC-010: scratch=allow");
	});
});

// ── VC-011: one declaration source, real call sites ─────────────────────────

describe("AC-003 refusal text vs guard call sites (VC-011)", () => {
	it("the refusal text lists exactly the declared surfaces", () => {
		const root = mkdtemp();
		writeForeignClaim(root, FOREIGN);
		const refusal = foreignLiveClaimRefusal(new IndexStore(root), FOREIGN);
		expect(refusal).not.toBeNull();
		const refusedLine = (refusal ?? "").split("\n").find((line) => line.startsWith("Refused:"));
		expect(refusedLine).toBeDefined();
		const listed = (refusedLine ?? "")
			.replace(/^Refused:\s*/, "")
			.replace(new RegExp(`,\\s*${CROSS_KEY_READ_ONLY_ACK_NOTE}\\.$`), "")
			.split(", ");
		expect(listed).toEqual([...CROSS_KEY_READ_ONLY_SURFACES]);
	});

	it("every declared surface maps to a real foreignLiveClaimRefusal call site", () => {
		// Call sites only: skip the definition line and comment lines.
		const guardSites = UI_BRIDGE_LINES.map((line, index) => ({ line: line.trim(), index })).filter(
			({ line }) =>
				line.includes("foreignLiveClaimRefusal(") &&
				!line.startsWith("//") &&
				!line.startsWith("*") &&
				!line.includes("export function "),
		);
		expect(guardSites).toHaveLength(CROSS_KEY_READ_ONLY_SURFACES.length);
		console.log(
			`[VERIFY] VC-011: declared_surfaces=${CROSS_KEY_READ_ONLY_SURFACES.length} guarded_sites=${guardSites.length}`,
		);

		const markers = [
			{ surface: "dispatch_worker", pattern: 'name: "dispatch_worker"' },
			{ surface: "/worker", pattern: 'pi.registerCommand("worker"' },
			{ surface: "advance_phase", pattern: 'name: "advance_phase"' },
		].map((marker) => ({ ...marker, pos: UI_BRIDGE_SOURCE.indexOf(marker.pattern) }));
		for (const marker of markers) expect(marker.pos, marker.surface).toBeGreaterThan(-1);

		const hit = new Set<string>();
		for (const site of guardSites) {
			const at = UI_BRIDGE_LINES.slice(0, site.index).join("\n").length;
			const enclosing = markers.filter((marker) => marker.pos < at).sort((a, b) => b.pos - a.pos)[0];
			expect(enclosing, `guard call at line ${site.index + 1} has no enclosing surface`).toBeDefined();
			hit.add(enclosing?.surface ?? "?");
		}
		expect([...hit].sort()).toEqual([...CROSS_KEY_READ_ONLY_SURFACES].sort());
	});

	it("the /worker guard sits before the single write point", () => {
		const workerStart = UI_BRIDGE_SOURCE.indexOf('pi.registerCommand("worker"');
		expect(workerStart).toBeGreaterThan(-1);
		const guardPos = UI_BRIDGE_SOURCE.indexOf("foreignLiveClaimRefusal(indexStore, ownerKey)", workerStart);
		const writePos = UI_BRIDGE_SOURCE.indexOf("writeDispatchTaskMd(", workerStart);
		expect(guardPos).toBeGreaterThan(-1);
		expect(writePos).toBeGreaterThan(-1);
		expect(guardPos).toBeLessThan(writePos);
	});
});

// ── C4: single write point ──────────────────────────────────────────────────

describe("AC-003 single write point writeDispatchTaskMd (C4)", () => {
	it("writes <key>/workers/<taskKey>/task.md with the pre-C4 bytes", () => {
		const root = mkdtemp();
		const result = writeDispatchTaskMd(
			{ agenticdocRoot: root, ownerKey: "_scratch" },
			{ taskKey: "t1", type: "research", body: "do the thing", frontmatter: "type: research\n" },
		);
		expect(result.ok).toBe(true);
		expect(result.injected).toBe(false);
		expect(result.path).toBe(path.join(root, "_scratch", "workers", "t1", "task.md"));
		expect(fs.readFileSync(result.path, "utf8")).toBe("type: research\n\ndo the thing\n");
	});

	it("both dispatch entries use it; no inline task.md write is left", () => {
		const calls = UI_BRIDGE_LINES.filter(
			(line) => line.includes("writeDispatchTaskMd(") && !line.includes("export function "),
		);
		expect(calls).toHaveLength(2);
		const inlineWrites = UI_BRIDGE_LINES.filter((line) => line.includes("fs.writeFileSync(taskMdPath"));
		expect(inlineWrites).toHaveLength(1);
	});
});

// ── regression: the shared guard still fences the other two surfaces ────────

describe("AC-003 regression: dispatch_worker / advance_phase unchanged", () => {
	it("dispatch_worker still refuses an explicit foreign key before any write", async () => {
		const root = mkdtemp();
		writeForeignClaim(root, FOREIGN);
		const { pi, tools, ctx } = fakePi();
		const store = new WorkerStore(root);
		registerWorkerTools(pi, store, new AckStore(root), new IndexStore(root), root, { key: undefined }, root);
		const tool = tools.get("dispatch_worker");
		if (!tool) throw new Error("dispatch_worker not registered");
		const result = await tool.execute(
			"id-foreign",
			{ task_key: "t-foreign", description: "work", type: "research", key: FOREIGN },
			undefined,
			undefined,
			ctx as unknown as ExtensionContext,
		);
		expect(result.content[0]?.text ?? "").toContain(`[${CROSS_KEY_READ_ONLY}]`);
		expect(workerTaskDirs(root, FOREIGN)).toEqual([]);
		expect(store.readAll()).toEqual([]);
	});

	it("advance_phase still refuses a foreign live key before the gate script runs", async () => {
		const root = mkdtemp();
		writeForeignClaim(root, FOREIGN);
		const scripts = path.join(root, ".claude", "scripts");
		fs.mkdirSync(scripts, { recursive: true });
		fs.writeFileSync(
			path.join(scripts, "advance_phase.py"),
			"import pathlib\npathlib.Path(__file__).with_name('RAN').write_text('ran', encoding='utf-8')\nprint('GATE OK')\n",
			"utf8",
		);
		const { pi, tools, ctx } = fakePi();
		registerAdvancePhaseTool(pi, root, new IndexStore(root));
		const tool = tools.get("advance_phase");
		if (!tool) throw new Error("advance_phase not registered");
		const result = await tool.execute(
			"id-advance",
			{ key: FOREIGN, target_phase: "plan" },
			undefined,
			undefined,
			ctx as unknown as ExtensionContext,
		);
		expect(result.content[0]?.text ?? "").toContain(`[${CROSS_KEY_READ_ONLY}]`);
		expect(fs.existsSync(path.join(scripts, "RAN"))).toBe(false);
	});
});
