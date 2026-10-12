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
	foreignLiveClaimRefusal,
	registerAdvancePhaseTool,
	registerWorkerTools,
	resolveOwnerKeyWithSync,
	windowClaimId,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import {
	IndexStore,
	keyNameRefusal,
	normalizeKey,
	RESERVED_INDEX_NAMES,
} from "../../src/extensions/agent-team-loop/shared/index-store.ts";
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

/** Minimal pi that records the `sendMessage` summaries `displaySummary` emits
 * (owner-resolution warnings). */
function warningPi(): { pi: ExtensionAPI; messages: string[] } {
	const messages: string[] = [];
	const pi = {
		registerTool: () => {},
		registerCommand: () => {},
		sendMessage: (m: unknown) => {
			const content = typeof m === "string" ? m : ((m as { content?: string }).content ?? "");
			messages.push(content);
		},
		notify: () => {},
	} as unknown as ExtensionAPI;
	return { pi, messages };
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

// ── AC-006 / VC-024…028, VC-043, VC-044: key name identity ────────────────

const RESERVED_EXCEPT_SCRATCH = RESERVED_INDEX_NAMES.filter((name) => normalizeKey(name) !== "_scratch");

describe("key name identity (AC-006)", () => {
	it("the reserved list is the explicit 14-name constant and every name is refused", () => {
		// Per-name cases (RQ-5's 12 + _impl_gate.log + _incidents): every name is
		// refused by the shared name gate, and the guard refuses all but _scratch.
		expect(RESERVED_INDEX_NAMES).toHaveLength(14);
		const store = new IndexStore(mkdtemp());
		for (const name of RESERVED_INDEX_NAMES) {
			expect(keyNameRefusal(name), name).not.toBeNull();
		}
		for (const name of RESERVED_EXCEPT_SCRATCH) {
			expect(foreignLiveClaimRefusal(store, name), name).not.toBeNull();
		}
		// _scratch is the ONE reserved name the guard still lets through as an
		// owner key (it stays un-claimable and un-advanceable, tested below).
		expect(foreignLiveClaimRefusal(store, "_scratch")).toBeNull();
		console.log(
			`[VERIFY] VC-043: reserved=${RESERVED_INDEX_NAMES.length} names_refused=${RESERVED_INDEX_NAMES.length} guard_allow=1`,
		);
	});

	it("a live _tmp key is refused (exempt_live_key == 0)", () => {
		const root = mkdtemp();
		writeForeignClaim(root, "_tmp");
		const store = new IndexStore(root);
		const refusal = foreignLiveClaimRefusal(store, "_tmp");
		expect(refusal).not.toBeNull();
		expect(refusal ?? "").toContain(`[${CROSS_KEY_READ_ONLY}]`);
		// The whole `_`/`.` prefix family the old exemption waved through.
		for (const name of ["_tmp", ".mw", "_index.parallel", "_workers.parallel", "_incidents"]) {
			expect(foreignLiveClaimRefusal(store, name), name).not.toBeNull();
		}
		// An illegal shape that is not reserved is refused too (`../x` traversal).
		expect(keyNameRefusal("../x")?.code).toBe("key-path-escape");
		console.log(`[VERIFY] VC-025: _tmp_live_refused=${refusal !== null} prefix_family_refused=5 traversal_refused=1`);
	});

	it("a case-variant key resolves to the same row (case_mismatch_bypass == 0)", async () => {
		const root = mkdtemp();
		writeForeignClaim(root, "mw-key"); // stored lower-case, held by another host
		const store = new IndexStore(root);
		expect(store.findByKey("MW-KEY")?.key).toBe("mw-key");
		expect(foreignLiveClaimRefusal(store, "MW-KEY")).not.toBeNull();

		// claim() must not append a second, case-variant row: it updates the row
		// the guard sees and keeps its first-written casing.
		const outcome = await store.claim("MW-KEY", windowClaimId(), () => false, { force: true });
		expect(outcome.ok).toBe(true);
		const rows = store.readAll().filter((r) => normalizeKey(r.key) === "mw-key");
		expect(rows).toHaveLength(1);
		expect(rows[0]?.key).toBe("mw-key");
		expect(rows[0]?.claimId).toBe(windowClaimId());
		// The active pointer and the guard read the same row.
		expect(store.activeEntry()?.key).toBe("mw-key");
		console.log(`[VERIFY] VC-026: rows=${rows.length} stored=${rows[0]?.key} bypass=0`);
	});

	it("upsert preserves the stored key casing (no migration)", async () => {
		const root = mkdtemp();
		fs.writeFileSync(
			path.join(root, "_index.parallel"),
			"| mw-key | idle | SPEC | | - | x | 2026-10-10T00:00:00Z |\n",
			"utf8",
		);
		const store = new IndexStore(root);
		await store.upsert({
			key: "MW-KEY",
			status: "idle",
			phase: "SPEC",
			claimId: "",
			deps: "",
			desc: "",
			updated: "2026-10-11T00:00:00Z",
		});
		const raw = fs.readFileSync(path.join(root, "_index.parallel"), "utf8");
		expect(raw).toContain("| mw-key |");
		expect(raw).not.toContain("| MW-KEY |");
		expect(store.readAll()).toHaveLength(1);
	});

	it("claim and advance_phase refuse the same names (direction consistency)", async () => {
		const root = mkdtemp();
		const store = new IndexStore(root);
		const scripts = path.join(root, ".claude", "scripts");
		fs.mkdirSync(scripts, { recursive: true });
		fs.writeFileSync(
			path.join(scripts, "advance_phase.py"),
			"import pathlib\npathlib.Path(__file__).with_name('RAN').write_text('ran', encoding='utf-8')\nprint('GATE OK')\n",
			"utf8",
		);
		const { pi, tools } = fakeToolPi();
		registerAdvancePhaseTool(pi, root, store);
		const advance = tools.get("advance_phase");
		if (!advance) throw new Error("advance_phase not registered");

		for (const name of [...RESERVED_INDEX_NAMES, "_tmp", "../x"]) {
			const named = keyNameRefusal(name);
			expect(named, name).not.toBeNull();
			const claimed = await store.claim(name, windowClaimId(), () => false);
			expect(claimed.ok, name).toBe(false);
			expect(claimed.refusal, name).toBe(named?.code);
			const adv = await advance.execute(
				`adv-${name}`,
				{ key: name, target_phase: "plan" },
				undefined,
				undefined,
				fakeToolCtx(),
			);
			expect(adv.content[0]?.text ?? "", name).not.toContain("GATE OK");
			expect(fs.existsSync(path.join(scripts, "RAN")), name).toBe(false);
		}

		// The new-key bootstrap path stays open in both: a legal, unclaimed name.
		expect(keyNameRefusal("mw-fresh")).toBeNull();
		expect((await store.claim("mw-fresh", windowClaimId(), () => false)).ok).toBe(true);
		const fresh = await advance.execute(
			"adv-fresh",
			{ key: "mw-fresh", target_phase: "plan" },
			undefined,
			undefined,
			fakeToolCtx(),
		);
		expect(fresh.content[0]?.text ?? "").toContain("GATE OK");
		console.log(
			`[VERIFY] VC-028: names_consistent=${RESERVED_INDEX_NAMES.length + 2} bootstrap_claim=ok bootstrap_advance=ok`,
		);
	});

	it("_index.md fallback to a held-live key degrades to _scratch with zero writes", () => {
		const root = mkdtemp();
		// Foreign live row, but NO active row: activeEntry() === undefined, the
		// exact A7 precondition. The `_index.md active:` pointer is the only hint.
		const docKey = "doc-key-t09-a";
		// Same foreign claim, but status idle: activeEntry() stays undefined while
		// findByKey(docKey) reports a held-live claim.
		fs.writeFileSync(
			path.join(root, "_index.parallel"),
			`| ${docKey} | idle | EXECUTE | other-host:4242 | - | doc | 2026-10-10T00:00:00Z |\n`,
			"utf8",
		);
		fs.writeFileSync(path.join(root, "_index.md"), `active: ${docKey}\n`, "utf8");
		const store = new IndexStore(root);
		expect(store.activeEntry()).toBeUndefined();
		const { pi, messages } = warningPi();

		const owner = resolveOwnerKeyWithSync(pi, store, { key: undefined }, undefined, root);
		expect(owner).toBe("_scratch");
		expect(messages.some((m) => m.includes(docKey))).toBe(true);
		// No implicit writer reached the other window's namespace.
		expect(fs.existsSync(path.join(root, docKey, "workers"))).toBe(false);
		console.log(`[VERIFY] VC-027: fallback_owner=_scratch warned=${messages.length > 0} writes=0`);
	});

	it("_index.md fallback naming a reserved name degrades to _scratch", () => {
		const root = mkdtemp();
		fs.writeFileSync(path.join(root, "_index.md"), "active: _incidents\n", "utf8");
		const store = new IndexStore(root);
		const { pi } = warningPi();
		expect(resolveOwnerKeyWithSync(pi, store, { key: undefined }, undefined, root)).toBe("_scratch");
		expect(fs.existsSync(path.join(root, "_incidents", "workers"))).toBe(false);
	});

	it("the dispatch_worker guard is unconditional while the 3 call lines stay", () => {
		const source = fs.readFileSync(
			new URL("../../src/extensions/agent-team-loop/pm/ui-bridge.ts", import.meta.url),
			"utf8",
		);
		const calls = source
			.split(/\r?\n/)
			.filter(
				(line) =>
					line.includes("foreignLiveClaimRefusal(") &&
					!line.trim().startsWith("//") &&
					!line.includes("export function "),
			);
		expect(calls).toHaveLength(3);
		// The pre-T-09 wrapper that skipped the guard for the implicit path is gone.
		expect(source).not.toContain('if ((key ?? "").trim())');
		console.log(`[VERIFY] VC-044: guard_calls=${calls.length} unconditional=1 wrapper_removed=1`);
	});
});

// ── AC-008 key-identity branch coverage (T-10 / BR-07, BR-08) ───────────────
// Re-anchored QG-B coordinates: `ui-bridge.ts:250` (the `_`/`.` prefix
// exemption) and `ui-bridge.ts:82` (the `_index.md` active fallback). Both are
// asserted at the production tool boundary, not only on the helper.

describe("AC-008 key-identity branches (BR-07/BR-08)", () => {
	it("BR-07: a live `_tmp` foreign key is refused by dispatch_worker with zero writes (ui-bridge.ts:250)", async () => {
		const root = mkdtemp();
		writeForeignClaim(root, "_tmp");
		const store = new WorkerStore(root);
		const { pi, tools } = fakeToolPi();
		registerWorkerTools(pi, store, new AckStore(root), new IndexStore(root), root, { key: undefined });
		const tool = tools.get("dispatch_worker");
		if (!tool) throw new Error("dispatch_worker not registered");

		const r = await tool.execute(
			"id-tmp",
			{ task_key: "t-tmp", description: "work", type: "research", key: "_tmp" },
			undefined,
			undefined,
			fakeToolCtx(),
		);
		const text = r.content[0]?.text ?? "";
		expect(text).toContain(`[${CROSS_KEY_READ_ONLY}]`);
		expect(text).toContain("_tmp");
		// Zero side effect: no `_tmp` namespace, no queue row/file.
		expect(fs.existsSync(path.join(root, "_tmp", "workers", "t-tmp"))).toBe(false);
		expect(store.readAll()).toEqual([]);
		expect(fs.existsSync(path.join(root, "_workers.parallel"))).toBe(false);
		console.log("[VERIFY] AC-008/BR-07: tmp_live_refused=1 writes=0");
	});

	it("BR-07: an illegal key shape is refused before mkdir (paths.ts key/taskKey)", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const { pi, tools } = fakeToolPi();
		registerWorkerTools(pi, store, new AckStore(root), new IndexStore(root), root, { key: undefined });
		const tool = tools.get("dispatch_worker");
		if (!tool) throw new Error("dispatch_worker not registered");

		for (const key of ["../x", "a/b", "C:x"]) {
			const r = await tool.execute(
				`id-${key}`,
				{ task_key: "t-esc", description: "work", type: "research", key },
				undefined,
				undefined,
				fakeToolCtx(),
			);
			const text = r.content[0]?.text ?? "";
			expect(text, key).toContain(`[${CROSS_KEY_READ_ONLY}]`);
			expect(text, key).not.toContain("Dispatched worker");
		}
		expect(store.readAll()).toEqual([]);
		// Nothing escaped the agenticdoc root.
		expect(fs.existsSync(path.resolve(root, "..", "x", "workers"))).toBe(false);
		expect(fs.existsSync(path.join(root, "a"))).toBe(false);
		console.log("[VERIFY] AC-008/BR-07: illegal_shapes_refused=3 escape_dirs=0");
	});

	it("BR-08: an implicit dispatch_worker with no active row creates nothing under the _index.md key (ui-bridge.ts:82)", async () => {
		const root = mkdtemp();
		const docKey = "doc-key-t10";
		// No active row (`activeEntry() === undefined`) but the `_index.md active:`
		// pointer names a held-live key — the exact A7 precondition.
		fs.writeFileSync(
			path.join(root, "_index.parallel"),
			`| ${docKey} | idle | EXECUTE | other-host:4242 | - | doc | 2026-10-10T00:00:00Z |\n`,
			"utf8",
		);
		fs.writeFileSync(path.join(root, "_index.md"), `active: ${docKey}\n`, "utf8");
		writePhaseDocs(root, "_scratch");
		const store = new WorkerStore(root);
		const { pi, tools } = fakeToolPi();
		registerWorkerTools(pi, store, new AckStore(root), new IndexStore(root), root, { key: undefined });
		const tool = tools.get("dispatch_worker");
		if (!tool) throw new Error("dispatch_worker not registered");

		const r = await tool.execute(
			"id-implicit",
			{ task_key: "t-implicit", description: "work", type: "research" },
			undefined,
			undefined,
			fakeToolCtx(),
		);
		const text = r.content[0]?.text ?? "";
		// The implicit path degrades to _scratch: it must not create the foreign
		// key's namespace, and the queue row belongs to _scratch.
		expect(text).not.toContain(`[${CROSS_KEY_READ_ONLY}]`);
		expect(fs.existsSync(path.join(root, docKey, "workers"))).toBe(false);
		const row = store.findByKey("t-implicit");
		expect(row?.taskPath).toContain(`${path.sep}_scratch${path.sep}`);
		console.log(
			`[VERIFY] AC-008/BR-08: fallback_owner=_scratch foreign_ns=${String(fs.existsSync(path.join(root, docKey, "workers")))}`,
		);
	});
});
