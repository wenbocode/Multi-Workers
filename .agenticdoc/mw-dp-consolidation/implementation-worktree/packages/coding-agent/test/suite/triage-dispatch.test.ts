/**
 * triage-dispatch.test.ts — DP-1 pre-dispatch triage wiring (mw-jev-provider-
 * integration T-03; design D-004/D-005/D-006/D-007).
 *
 * What is pinned here:
 *
 * 1. **default-off equivalence** — `.mw/decide.json` missing / `enabled=false` /
 *    `points.dp1.enabled=false` means ZERO spawn, ZERO ledger write, ZERO notify
 *    delta: `planDispatchFrontmatter` keeps its pre-T-03 bytes and the
 *    `dispatch_worker` / `/worker` receipts are byte-identical;
 * 2. **bypass advice only** — an available suggestion is appended to the
 *    receipt (with the explicit "旁路建议，未据此改派发" wording and a
 *    provenance-qualified confidence) and NEVER rewrites `type` / role / model;
 * 3. **ledger + disagreement wake** — every produced advice writes exactly one
 *    `triage-suggestion` five-tuple row; `deliverPmAlert` fires ONLY when the
 *    suggestion type differs from the dispatched type and
 *    `points.dp1.alert_on_disagreement !== false`;
 * 4. **fail-soft** — timeout / bad JSON / non-zero exit / spawn error are
 *    silent, never throw, and the dispatch still lands; unavailable writes a
 *    `triage-unavailable` row only under `triage_notify_on_unavailable=true`.
 *
 * The decision child is stubbed at the `DecideRunner` seam (no real provider
 * call, no network, no real `mw decide run`). The suite harness (faux provider)
 * is used for the CI-safety smoke check; the triage tests themselves make no
 * provider calls.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../src/core/extensions/types.ts";
import { formatDispatchAlarm } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import {
	type DecideRunner,
	type DecideRunRequest,
	DP1_ID,
	formatTriageReceipt,
	newDecisionMeta,
	type RawDecideRun,
	triageDispatchEnvelope,
} from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import {
	appendTriageReceipt,
	computeDispatchTriage,
	emitDispatchTriage,
	planDispatchFrontmatter,
	registerWorkerCommands,
	registerWorkerTools,
	windowClaimId,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { createHarness } from "./harness.ts";

const tempDirs: string[] = [];

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

// ── fixtures ────────────────────────────────────────────────────────────────

/** `.mw/decide.json` (design D-007). Omit the file entirely for the off path. */
function writeDecideJson(root: string, body: Record<string, unknown>): void {
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(root, ".mw", "decide.json"), `${JSON.stringify(body, null, 2)}\n`, "utf8");
}

function readLedger(root: string): Array<Record<string, unknown>> {
	const file = path.join(root, "_autopilot", "auto-decisions.jsonl");
	if (!fs.existsSync(file)) return [];
	return fs
		.readFileSync(file, "utf8")
		.split("\n")
		.filter((line) => line.trim() !== "")
		.map((line) => JSON.parse(line) as Record<string, unknown>);
}

/** One `mw decide run` stdout payload (design D-003 response shape). */
function decideStdout(options: {
	type?: string;
	risk?: string;
	typeConf?: number | null;
	riskConf?: number | null;
	source?: string;
	latency?: number;
}): string {
	return JSON.stringify({
		available: true,
		transport: "llm-transitional",
		model: "glm-5.3-flashx",
		confidence_source: options.source ?? "model-self-report",
		attempts: 1,
		latency_ms: options.latency ?? 12,
		answers: {
			triage_type: { value: options.type ?? "research", confidence: options.typeConf ?? 0.8 },
			triage_risk: { value: options.risk ?? "low", confidence: options.riskConf ?? 0.6 },
		},
		reason: null,
	});
}

