import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI, ExtensionContext, ToolDefinition } from "../../src/core/extensions/types.ts";
import { createCodexDispatchAdapter } from "../../src/extensions/agent-team-loop/pm/codex-pm-workflow.ts";
import {
	registerWorkerTools,
	type WorkerDispatchAdapter,
	windowClaimId,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const temporary: string[] = [];
const KEY = "codex-counter";
const DOC = [
	"# Counter",
	"- Workflow: codex-lite",
	`- Key: ${KEY}`,
	"- Phase: EXECUTE",
	"- Claim-Id: codex",
	"- Status: active",
	"",
	"## 目标",
	"Make increment return its input plus one.",
	"## 范围",
	"Only counter.py.",
	"## 验收标准",
	"- AC-001: increment(4) returns 5.",
	"## 接续须知",
	"Dispatch the remaining implementation; then verify the result.",
	"",
].join("\n");

beforeEach(() => {
	for (const name of ["MW_TARGET_GAME", "MW_TARGET_ENGINE", "MW_PARTITION_PARENT", "MW_PARTITION_ROOT"])
		vi.stubEnv(name, "");
});

afterEach(() => {
	vi.unstubAllEnvs();
	for (const root of temporary.splice(0)) {
		const resolved = fs.realpathSync.native(root);
		if (!resolved.startsWith(fs.realpathSync.native(os.tmpdir()) + path.sep))
			throw new Error("Unexpected fixture path");
		fs.rmSync(root, { recursive: true, force: true });
	}
});

async function fixture() {
	const project = fs.mkdtempSync(path.join(os.tmpdir(), "codex-pm-workflow-"));
	temporary.push(project);
	const root = path.join(project, ".agenticdoc");
	const keyDir = path.join(root, KEY);
	fs.mkdirSync(path.join(keyDir, "tasks"), { recursive: true });
	fs.mkdirSync(path.join(project, ".mw"));
	fs.writeFileSync(path.join(project, ".mw", "decide.json"), '{"enabled":false}\n');
	fs.writeFileSync(path.join(root, "target.yml"), "active: single\n");
	const doc = path.join(keyDir, "codex_doc.md");
	fs.writeFileSync(doc, DOC);
	fs.writeFileSync(path.join(keyDir, "pm-state.md"), `- Key: ${KEY}\n- Claim-Id: codex\n- Phase: init\n`);
	const card = path.join(keyDir, "tasks", "T-01.md");
	fs.writeFileSync(
		card,
		[
			"type: coding",
			"## 上下文",
			".agenticdoc/goal.md and counter.py:1 define the contract. AC-001.",
			"## 要求",
			"Implement increment; return its input plus one.",
			"## 交付格式",
			"Update counter.py and report the result in output.md.",
			"## 写入允许面",
			"- counter.py",
			"## 写入禁止面",
			"- tests/",
			"## 验收命令",
			'```json\n["python", "check_counter.py"]\n```',
			"## 改动历史",
			"Initial task card.",
			"",
		].join("\n"),
	);
	const index = new IndexStore(root);
	await index.upsert({
		key: KEY,
		status: "active",
		phase: "EXECUTE",
		claimId: "codex",
		deps: "",
		desc: "counter",
		updated: "now",
	});
	const worker = new WorkerStore(root);
	const tools = new Map<string, ToolDefinition>();
	const pi = {
		registerTool: (tool: ToolDefinition) => tools.set(tool.name, tool),
		sendMessage: () => {},
	} as unknown as ExtensionAPI;
	function register(adapter?: WorkerDispatchAdapter) {
		registerWorkerTools(
			pi,
			worker,
			new AckStore(root),
			index,
			root,
			{ key: undefined },
			project,
			undefined,
			undefined,
			adapter,
		);
	}
	async function dispatch(extra: Record<string, unknown> = {}) {
		const tool = tools.get("dispatch_worker");
		if (!tool) throw new Error("Missing dispatch tool");
		const result = await tool.execute(
			"fixture-dispatch",
			{
				key: KEY,
				task_key: "counter-task",
				card_path: card,
				description: "Implement AC-001.",
				type: "coding",
				...extra,
			},
			undefined,
			undefined,
			{ hasUI: false } as ExtensionContext,
		);
		return result.content.flatMap((item) => (item.type === "text" ? [item.text] : [])).join("\n");
	}
	return { project, root, keyDir, doc, card, index, worker, tools, register, dispatch };
}

type Fixture = Awaited<ReturnType<typeof fixture>>;

function adapter(fx: Fixture) {
	return createCodexDispatchAdapter(fx.root, fx.index, KEY, "codex", "coding");
}

function expectNoDispatch(fx: Fixture) {
	expect(fx.worker.readAll()).toEqual([]);
	expect(fs.existsSync(path.join(fx.keyDir, "workers"))).toBe(false);
}

describe("Codex lightweight dispatch adapter", () => {
	it("dispatches without SDD documents and propagates the actual EXECUTE phase", async () => {
		const fx = await fixture();
		fx.register(adapter(fx));
		expect(await fx.dispatch()).toContain("Dispatched worker 'counter-task'");
		expect(fx.worker.readAll()).toHaveLength(1);
		const task = fs.readFileSync(path.join(fx.keyDir, "workers", "counter-task", "task.md"), "utf8");
		expect(task).toMatch(/^phase: EXECUTE$/m);
		expect(task).toContain("increment");
		expect(task).not.toContain("Dispatch the remaining implementation");
		for (const file of ["spec.md", "design.md", "plan.md"])
			expect(fs.existsSync(path.join(fx.keyDir, file))).toBe(false);
	});

	it("keeps a codex ClaimId and model-supplied workflow fields from enabling the ordinary entry", async () => {
		const fx = await fixture();
		fx.register();
		const schema = fx.tools.get("dispatch_worker")?.parameters;
		if (!schema || !("properties" in schema)) throw new Error("Expected an object schema for dispatch_worker");
		expect(schema.properties).not.toHaveProperty("workflow");
		expect(await fx.dispatch({ workflow: "codex-lite", claim_id: "codex" })).not.toContain("Dispatched worker");
		expectNoDispatch(fx);
	});

	it("keeps the normal MW SDD gate even with a Codex document and PM mode marker", async () => {
		const fx = await fixture();
		const row = fx.index.findByKey(KEY);
		if (!row) throw new Error("Missing fixture row");
		await fx.index.upsert({ ...row, claimId: windowClaimId() });
		fs.writeFileSync(path.join(fx.keyDir, "pm-state.md"), "- Phase: EXECUTE\n- PM mode: codex\n");
		fx.register();
		const refused = await fx.dispatch();
		expect(refused).toContain("missing phase documentation");
		expect(refused).toContain("spec.md missing");
		expectNoDispatch(fx);
		fs.writeFileSync(path.join(fx.keyDir, "spec.md"), `AC-001 counter behavior\n${"contract\n".repeat(80)}`);
		fs.writeFileSync(path.join(fx.keyDir, "design.md"), "design\n".repeat(100));
		const notes = path.join(fx.keyDir, "evidence", "research");
		fs.mkdirSync(notes, { recursive: true });
		fs.writeFileSync(path.join(notes, "spec-counter.md"), "Source: counter.py:1");
		fs.writeFileSync(path.join(notes, "design-counter.md"), "Source: counter.py:1");
		expect(await fx.dispatch()).toContain("Dispatched worker 'counter-task'");
	});

	it.each([
		["workflow mismatch", DOC.replace("codex-lite", "sdd")],
		["phase mismatch", DOC.replace("Phase: EXECUTE", "Phase: VERIFY")],
		["claim mismatch", DOC.replace("Claim-Id: codex", "Claim-Id: other")],
		["status mismatch", DOC.replace("Status: active", "Status: idle")],
		["duplicate machine line", `${DOC}\n- Phase: EXECUTE\n`],
		["missing goal", DOC.replace("Make increment return its input plus one.", "<!-- no goal -->")],
		["missing acceptance criterion", DOC.replace("- AC-001: increment(4) returns 5.", "<!-- - AC-001: fake -->")],
		[
			"duplicate acceptance criterion",
			DOC.replace("- AC-001: increment(4) returns 5.", "- AC-001: First.\n- AC-001: Second."),
		],
		["duplicate business section", `${DOC}\n## 目标\nAnother goal.\n`],
		["missing handoff", DOC.replace("## 接续须知", "## Other section")],
	])("refuses %s before task or queue creation", async (_label, document) => {
		const fx = await fixture();
		fs.writeFileSync(fx.doc, document);
		fx.register(adapter(fx));
		expect(await fx.dispatch()).toContain("Codex lightweight dispatch refused");
		expectNoDispatch(fx);
	});

	it.each([
		{ phase: "SPEC" },
		{ phase: "VERIFY" },
		{ phase: "DONE", status: "idle" as const },
		{ claimId: windowClaimId() },
		{ status: "idle" as const },
	])("refuses an authoritative non-dispatchable row %j", async (change) => {
		const fx = await fixture();
		const row = fx.index.findByKey(KEY);
		if (!row) throw new Error("Missing fixture row");
		await fx.index.upsert({ ...row, ...change });
		fx.register(adapter(fx));
		expect(await fx.dispatch()).toContain("Codex lightweight dispatch refused");
		expectNoDispatch(fx);
	});

	it("rejects duplicate and malformed authoritative rows", async () => {
		const fx = await fixture();
		const file = path.join(fx.root, "_index.parallel");
		const original = fs.readFileSync(file, "utf8");
		fx.register(adapter(fx));
		fs.appendFileSync(file, `| ${KEY.toUpperCase()} | active | EXECUTE | codex | | | now |\n`);
		expect(await fx.dispatch()).toContain("Expected one authoritative Codex key row");
		expectNoDispatch(fx);
		fs.writeFileSync(file, `${original}\n| broken | active | extra |\n`);
		expect(await fx.dispatch()).toContain("Codex lightweight dispatch refused");
		expectNoDispatch(fx);
	});

	it("binds the trusted adapter to its explicit key and codex claim", async () => {
		const fx = await fixture();
		fx.register(createCodexDispatchAdapter(fx.root, fx.index, KEY, "other", "coding"));
		expect(await fx.dispatch()).toContain("explicit key and ClaimId codex");
		expectNoDispatch(fx);
		fx.register(adapter(fx));
		expect(await fx.dispatch({ key: "another-key" })).toContain("explicit key and ClaimId codex");
		expectNoDispatch(fx);
	});

	it("still enforces task-card requirements after lightweight validation", async () => {
		const fx = await fixture();
		fs.writeFileSync(fx.card, "type: coding\n## 上下文\nIncomplete card.\n");
		fx.register(adapter(fx));
		expect(await fx.dispatch()).toContain("dispatch-card");
		expectNoDispatch(fx);
	});

	it("revalidates Codex state before publishing a task after pre-dispatch work", async () => {
		const fx = await fixture();
		const inspect = adapter(fx);
		let first = true;
		fx.register((key) => {
			const result = inspect(key);
			if (first && result.ok) {
				first = false;
				fs.writeFileSync(fx.doc, DOC.replace("Phase: EXECUTE", "Phase: VERIFY"));
			}
			return result;
		});
		expect(await fx.dispatch()).toContain("Codex lightweight dispatch refused");
		expectNoDispatch(fx);
	});
});
