/**
 * worker-crosskey-readonly.test.ts — AC-024 (PM 跨 key 只读):
 * reading another window's key stays global and unrestricted; WRITING into it
 * is refused at the tool layer with the stable `cross-key-read-only` code.
 *
 * This is the second half of the IN-3 lesson: scope isolation must not blind the
 * PM (it still needs the whole-project status view) — it must only stop it from
 * mutating another key's namespace (dispatch / advance_phase) behind that key's
 * owner's back.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionContext } from "../../src/core/extensions/types.ts";
import {
	CROSS_KEY_READ_ONLY,
	registerAdvancePhaseTool,
	registerWorkerTools,
	windowClaimId,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { type WorkerEntry, WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const tempDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-crosskey-"));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

type ToolExecute = (
	id: string,
	params: unknown,
	signal: undefined,
	onUpdate: undefined,
	ctx: ExtensionContext,
) => Promise<{ content: Array<{ type: string; text: string }> }>;

/** Minimal tool-capturing pi — enough for registerWorkerTools/AdvancePhaseTool. */
function fakeToolPi(): { pi: ExtensionAPI; tools: Map<string, { execute: ToolExecute }> } {
	const tools = new Map<string, { execute: ToolExecute }>();
	const pi = {
		registerTool: (tool: { name: string; execute: ToolExecute }) => {
			tools.set(tool.name, tool);
		},
		sendMessage: () => {},
		notify: () => {},
	} as unknown as ExtensionAPI;
	return { pi, tools };
}

function fakeToolCtx(): ExtensionContext {
	return { hasUI: true, ui: { notify: () => {}, setWidget: () => {} } } as unknown as ExtensionContext;
}

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

/** A `_index.parallel` row whose claim cannot be this process: another host ⇒
 * `claimState` reports "held-live" deterministically, with no pid probing. */
function writeForeignClaim(root: string, key: string, claim = "other-host:4242"): void {
	fs.writeFileSync(
		path.join(root, "_index.parallel"),
		`| ${key} | active | EXECUTE | ${claim} | - | another window's key | 2026-10-10T00:00:00Z |\n`,
		"utf8",
	);
}

function runningRow(root: string, key: string, taskKey: string): WorkerEntry {
	return {
		taskKey,
		status: "running",
		cli: "pi",
		provider: "timi",
		taskPath: path.join(root, key, "workers", taskKey, "task.md"),
		dispatchedAt: "2026-10-10T00:00:00.000Z",
		updatedAt: "2026-10-10T00:00:00.000Z",
		model: "",
		origin: "manual",
	};
}

const FOREIGN = "mw-foreign";