function okRun(options: Parameters<typeof decideStdout>[0] = {}): RawDecideRun {
	return { status: 0, timedOut: false, stderr: "", stdout: decideStdout(options) };
}

interface Stub {
	run: DecideRunner;
	calls: DecideRunRequest[];
}

function stubRunner(response: RawDecideRun | (() => RawDecideRun)): Stub {
	const calls: DecideRunRequest[] = [];
	return {
		calls,
		run: (request) => {
			calls.push(request);
			return typeof response === "function" ? response() : response;
		},
	};
}

function fakePi(): {
	pi: ExtensionAPI;
	commands: Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>;
	tools: Map<string, { execute: (...args: unknown[]) => Promise<{ content: Array<{ type: string; text: string }> }> }>;
	messages: Array<{ text: string; triggerTurn: boolean }>;
} {
	const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
	const tools = new Map<
		string,
		{ execute: (...args: unknown[]) => Promise<{ content: Array<{ type: string; text: string }> }> }
	>();
	const messages: Array<{ text: string; triggerTurn: boolean }> = [];
	const pi = {
		registerCommand: (
			name: string,
			opts: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
		) => {
			commands.set(name, opts.handler);
		},
		registerTool: (tool: {
			name: string;
			execute: (...args: unknown[]) => Promise<{ content: Array<{ type: string; text: string }> }>;
		}) => {
			tools.set(tool.name, tool);
		},
		appendEntry: () => {},
		sendUserMessage: () => {},
		sendMessage: (message: { content: string }, options?: { triggerTurn?: boolean }) => {
			messages.push({ text: message.content, triggerTurn: options?.triggerTurn === true });
		},
	} as unknown as ExtensionAPI;
	return { pi, commands, tools, messages };
}

function fakeCtx(): { ctx: ExtensionCommandContext; notifications: string[] } {
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

/** Complete phase-doc set so the docs gate never masks the triage path. */
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

function writeCompliantCard(root: string, key = "k"): string {
	const dir = path.join(root, key, "tasks");
	fs.mkdirSync(dir, { recursive: true });
	const cardPath = path.join(dir, "T-00-fixture.md");
	fs.writeFileSync(
		cardPath,
		[
			"type: coding",
			"",
			"## 上下文",
			"",
			"triage fixture。种子锚点 .agenticdoc/goal.md；判据入口 pm/ui-bridge.ts:1257。",
			"",
			"## 要求",
			"",
			"AC-001 成立。",
			"",
			"## 交付格式",
			"",
			"report.md。",
			"",
			"## 写入允许面",
			"",
			"仅本任务目录下的 task.md、output.md 与 report.md。",
			"",
			"## 写入禁止面",
			"",
			"本任务目录之外的任何路径。",
			"",
			"## 验收命令",
			"",
			"node ../../node_modules/vitest/dist/cli.js --run test/suite/triage-dispatch.test.ts",
			"",
			"## 改动历史",
			"",
			"见本任务 trace.log 写入事件与 report.md 的改动清单。",
			"",
		].join("\n"),
		"utf8",
	);
	return cardPath;
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
	cardPath: string;
	cardRel: string;
	stub: Stub;
	messages: Array<{ text: string; triggerTurn: boolean }>;
	notifications: string[];
	execute: (params: Record<string, unknown>) => Promise<string>;
	runCommand: (args: string) => Promise<void>;
}

async function setupFixture(stub: Stub): Promise<ToolFixture> {
	const root = mkdtemp("atl-triage-");
	const ws = new WorkerStore(root);
	const is = new IndexStore(root);
	const { pi, commands, tools, messages } = fakePi();
	writePhaseDocs(root, "k");
	writePmState(root, "k", "EXECUTE");
	await seedKey(root, "k", windowClaimId());
	registerWorkerTools(pi, ws, new AckStore(root), is, root, { key: "k" }, root, stub.run);
	registerWorkerCommands(pi, ws, is, root, { key: "k" }, root, stub.run);
	const tool = tools.get("dispatch_worker");
	if (!tool) throw new Error("dispatch_worker not registered");
	const handler = commands.get("worker");
	if (!handler) throw new Error("/worker not registered");
	const cardPath = writeCompliantCard(root);
	const cardRel = "k/tasks/T-00-fixture.md";
	const { ctx, notifications } = fakeCtx();
	return {
		root,
		cardPath,
		cardRel,
		stub,
		messages,
		notifications,
		execute: async (params) => {
			const result = (await tool.execute(
				"id",
				{ card_path: cardPath, ...params },
				undefined,
				undefined,
				ctx as unknown as ExtensionContext,
			)) as { content: Array<{ type: string; text: string }> };
			return result.content[0]?.text ?? "";
		},
		runCommand: async (args) => {
			const withCard = args.replace(/^(\S+)\s*/, `$1 --card ${cardRel} `);
			await handler(withCard, ctx);
		},
	};
}

/** One material envelope (the dp1 producer's real payload) for client-level
 * assertions; the identity rides on `meta`, the material on the registry keys. */
function materialEnvelope(
	root: string,
	stub: Stub,
	material: Record<string, unknown> = {
		task_goal: "goal",
		task_requirements: "requirements",
		task_deliverables: "deliverables",
	},
	maxBytes?: number,
) {
	return triageDispatchEnvelope({
		projectDir: root,
		dpId: DP1_ID,
		material,
		meta: newDecisionMeta({ key: "k", taskKey: "w-material", initiatorRole: "pm" }),
		run: stub.run,
		...(maxBytes === undefined ? {} : { maxBytes }),
	});
}

function taskMdOf(root: string, taskKey: string): string {
	return fs.readFileSync(path.join(root, "k", "workers", taskKey, "task.md"), "utf8");
}

function ledgerRows(root: string, kind: string): Array<Record<string, unknown>> {
	return readLedger(root).filter((row) => row.kind === kind);
}

const basePlan = (cwd: string) => ({
	cwd,
	cli: "pi",
	provider: "timi",
	taskType: "coding",
	model: "",
	modelReason: "",
	registry: undefined,
});

// ── 1. default-off equivalence ─────────────────────────────────────────────

describe("DP-1 default-off equivalence (T-03 requirement 5)", () => {
	it("no .mw/decide.json: plan is byte-identical and spawns nothing", () => {
		const root = mkdtemp("atl-triage-off-");
		const stub = stubRunner(okRun());
		const plan = planDispatchFrontmatter({ ...basePlan(root), triageRun: stub.run });
		if (!plan.ok) throw new Error(plan.message);
		expect(plan.triage).toBeNull();
		expect(plan.frontmatter).toBe("type: coding\n");
		expect(plan.echo).toBe("model: route default (no dispatch.yml coding default)");
		expect(stub.calls).toEqual([]);
	});

	it("enabled=false / points.dp1.enabled=false are the same complete bypass", () => {
		for (const body of [{ enabled: false }, { enabled: true, points: { dp1: { enabled: false } } }]) {
			const root = mkdtemp("atl-triage-off-");
			writeDecideJson(root, body);
			const stub = stubRunner(okRun());
			const plan = planDispatchFrontmatter({ ...basePlan(root), triageRun: stub.run });
			if (!plan.ok) throw new Error(plan.message);
			expect(plan.triage).toBeNull();
			expect(stub.calls, JSON.stringify(body)).toEqual([]);
		}
	});

	it("the dispatch_worker receipt and task.md are byte-identical when disabled", async () => {
		const stub = stubRunner(okRun());
		const fx = await setupFixture(stub);
		const message = await fx.execute({ task_key: "w-off", description: "do the thing" });
		const taskPath = path.join(fx.root, "k", "workers", "w-off", "task.md");
		expect(message).toBe(
			`Dispatched worker 'w-off' (type: coding, role: coding, model: route default (no dispatch.yml coding default)) under key 'k'. Task file: ${taskPath}. Check mw_status to confirm the service is running.`,
		);
		expect(message).not.toContain("[triage]");
		expect(taskMdOf(fx.root, "w-off")).toContain("type: coding");
		expect(new WorkerStore(fx.root).readAll().map((row) => row.taskKey)).toEqual(["w-off"]);
		expect(stub.calls).toEqual([]);
		expect(fs.existsSync(path.join(fx.root, "_autopilot", "auto-decisions.jsonl"))).toBe(false);
		expect(fx.messages).toEqual([]);
	});
});

// ── 2. receipt echo (bypass advice) ────────────────────────────────────────

describe("DP-1 receipt echo (T-03 requirement 3)", () => {
	it("dispatch_worker appends the advice line with provenance and never rewrites type", async () => {
		const stub = stubRunner(okRun({ type: "research", risk: "low" }));
		const fx = await setupFixture(stub);
		writeDecideJson(fx.root, { enabled: true });
		const message = await fx.execute({ task_key: "w-hit", type: "coding", description: "do the thing" });
		expect(message).toContain("[triage] 旁路建议，未据此改派发：");
		expect(message).toContain("triage_type=research");
		expect(message).toContain("triage_risk=low");
		expect(message).toContain("模型自报置信度（不用于门控）");
		expect(message).toContain("confidence_source=model-self-report");
		// The advice never rewrites the dispatch decision (type stays coding).
		expect(message).toContain("(type: coding, role: coding,");
		expect(taskMdOf(fx.root, "w-hit")).toContain("type: coding");
		expect(stub.calls).toHaveLength(1);
	});

	it("/worker carries the same advice line", async () => {
		const stub = stubRunner(okRun({ type: "review", risk: "mid" }));
		const fx = await setupFixture(stub);
		writeDecideJson(fx.root, { enabled: true });
		await fx.runCommand("pi --type coding do the thing");
		const note = fx.notifications.at(-1) ?? "";
		expect(note).toContain("[triage] 旁路建议，未据此改派发：");
		expect(note).toContain("triage_type=review");
		expect(note).toContain("模型自报置信度（不用于门控）");
		expect(note).toContain("[type: coding, role: coding,");
	});

	it("api-sourced confidence is labelled as a usable criterion (no not-for-gating marker)", () => {
		const stub = stubRunner(okRun({ type: "coding", risk: "high", source: "api" }));
		const root = mkdtemp("atl-triage-api-");
		writeDecideJson(root, { enabled: true });
		// The producer's real material path (dp1's three registry fields).
		const triage = computeDispatchTriage({
			projectDir: root,
			dispatchedType: "coding",
			run: stub.run,
			dp1: {
				key: "k",
				taskKey: "w-api",
				taskType: "coding",
				sections: {
					context: "目标 .agenticdoc/goal.md:1",
					requirements: "AC-001",
					deliverables: "report.md",
					extras: [],
				},
			},
		});
		if (triage === null) throw new Error("expected a dp1 triage");
		expect(triage.statePath).toBe("material");
		expect(triage.receipt).toContain("置信度来源=api（可作为判据）");
		expect(triage.receipt).not.toContain("不用于门控");
	});

	it("appendTriageReceipt is identity when there is no advice", () => {
		expect(appendTriageReceipt("base", null)).toBe("base");
		expect(appendTriageReceipt("base", { receipt: "" } as never)).toBe("base");
	});
});

// ── 3. ledger + disagreement wake ──────────────────────────────────────────

describe("DP-1 ledger and disagreement wake (T-03 requirement 4)", () => {
	it("a disagreement writes one triage-suggestion row and wakes the PM once", async () => {
		const stub = stubRunner(okRun({ type: "research", risk: "low" }));
		const fx = await setupFixture(stub);
		writeDecideJson(fx.root, { enabled: true });
		await fx.execute({ task_key: "w-dis", type: "coding", description: "do the thing" });
		const rows = ledgerRows(fx.root, "triage-suggestion");
		expect(rows).toHaveLength(1);
		expect(rows[0]?.seq).toBe(1);
		expect(rows[0]?.phase).toBe("dispatch-alarm");
		expect(rows[0]?.count).toBe(1);
		expect(String(rows[0]?.detail)).toContain("triage_type=research");
		expect(String(rows[0]?.detail)).toContain("dispatched_type=coding");
		expect(String(rows[0]?.detail)).toContain("disagreement=yes");
		const wakes = fx.messages.filter((m) => m.triggerTurn);
		expect(wakes).toHaveLength(1);
		expect(wakes[0]?.text).toBe(
			formatDispatchAlarm({ kind: "triage-suggestion", count: 1, detail: String(rows[0]?.detail) }),
		);
		expect(wakes[0]?.text).toContain("提示");
	});

	it("agreement writes the row without waking the PM", async () => {
		const stub = stubRunner(okRun({ type: "coding", risk: "low" }));
		const fx = await setupFixture(stub);
		writeDecideJson(fx.root, { enabled: true });
		await fx.execute({ task_key: "w-agree", type: "coding", description: "do the thing" });
		expect(ledgerRows(fx.root, "triage-suggestion")).toHaveLength(1);
		expect(String(ledgerRows(fx.root, "triage-suggestion")[0]?.detail)).toContain("disagreement=no");
		expect(fx.messages.filter((m) => m.triggerTurn)).toEqual([]);
	});

	it("alert_on_disagreement=false keeps the row but not the wake", async () => {
		const stub = stubRunner(okRun({ type: "research", risk: "low" }));
		const fx = await setupFixture(stub);
		writeDecideJson(fx.root, { enabled: true, points: { dp1: { alert_on_disagreement: false } } });
		await fx.execute({ task_key: "w-muted", type: "coding", description: "do the thing" });
		expect(ledgerRows(fx.root, "triage-suggestion")).toHaveLength(1);
		expect(fx.messages.filter((m) => m.triggerTurn)).toEqual([]);
	});

	it("emitDispatchTriage stays best-effort on a null advice", () => {
		const root = mkdtemp("atl-triage-null-");
		const { pi } = fakePi();
		expect(() => emitDispatchTriage(pi, root, null)).not.toThrow();
		expect(fs.existsSync(path.join(root, "_autopilot"))).toBe(false);
	});
});

// ── 4. fail-soft ───────────────────────────────────────────────────────────

describe("DP-1 fail-soft (T-03 requirements 1/4)", () => {
	const failures: Array<{ name: string; raw: RawDecideRun; reason: string }> = [
		{ name: "timeout", raw: { status: null, stdout: "", stderr: "", timedOut: true }, reason: "timeout" },
		{
			name: "bad JSON",
			raw: { status: 0, stdout: "not json at all", stderr: "", timedOut: false },
			reason: "bad-response",
		},
		{
			name: "non-zero exit",
			raw: { status: 2, stdout: "", stderr: "boom", timedOut: false },
			reason: "upstream-error",
		},
		{
			name: "spawn error",
			raw: { status: null, stdout: "", stderr: "", error: "ENOENT", timedOut: false },
			reason: "upstream-error",
		},
		{
			name: "available=false upstream",
			raw: {
				status: 0,
				stdout: JSON.stringify({ available: false, reason: "rate-limited" }),
				stderr: "",
				timedOut: false,
			},
			reason: "rate-limited",
		},
	];

	for (const failure of failures) {
		it(`${failure.name}: silent, dispatch intact, never throws`, async () => {
			const stub = stubRunner(failure.raw);
			const fx = await setupFixture(stub);
			writeDecideJson(fx.root, { enabled: true });
			const message = await fx.execute({ task_key: "w-fail", type: "coding", description: "do the thing" });
			expect(message).not.toContain("[triage]");
			expect(message).toContain("Dispatched worker 'w-fail'");
			expect(taskMdOf(fx.root, "w-fail")).toContain("type: coding");
			expect(new WorkerStore(fx.root).readAll().map((row) => row.taskKey)).toEqual(["w-fail"]);
			expect(readLedger(fx.root)).toEqual([]);
			expect(fx.messages).toEqual([]);
			// Client-level normalisation carries the expected reason (material path).
			const result = materialEnvelope(fx.root, stubRunner(failure.raw));
			expect(result.available).toBe(false);
			expect(result.reason).toBe(failure.reason);
		});
	}

	it("triage_notify_on_unavailable=true writes one triage-unavailable row without waking", async () => {
		const stub = stubRunner({ status: null, stdout: "", stderr: "", timedOut: true });
		const fx = await setupFixture(stub);
		writeDecideJson(fx.root, { enabled: true, triage_notify_on_unavailable: true });
		const message = await fx.execute({ task_key: "w-na", type: "coding", description: "do the thing" });
		expect(message).not.toContain("[triage]");
		const rows = ledgerRows(fx.root, "triage-unavailable");
		expect(rows).toHaveLength(1);
		expect(String(rows[0]?.detail)).toContain("reason=timeout");
		expect(ledgerRows(fx.root, "triage-suggestion")).toEqual([]);
		expect(fx.messages).toEqual([]);
	});

	it("a throwing runner is normalised, not propagated", () => {
		const root = mkdtemp("atl-triage-throw-");
		writeDecideJson(root, { enabled: true });
		const throwing: DecideRunner = () => {
			throw new Error("kaboom");
		};
		const result = materialEnvelope(root, { run: throwing, calls: [] });
		expect(result.available).toBe(false);
		expect(result.reason).toBe("upstream-error");
	});

	it("forwards the material verbatim with no questions map, and refuses an over-budget one", () => {
		const root = mkdtemp("atl-triage-state-");
		writeDecideJson(root, { enabled: true });
		const stub = stubRunner(okRun());
		const material = {
			task_goal: "goal",
			task_requirements: `requirements ${"x".repeat(500)}`,
			task_deliverables: "deliverables",
		};
		materialEnvelope(root, stub, material);
		expect(stub.calls).toHaveLength(1);
		const payload = JSON.parse(stub.calls[0]?.input ?? "{}") as {
			material: Record<string, unknown>;
			meta: Record<string, unknown>;
		};
		// The original text is never truncated and the registry owns the questions.
		expect(payload.material).toEqual(material);
		expect(payload).not.toHaveProperty("questions");
		expect(payload.meta.task_key).toBe("w-material");
		expect(stub.calls[0]?.projectDir).toBe(root);

		// An explicitly published budget is a REFUSAL, never a truncation.
		const budgetStub = stubRunner(okRun());
		const refused = materialEnvelope(root, budgetStub, material, 40);
		expect(refused.available).toBe(false);
		expect(refused.reason).toBe("input-oversize");
		expect(refused.escalate_to_human).toBe(true);
		expect(budgetStub.calls).toHaveLength(0);
	});

	it("formatTriageReceipt is empty for an unavailable result", () => {
		expect(
			formatTriageReceipt({
				available: false,
				reason: "timeout",
				confidences: {},
				confidence_source: "unknown",
				latency_ms: 0,
			}),
		).toBe("");
	});
});

// ── 5. suite harness / faux provider (CI safety) ───────────────────────────

describe("suite harness (faux provider, no real API)", () => {
	it("the harness registers a faux provider model", async () => {
		const harness = await createHarness();
		try {
			expect(harness.getModel().provider).toBe(harness.faux.getModel().provider);
			process.stdout.write("[VERIFY] T-03 provider=faux real_network=false\n");
		} finally {
			harness.cleanup();
		}
	});
});