describe("cross-key writes are refused (AC-024)", () => {
	it("dispatch_worker refuses an explicit foreign live key and writes nothing", async () => {
		const root = mkdtemp();
		writeForeignClaim(root, FOREIGN);
		const store = new WorkerStore(root);
		const { pi, tools } = fakeToolPi();
		registerWorkerTools(pi, store, new AckStore(root), new IndexStore(root), root, { key: undefined });

		const tool = tools.get("dispatch_worker");
		if (!tool) throw new Error("dispatch_worker not registered");
		const r = await tool.execute(
			"id-foreign",
			{ task_key: "t-foreign", description: "work", type: "research", key: FOREIGN },
			undefined,
			undefined,
			fakeToolCtx(),
		);
		const text = r.content[0]?.text ?? "";
		expect(text).toContain(`[${CROSS_KEY_READ_ONLY}]`);
		expect(text).toContain(FOREIGN);
		expect(text).toContain("switch_key");
		// Zero side effect: no task dir, no queue row, no queue file.
		expect(fs.existsSync(path.join(root, FOREIGN, "workers", "t-foreign"))).toBe(false);
		expect(store.readAll()).toEqual([]);
		expect(fs.existsSync(path.join(root, "_workers.parallel"))).toBe(false);
	});

	it("dispatch_worker still creates an unclaimed key (new-key bootstrap) and this window's own key", async () => {
		const root = mkdtemp();
		writePhaseDocs(root, "mw-new");
		writePhaseDocs(root, "mw-mine");
		fs.writeFileSync(
			path.join(root, "_index.parallel"),
			`| mw-mine | active | TASKS | ${windowClaimId()} | - | mine | 2026-10-10T00:00:00Z |\n`,
			"utf8",
		);
		const store = new WorkerStore(root);
		const { pi, tools } = fakeToolPi();
		registerWorkerTools(pi, store, new AckStore(root), new IndexStore(root), root, { key: "mw-mine" });
		const tool = tools.get("dispatch_worker");
		if (!tool) throw new Error("dispatch_worker not registered");

		for (const [taskKey, key] of [
			["t-new", "mw-new"],
			["t-mine", "mw-mine"],
		] as const) {
			const r = await tool.execute(
				`id-${taskKey}`,
				{ task_key: taskKey, description: "work", type: "research", key },
				undefined,
				undefined,
				fakeToolCtx(),
			);
			const text = r.content[0]?.text ?? "";
			expect(text).not.toContain(CROSS_KEY_READ_ONLY);
			expect(text).toContain(`Dispatched worker '${taskKey}'`);
			expect(store.findByKey(taskKey)?.status).toBe("pending");
		}
	});

	it("advance_phase refuses a foreign live key before the gate script runs", async () => {
		const root = mkdtemp();
		writeForeignClaim(root, FOREIGN);
		const scripts = path.join(root, ".claude", "scripts");
		fs.mkdirSync(scripts, { recursive: true });
		// The stub records that it ran: a refusal must leave no marker.
		fs.writeFileSync(
			path.join(scripts, "advance_phase.py"),
			"import pathlib, sys\npathlib.Path(__file__).with_name('RAN').write_text(' '.join(sys.argv[1:]), encoding='utf-8')\nprint('GATE OK')\n",
			"utf8",
		);
		const { pi, tools } = fakeToolPi();
		registerAdvancePhaseTool(pi, root, new IndexStore(root));
		const tool = tools.get("advance_phase");
		if (!tool) throw new Error("advance_phase not registered");

		const r = await tool.execute(
			"id-advance",
			{ key: FOREIGN, target_phase: "plan" },
			undefined,
			undefined,
			fakeToolCtx(),
		);
		expect(r.content[0]?.text ?? "").toContain(`[${CROSS_KEY_READ_ONLY}]`);
		expect(fs.existsSync(path.join(scripts, "RAN"))).toBe(false);
	});
});

describe("reading another key stays global (AC-024 reverse case)", () => {
	it("list_tasks scope all/key expose the foreign key while its writes are refused", async () => {
		const root = mkdtemp();
		writeForeignClaim(root, FOREIGN);
		const store = new WorkerStore(root);
		await store.upsert(runningRow(root, FOREIGN, "t-foreign"));
		const indexStore = new IndexStore(root);
		const { pi, tools } = fakeToolPi();
		registerWorkerTools(pi, store, new AckStore(root), indexStore, root, { key: "mw-mine" });

		const list = tools.get("list_tasks");
		const dispatch = tools.get("dispatch_worker");
		if (!list || !dispatch) throw new Error("tools not registered");

		const all = await list.execute("id-all", { scope: "all" }, undefined, undefined, fakeToolCtx());
		expect(all.content[0]?.text).toContain(`${FOREIGN} :: t-foreign | running`);

		const byKey = await list.execute("id-key", { scope: "key", key: FOREIGN }, undefined, undefined, fakeToolCtx());
		expect(byKey.content[0]?.text).toContain("t-foreign | running");

		// The whole point of the pair: same key, same window — read succeeds,
		// write is refused.
		const refused = await dispatch.execute(
			"id-write",
			{ task_key: "t-foreign-2", description: "work", type: "research", key: FOREIGN },
			undefined,
			undefined,
			fakeToolCtx(),
		);
		expect(refused.content[0]?.text ?? "").toContain(`[${CROSS_KEY_READ_ONLY}]`);
		expect(store.readAll().map((e) => e.taskKey)).toEqual(["t-foreign"]);
	});
});
