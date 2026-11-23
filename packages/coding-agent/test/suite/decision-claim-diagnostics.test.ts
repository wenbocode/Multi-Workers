/** T-01 mw-decision-claim-diagnostics — explicit claim-refusal diagnostics.
 *
 * Fully offline: a local CapturingApi drives the REAL registered execute, plus
 * one faux-provider harness integration case. Injected runner spies count every
 * decision/sign/lifecycle child; IndexStore.readAll is spied to prove one read
 * per judgment; isolated temp projects are cleaned up. No real provider, no
 * real pi/python subprocess, no index writes by the tool. */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	ASK_DECISION_BLOCKED_ACTION,
	ASK_DECISION_GUESS_DIRECTIVE,
	ASK_DECISION_PARAMETERS,
	ASK_DECISION_REASON_INPUT_INCOMPLETE,
	ASK_DECISION_TOOL,
	CLAIM_DIAGNOSIS_MESSAGE,
	CLAIM_DIAGNOSIS_RECOVERY,
	type ClaimDiagnosis,
	claimRefusalOutcome,
	DECISION_RECEIPT_TOOL,
	type DecideRunner,
	type DecideRunRequest,
	type LifecycleRunner,
	refusalOutcome,
	registerAskDecisionTool,
	runAskDecision,
	type SignRunner,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import { claimedPmKey, inspectPmClaim } from "../../src/extensions/agent-team-loop/shared/decide-policy.ts";
import { DECIDE_REGISTRY } from "../../src/extensions/agent-team-loop/shared/decide-registry.generated.ts";
import {
	type DecisionFeedback,
	parseDecisionFeedback,
} from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import { IndexStore, keyNameRefusal, normalizeKey } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { agenticdocRoot } from "../../src/extensions/agent-team-loop/shared/paths.ts";
import { createHarness, getMessageText, type Harness } from "./harness.ts";

const KEY = "mw-claim-diag";
const SELF = `${os.hostname()}:${process.pid}`;
const FOREIGN = "foreign-owner-key";
const FOREIGN_CLAIM = "other-host:999";
const TASK = "claim-diag-task";

const selfActive = `| ${KEY} | active | EXECUTE | ${SELF} | — | fixture | now |`;
const selfIdle = selfActive.replace("active", "idle");
const selfDone = selfActive.replace("active", "done");
const selfActive2 = `| ${KEY}-2 | active | EXECUTE | ${SELF} | — | fixture | now |`;
const foreignActive = `| ${FOREIGN} | active | EXECUTE | ${FOREIGN_CLAIM} | — | fixture | now |`;
const reservedActive = `| _scratch | active | EXECUTE | ${SELF} | — | fixture | now |`;

const tempDirs: string[] = [];
const harnesses: Harness[] = [];
const savedEnv = new Map<string, string | undefined>();

function mkTemp(prefix = "mw-claim-diag-"): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

function pmProject(): string {
	const root = mkTemp();
	fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(root, ".mw", "decide.json"), `${JSON.stringify({ enabled: true })}\n`, "utf8");
	return root;
}

function indexFileOf(root: string): string {
	return path.join(root, ".agenticdoc", "_index.parallel");
}

function lockFileOf(root: string): string {
	return path.join(root, ".mw", "index.lock");
}

function setIndex(root: string, content: string | null): void {
	const file = indexFileOf(root);
	if (content === null) fs.rmSync(file, { force: true });
	else fs.writeFileSync(file, content, "utf8");
}

beforeEach(() => {
	for (const name of ["PI_WORKER_TASK", "MW_PY", "MW_STUB_SEEN"]) savedEnv.set(name, process.env[name]);
	delete process.env.PI_WORKER_TASK;
	delete process.env.MW_PY;
	delete process.env.MW_STUB_SEEN;
});

afterEach(() => {
	for (const [name, value] of savedEnv) {
		if (value === undefined) delete process.env[name];
		else process.env[name] = value;
	}
	savedEnv.clear();
	while (harnesses.length > 0) harnesses.pop()?.cleanup();
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	vi.restoreAllMocks();
});

// ── minimal, schema-valid dp-auto material / preparation ─────────────────────

function dpAutoMaterial(): Record<string, unknown> {
	return {
		question: "Which option should the PM take?",
		background: {
			task_goal: "diagnose the claim refusal",
			current_state: "index row is not an active self claim",
			tried: "the ask was refused locally",
			unknowns: "whether the index is missing or malformed",
			constraints: "fail-closed, no auto-retry",
		},
		handling_options: [
			{
				id: "c1",
				label: "continue",
				description: "stay in scope",
				consequence: "keeps scope",
				risk: "low",
				conditions: "within budget",
			},
			{
				id: "c2",
				label: "ask pm",
				description: "hand to PM",
				consequence: "escalates",
				risk: "low",
				conditions: "within budget",
			},
		],
	};
}

function dpAutoPreparation(): Record<string, unknown> {
	return {
		prepared_at: "2026-10-25T10:00:00Z",
		basis_catalog: [
			{
				id: "reason",
				text: "Review the referenced evidence",
				material_refs: ["question"],
				applies_to: ["c1", "c2"],
			},
		],
	};
}

function askParams(requested: string | undefined): Record<string, unknown> {
	return {
		dp: "dp-auto",
		trigger: "claim-diag#ckpt1",
		material: dpAutoMaterial(),
		preparation: dpAutoPreparation(),
		...(requested !== undefined ? { key: requested } : {}),
	};
}

// ── injected runner spies (no real provider / subprocess) ───────────────────

interface Spies {
	decide: DecideRunner;
	lifecycle: LifecycleRunner;
	sign: SignRunner;
	decideCalls: unknown[];
	lifecycleCalls: unknown[];
	signCalls: unknown[];
}

function spies(): Spies {
	const decideCalls: unknown[] = [];
	const lifecycleCalls: unknown[] = [];
	const signCalls: unknown[] = [];
	const decide: DecideRunner = async (request) => {
		decideCalls.push(request);
		const env = JSON.parse(request.input) as {
			meta: { logical_id: string };
			preparation?: { basis_catalog?: Array<{ id: string }> };
		};
		const basisId = env.preparation?.basis_catalog?.[0]?.id ?? "reason";
		const answers =
			request.dp === "dp-w-check-task"
				? { reachability: { value: "continue" }, basis_id: { value: basisId } }
				: { handling: { value: "c2", confidence: 0.9 }, basis_id: { value: basisId } };
		return {
			status: 0,
			stdout: JSON.stringify({
				available: true,
				file_evidence: [],
				mode: "auto",
				acted: false,
				confidence_source: "api",
				latency_ms: 5,
				decision_id: `${request.dp}:${env.meta.logical_id}`,
				answers,
			}),
			stderr: "",
			timedOut: false,
		};
	};
	const lifecycle: LifecycleRunner = async (request) => {
		lifecycleCalls.push(request);
		const env = JSON.parse(request.input) as { stage?: string };
		return {
			status: 0,
			stdout: JSON.stringify({
				stage: env.stage ?? "consumed",
				status: "written",
				recorded: true,
				duplicate: false,
			}),
			stderr: "",
			timedOut: false,
		};
	};
	const sign: SignRunner = async (request) => {
		signCalls.push(request);
		return { status: 0, stdout: "{}", stderr: "", timedOut: false };
	};
	return { decide, lifecycle, sign, decideCalls, lifecycleCalls, signCalls };
}

// ── local CapturingApi: calls the REAL registered execute ────────────────────

interface CapturedTool {
	name: string;
	parameters: unknown;
	promptGuidelines?: string[];
	description?: string;
	execute: (
		toolCallId: string,
		params: Record<string, unknown>,
		signal?: AbortSignal,
	) => Promise<{ content: Array<{ type: "text"; text: string }>; details: unknown; terminate?: boolean }>;
}

type CapturedHandler = (event: unknown, ctx: unknown) => unknown;

class CapturingApi {
	readonly tools = new Map<string, CapturedTool>();
	readonly handlers = new Map<string, CapturedHandler[]>();
	active: string[] = [];
	registerTool(tool: unknown): void {
		const captured = tool as CapturedTool;
		this.tools.set(captured.name, captured);
	}
	on(event: string, handler: CapturedHandler): void {
		const list = this.handlers.get(event) ?? [];
		list.push(handler);
		this.handlers.set(event, list);
	}
	getActiveTools(): string[] {
		return [...this.active];
	}
	setActiveTools(names: string[]): void {
		this.active = [...names];
	}
	fire(event: string): void {
		for (const handler of this.handlers.get(event) ?? []) handler({ type: event }, {});
	}
}

function pmTools(projectDir: string) {
	const spy = spies();
	const capture = new CapturingApi();
	const handle = registerAskDecisionTool(capture as unknown as ExtensionAPI, {
		projectDir,
		initiatorRole: "pm",
		runner: spy.decide,
		lifecycleRunner: spy.lifecycle,
		signRunner: spy.sign,
	});
	const ask = capture.tools.get(ASK_DECISION_TOOL);
	const receipt = capture.tools.get(DECISION_RECEIPT_TOOL);
	if (ask === undefined || receipt === undefined) throw new Error("tools were not registered");
	return { capture, handle, spy, ask, receipt };
}

function firstLine(text: string): string {
	return text.split("\n")[0] ?? "";
}

function payloadOf(text: string): Record<string, unknown> {
	return JSON.parse(firstLine(text)) as Record<string, unknown>;
}

interface Diagnosis {
	reason: string;
	message: string;
	recovery: string;
}

function diagnosisOf(payload: Record<string, unknown>): Diagnosis {
	return payload.claim_diagnosis as Diagnosis;
}

const PM_CLAIM_EXPLANATIONS: Record<string, string> = {
	"index-empty-or-unparseable":
		"PM 认领校验未通过：本次索引读取返回 0 行；索引缺失、空文件或全部数据行损坏在既有读取器下无法区分，具体状态 unknown，不得据空结果猜测具体原因。",
	"index-unreadable":
		"PM 认领校验未通过：本次索引读取抛出异常，底层原因 unknown；该状态不等同于索引缺失、空文件或全部数据行损坏，也不输出异常内容。",
	"invalid-key": "PM 认领校验未通过：解析到的 key 名称不符合现有注册约束。",
	"ambiguous-claim": "PM 认领校验未通过：满足本次判定的 active 认领或同名 key 行不唯一，无法解析出唯一绑定。",
	"key-not-found": "PM 认领校验未通过：请求 key 在已解析索引行中不存在。",
	"key-inactive": "PM 认领校验未通过：请求 key 对应行不是 active。",
	"foreign-owner": "PM 认领校验未通过：请求 key 对应的 active 行由另一窗口持有。",
	"no-active-claim": "PM 认领校验未通过：已解析索引中没有本窗口唯一 active 认领。",
};

const PM_RECOVERY_ADVICE = [
	"claim/switch",
	"重建本窗口 active 认领",
	"等待持有窗口释放",
	"带外修复协调索引",
	"修索引",
	"自动重试",
];

function expectNoPmRecoveryAdvice(label: string, payload: Record<string, unknown>, text: string): Diagnosis {
	const diagnosis = diagnosisOf(payload);
	const serialized = JSON.stringify(diagnosis);
	for (const marker of PM_RECOVERY_ADVICE) {
		expect(serialized, `${label}: payload ${marker}`).not.toContain(marker);
		expect(text, `${label}: text ${marker}`).not.toContain(marker);
	}
	return diagnosis;
}

/** The ORIGINAL predicate, copied verbatim, is the equivalence oracle. */
function legacyClaimedPmKey(projectDir: string, requested?: string): string | undefined {
	try {
		const self = currentClaimId();
		const rows = new IndexStore(agenticdocRoot(projectDir)).readAll();
		const eligible = rows.filter(
			(row) =>
				row.status === "active" &&
				row.claimId === self &&
				(requested === undefined || normalizeKey(requested) === normalizeKey(row.key)),
		);
		if (eligible.length !== 1) return undefined;
		const key = eligible[0].key;
		if (keyNameRefusal(key) || rows.filter((row) => normalizeKey(row.key) === normalizeKey(key)).length !== 1)
			return undefined;
		return key;
	} catch {
		return undefined;
	}
}

const INDEX_UNREADABLE_SECRET = "EACCES-synthetic-do-not-leak";

describe("claim refusal diagnostics — VC-001 precise reasons", () => {
	it("maps every refusal shape to a reason-specific message/recovery (no leaks)", async () => {
		const root = pmProject();
		const cases: Array<{ name: string; index: string | null; requested: string | undefined; reason: string }> = [
			{ name: "empty index", index: "", requested: KEY, reason: "index-empty-or-unparseable" },
			{ name: "missing index file", index: null, requested: KEY, reason: "index-empty-or-unparseable" },
			{
				name: "only comment/header/malformed lines",
				index: "# comment\n| Key | status | phase | claimId | deps | desc | updated |\n--- | ---\nbroken line",
				requested: KEY,
				reason: "index-empty-or-unparseable",
			},
			{ name: "foreign owner for requested key", index: foreignActive, requested: FOREIGN, reason: "foreign-owner" },
			{
				name: "self+foreign, requested foreign",
				index: `${selfActive}\n${foreignActive}`,
				requested: FOREIGN,
				reason: "foreign-owner",
			},
			{ name: "self idle", index: selfIdle, requested: KEY, reason: "key-inactive" },
			{ name: "self done", index: selfDone, requested: KEY, reason: "key-inactive" },
			{ name: "requested key absent", index: foreignActive, requested: KEY, reason: "key-not-found" },
			{
				name: "requested key absent among rows",
				index: `${selfActive}\n${foreignActive}`,
				requested: "no-such-key",
				reason: "key-not-found",
			},
			{
				name: "two self-active rows, no key",
				index: `${selfActive}\n${selfActive2}`,
				requested: undefined,
				reason: "ambiguous-claim",
			},
			{ name: "duplicate key rows", index: `${selfActive}\n${selfIdle}`, requested: KEY, reason: "ambiguous-claim" },
			{ name: "reserved key name", index: reservedActive, requested: undefined, reason: "invalid-key" },
			{ name: "only foreign active, no key", index: foreignActive, requested: undefined, reason: "no-active-claim" },
			{ name: "only self idle, no key", index: selfIdle, requested: undefined, reason: "no-active-claim" },
		];
		for (const c of cases) {
			setIndex(root, c.index);
			const t = pmTools(root);
			const result = await t.ask.execute("call", askParams(c.requested));
			const text = result.content[0]?.text ?? "";
			const payload = payloadOf(text);
			expect(payload.available, c.name).toBe(false);
			expect(payload.unavailable, c.name).toBe(ASK_DECISION_REASON_INPUT_INCOMPLETE);
			expect(payload.action, c.name).toBe(ASK_DECISION_BLOCKED_ACTION);
			expect(payload.missing_fields, c.name).toBeUndefined();
			const d = diagnosisOf(payload);
			expect(d.reason, c.name).toBe(c.reason);
			const expected = PM_CLAIM_EXPLANATIONS[c.reason] ?? "";
			expect(expected, c.name).not.toBe("");
			expect(d.message, c.name).toContain(CLAIM_DIAGNOSIS_MESSAGE);
			expect(d.message, c.name).toContain(expected);
			expect(d.recovery, c.name).toBe(CLAIM_DIAGNOSIS_RECOVERY);
			// claimRefusalOutcome must emit the supplied diagnosis, not fixed PM text.
			expect(text, c.name).toContain(d.message);
			expect(text, c.name).toContain(d.recovery);
			// Fixed explanation names meta.key only to say it is NOT a material field.
			expect(d.message).toContain("meta.key");
			// Generic no-guessing directive is kept.
			expect(text).toContain(ASK_DECISION_GUESS_DIRECTIVE);
			// No other owner/key list, no absolute path, no raw exception.
			expect(text, c.name).not.toContain(FOREIGN);
			expect(text, c.name).not.toContain(FOREIGN_CLAIM);
			expect(text, c.name).not.toContain(root);
			// Zero spawns on every refusal.
			expect(t.spy.decideCalls, c.name).toHaveLength(0);
			expect(t.spy.lifecycleCalls, c.name).toHaveLength(0);
			expect(t.spy.signCalls, c.name).toHaveLength(0);
			// F4: only missing / empty / all-bad-lines are indistinguishable here.
			if (c.reason === "index-empty-or-unparseable") {
				expect(d.message).toContain("unknown");
				expect(d.message).toContain("索引缺失、空文件或全部数据行损坏");
				expect(d.message).toContain("无法区分");
				expect(d.message).not.toContain("抛出异常");
				expect(d.message).not.toContain("不可读");
			}
		}
		// readAll throwing is ONLY "unreadable"; the raw exception never leaks.
		vi.spyOn(IndexStore.prototype, "readAll").mockImplementation(() => {
			throw new Error(INDEX_UNREADABLE_SECRET);
		});
		const thrown = pmTools(root);
		const thrownResult = await thrown.ask.execute("call", askParams(KEY));
		const thrownText = thrownResult.content[0]?.text ?? "";
		const thrownPayload = payloadOf(thrownText);
		expect(thrownPayload.available).toBe(false);
		const thrownDiagnosis = diagnosisOf(thrownPayload);
		expect(thrownDiagnosis.reason).toBe("index-unreadable");
		expect(thrownDiagnosis.message).toContain(PM_CLAIM_EXPLANATIONS["index-unreadable"] ?? "");
		expect(thrownDiagnosis.message).toContain("本次索引读取抛出异常");
		expect(thrownDiagnosis.message).toContain("底层原因 unknown");
		expect(thrownDiagnosis.message).not.toContain("无法区分");
		expect(thrownDiagnosis.recovery).toBe(CLAIM_DIAGNOSIS_RECOVERY);
		expect(thrownText).toContain(thrownDiagnosis.message);
		expect(thrownText).toContain(thrownDiagnosis.recovery);
		expect(thrownText).not.toContain(INDEX_UNREADABLE_SECRET);
		expect(thrownText).not.toContain("Error:");
		expect(thrownText).toContain(ASK_DECISION_GUESS_DIRECTIVE);
		// F1: the refusal text is built from the ACTUAL diagnosis object.
		const customDiagnosis: ClaimDiagnosis = {
			reason: "worker-key-mismatch",
			message: "CUSTOM_DIAGNOSIS_MESSAGE",
			recovery: "CUSTOM_DIAGNOSIS_RECOVERY",
		};
		const customOutcome = claimRefusalOutcome("dp-auto", customDiagnosis);
		expect(firstLine(customOutcome.text)).toBe(JSON.stringify(customOutcome.payload));
		expect(payloadOf(customOutcome.text).claim_diagnosis).toEqual(customDiagnosis);
		expect(customOutcome.text).toContain(customDiagnosis.message);
		expect(customOutcome.text).toContain(customDiagnosis.recovery);
		expect(customOutcome.text).toContain(ASK_DECISION_GUESS_DIRECTIVE);
		expect(customOutcome.text).not.toContain(CLAIM_DIAGNOSIS_MESSAGE);
		expect(customOutcome.text).not.toContain(CLAIM_DIAGNOSIS_RECOVERY);
		expect(customOutcome.spawned).toBe(false);
		process.stdout.write("[VERIFY] VC-001: claim_diagnostics=pass\n");
	});
});

describe("claim refusal diagnostics — VC-002 zero side effects, one read", () => {
	it("ask refusal: zero children, readAll once, index bytes/lock unchanged, no terminal on repeats", async () => {
		const root = pmProject();
		setIndex(root, selfIdle); // key-inactive
		const before = fs.readFileSync(indexFileOf(root));
		const readSpy = vi.spyOn(IndexStore.prototype, "readAll");
		const t = pmTools(root);
		// Three consecutive claim refusals must NOT touch the counter / terminal.
		for (let i = 0; i < 3; i++) {
			const result = await t.ask.execute(`call-${i}`, askParams(KEY));
			expect(result.terminate).toBeUndefined();
			expect(result.content[0]?.text).not.toContain("TERMINAL");
			expect(payloadOf(result.content[0]?.text ?? "").claim_diagnosis).toBeDefined();
		}
		expect(t.handle.counter.countFor("dp-auto")).toBe(0);
		expect(t.spy.decideCalls).toHaveLength(0);
		expect(t.spy.lifecycleCalls).toHaveLength(0);
		expect(t.spy.signCalls).toHaveLength(0);
		// One read per judgment (3 judgments), never a second diagnostic read.
		expect(readSpy).toHaveBeenCalledTimes(3);
		// One isolated judgment reads exactly once.
		readSpy.mockClear();
		await t.ask.execute("single", askParams(KEY));
		expect(readSpy).toHaveBeenCalledTimes(1);
		// The tool never writes the index and never takes a lock.
		expect(fs.readFileSync(indexFileOf(root)).equals(before)).toBe(true);
		expect(fs.existsSync(lockFileOf(root))).toBe(false);
	});

	it("known-decision receipt refusal: no new children, index bytes/lock unchanged", async () => {
		const root = pmProject();
		setIndex(root, selfActive); // valid claim for a first, successful ask
		const t = pmTools(root);
		const confirmed = payloadOf((await t.ask.execute("ask-ok", askParams(undefined))).content[0]?.text ?? "");
		expect(confirmed.available).toBe(true);
		if (!confirmed.available) throw new Error("expected a decision for the valid claim");
		expect(confirmed.claim_diagnosis).toBeUndefined(); // no leak on the success path
		const decideAfterAsk = t.spy.decideCalls.length;
		const lifecycleAfterAsk = t.spy.lifecycleCalls.length;
		const signAfterAsk = t.spy.signCalls.length;
		// Flip the index to a foreign-only row, then snapshot.
		setIndex(root, foreignActive);
		const before = fs.readFileSync(indexFileOf(root));
		const receiptResult = await t.receipt.execute("receipt-1", {
			decision_id: confirmed.decision_id,
			stage: "executed",
			action: "record",
		});
		const receiptText = receiptResult.content[0]?.text ?? "";
		expect(receiptText).toContain("claim_diagnosis");
		expect(receiptText).toContain("key-not-found");
		expect(receiptText).not.toContain('"missing_fields"');
		const details = receiptResult.details as { status?: string; claim_diagnosis?: Diagnosis };
		expect(details.status).toBe("refused");
		expect(details.claim_diagnosis?.reason).toBe("key-not-found");
		// Zero NEW decision/sign/lifecycle activity from the refusal.
		expect(t.spy.decideCalls).toHaveLength(decideAfterAsk);
		expect(t.spy.lifecycleCalls).toHaveLength(lifecycleAfterAsk);
		expect(t.spy.signCalls).toHaveLength(signAfterAsk);
		expect(fs.readFileSync(indexFileOf(root)).equals(before)).toBe(true);
		expect(fs.existsSync(lockFileOf(root))).toBe(false);
	});

	it("faux-provider harness: a claim refusal reaches the real execute with zero spawns", async () => {
		const root = pmProject();
		setIndex(root, "");
		const before = fs.readFileSync(indexFileOf(root));
		const spy = spies();
		const harness = await createHarness({
			extensionFactories: [
				(pi) => {
					registerAskDecisionTool(pi, {
						projectDir: root,
						initiatorRole: "pm",
						runner: spy.decide,
						lifecycleRunner: spy.lifecycle,
						signRunner: spy.sign,
					});
				},
			],
		});
		harnesses.push(harness);
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall(ASK_DECISION_TOOL, askParams(KEY))], { stopReason: "toolUse" }),
			fauxAssistantMessage("done"),
		]);
		await harness.session.prompt("Check this request.");
		const result = harness.session.messages.filter((message) => message.role === "toolResult").at(-1);
		const text = getMessageText(result);
		const payload = payloadOf(text);
		expect(payload.available).toBe(false);
		expect(diagnosisOf(payload).reason).toBe("index-empty-or-unparseable");
		expect(spy.decideCalls).toHaveLength(0);
		expect(spy.lifecycleCalls).toHaveLength(0);
		expect(spy.signCalls).toHaveLength(0);
		expect(fs.readFileSync(indexFileOf(root)).equals(before)).toBe(true);
		expect(fs.existsSync(lockFileOf(root))).toBe(false);
		process.stdout.write("[VERIFY] VC-002: refusal_side_effects=0\n");
	});
});

describe("claim refusal diagnostics — VC-003 authorization equivalence + legal paths", () => {
	it("claimedPmKey and inspectPmClaim().key equal the original predicate over the full matrix", () => {
		const root = pmProject();
		const variants: Array<{ name: string; index: string | null; requested: string | undefined }> = [
			{ name: "empty", index: "", requested: KEY },
			{ name: "missing", index: null, requested: KEY },
			{ name: "valid explicit key", index: selfActive, requested: KEY },
			{ name: "valid omitted key", index: selfActive, requested: undefined },
			{ name: "case + whitespace", index: selfActive, requested: `  ${KEY.toUpperCase()}  ` },
			{ name: "valid with foreign row", index: `${selfActive}\n${foreignActive}`, requested: undefined },
			{ name: "valid with partial bad rows", index: `${selfActive}\n# comment\nbroken | line`, requested: KEY },
			{ name: "self idle", index: selfIdle, requested: KEY },
			{ name: "foreign owner", index: foreignActive, requested: FOREIGN },
			{ name: "duplicate key rows", index: `${selfActive}\n${selfIdle}`, requested: KEY },
			{ name: "ambiguous self claims", index: `${selfActive}\n${selfActive2}`, requested: undefined },
			{ name: "reserved name", index: reservedActive, requested: undefined },
		];
		for (const v of variants) {
			setIndex(root, v.index);
			const legacy = legacyClaimedPmKey(root, v.requested);
			expect(claimedPmKey(root, v.requested), v.name).toBe(legacy);
			expect(inspectPmClaim(root, v.requested).key, v.name).toBe(legacy);
		}
		// Partial bad rows do NOT introduce a new refusal: the valid self row still authorizes.
		setIndex(root, `${selfActive}\n# comment\nbroken | line`);
		expect(claimedPmKey(root, KEY)).toBe(KEY);
		expect(inspectPmClaim(root, KEY).reason).toBe("ok");
	});

	it("legal PM (valid claim) succeeds with no diagnosis leak; worker/role refusals never fake a PM claim", async () => {
		const root = pmProject();
		setIndex(root, selfActive);
		const pm = pmTools(root);
		for (const requested of [undefined, KEY, `  ${KEY.toUpperCase()}  `]) {
			const result = await pm.ask.execute("pm-ok", askParams(requested));
			const payload = payloadOf(result.content[0]?.text ?? "");
			expect(payload.available).toBe(true);
			expect(payload.claim_diagnosis).toBeUndefined();
		}

		// Worker with a card-derived ownerKey: mismatched key -> worker-key-mismatch
		// (NOT any PM claim reason); matching key proceeds unchanged (no diagnosis).
		const taskPath = path.join(root, ".agenticdoc", KEY, "workers", TASK, "task.md");
		fs.mkdirSync(path.dirname(taskPath), { recursive: true });
		fs.writeFileSync(taskPath, "type: coding\n\n## 上下文\n\nfixture\n", "utf8");
		const workerSpy = spies();
		const workerCapture = new CapturingApi();
		registerAskDecisionTool(workerCapture as unknown as ExtensionAPI, {
			projectDir: root,
			taskPath,
			runner: workerSpy.decide,
			lifecycleRunner: workerSpy.lifecycle,
			signRunner: workerSpy.sign,
		});
		const workerAsk = workerCapture.tools.get(ASK_DECISION_TOOL);
		if (workerAsk === undefined) throw new Error("worker ask tool not registered");
		const mismatchResult = await workerAsk.execute("w-1", askParams("wrong-key"));
		const mismatchText = mismatchResult.content[0]?.text ?? "";
		const mismatch = payloadOf(mismatchText);
		expect(mismatch.available).toBe(false);
		const mismatchDiagnosis = expectNoPmRecoveryAdvice("worker-key-mismatch", mismatch, mismatchText);
		expect(mismatchDiagnosis.reason).toBe("worker-key-mismatch");
		expect(["key-inactive", "foreign-owner", "no-active-claim", "index-empty-or-unparseable"]).not.toContain(
			mismatchDiagnosis.reason,
		);
		expect(mismatch.missing_fields).toBeUndefined();
		expect(mismatchDiagnosis.message).toContain("请求 key 与卡路径派生的 ownerKey 不一致");
		expect(mismatchDiagnosis.message).not.toContain("PM 认领校验未通过");
		expect(mismatchDiagnosis.message).not.toContain("索引读取");
		expect(mismatchDiagnosis.recovery).toContain("由所属 PM 核对原 task 卡 ownerKey");
		expect(mismatchDiagnosis.recovery).toContain("派发身份");
		expect(mismatchText).toContain(mismatchDiagnosis.message);
		expect(mismatchText).toContain(mismatchDiagnosis.recovery);
		expect(workerSpy.decideCalls).toHaveLength(0);

		// A PM-only dp with a valid worker key stays role-forbidden; it is NOT a success proof.
		const matchedResult = await workerAsk.execute("w-2", askParams(KEY));
		const matched = payloadOf(matchedResult.content[0]?.text ?? "");
		expect(matched.unavailable).toBe("role-forbidden");
		expect(matched.claim_diagnosis).toBeUndefined();
		expect(workerSpy.decideCalls).toHaveLength(0);

		// An unknown role is never told it needs a PM claim / index repair / retry.
		const unknownCapture = new CapturingApi();
		const unknownSpy = spies();
		registerAskDecisionTool(unknownCapture as unknown as ExtensionAPI, {
			projectDir: root,
			initiatorRole: "unknown",
			runner: unknownSpy.decide,
			lifecycleRunner: unknownSpy.lifecycle,
			signRunner: unknownSpy.sign,
		});
		const unknownAsk = unknownCapture.tools.get(ASK_DECISION_TOOL);
		if (unknownAsk === undefined) throw new Error("unknown ask tool not registered");
		const unknownResult = await unknownAsk.execute("u-1", askParams(KEY));
		const unknownText = unknownResult.content[0]?.text ?? "";
		const unknownPayload = payloadOf(unknownText);
		expect(unknownPayload.available).toBe(false);
		const unknownDiagnosis = expectNoPmRecoveryAdvice("unknown-role", unknownPayload, unknownText);
		expect(unknownDiagnosis.reason).toBe("unknown-role");
		expect(unknownDiagnosis.message).toContain("注册窗口角色或 task 卡 type 未识别");
		expect(unknownDiagnosis.message).not.toContain("PM 认领校验未通过");
		expect(unknownDiagnosis.message).not.toContain("索引读取");
		expect(unknownDiagnosis.recovery).toContain("核对注册窗口角色与 task 卡 type 的派发身份");
		expect(unknownText).toContain(unknownDiagnosis.message);
		expect(unknownText).toContain(unknownDiagnosis.recovery);
		expect(unknownSpy.decideCalls).toHaveLength(0);
		expect(unknownSpy.lifecycleCalls).toHaveLength(0);
		expect(unknownSpy.signCalls).toHaveLength(0);

		// 越权: a worker cannot reach a PM-only dp; role-forbidden stays zero-spawn
		// and the diagnosis never supplies a forged meta entry (no meta.key param).
		const overreach = await runAskDecision({
			projectDir: root,
			dp: "dp-pm-steer",
			trigger: "overreach#ckpt1",
			material: { task_goal: "g", task_requirements: "r", task_deliverables: "d", pm_decision_background: "b" },
			preparation: {
				prepared_at: "2026-10-25T10:00:00Z",
				basis_catalog: [
					{
						id: "r",
						text: "t",
						material_refs: ["task_goal"],
						applies_to: ["narrow", "split", "direct-exec", "escalate"],
					},
				],
			},
			initiatorRole: "coding",
			key: KEY,
			taskKey: TASK,
			runner: unknownSpy.decide,
			lifecycleRunner: unknownSpy.lifecycle,
		});
		expect(overreach.spawned).toBe(false);
		expect(payloadOf(overreach.text).unavailable).toBe("role-forbidden");
		expect(JSON.stringify(ASK_DECISION_PARAMETERS)).not.toContain("meta.key");
	});

	it("legal worker succeeds on dp-w-check-task with schema material, basis and correlated lifecycle", async () => {
		const root = pmProject();
		setIndex(root, null);
		const readSpy = vi.spyOn(IndexStore.prototype, "readAll");
		const taskPath = path.join(root, ".agenticdoc", KEY, "workers", TASK, "task.md");
		fs.mkdirSync(path.dirname(taskPath), { recursive: true });
		fs.writeFileSync(taskPath, "type: coding\n\n## 上下文\n\nfixture\n", "utf8");
		const workerSpy = spies();
		const workerCapture = new CapturingApi();
		registerAskDecisionTool(workerCapture as unknown as ExtensionAPI, {
			projectDir: root,
			taskPath,
			runner: workerSpy.decide,
			lifecycleRunner: workerSpy.lifecycle,
			signRunner: workerSpy.sign,
		});
		const workerAsk = workerCapture.tools.get(ASK_DECISION_TOOL);
		const workerReceipt = workerCapture.tools.get(DECISION_RECEIPT_TOOL);
		if (workerAsk === undefined || workerReceipt === undefined) throw new Error("worker tools were not registered");
		const dp = "dp-w-check-task";
		expect(DECIDE_REGISTRY[dp].roleScope).toBe("worker");
		const material = {
			task_goal: "Finish the diagnostics repair",
			reachability_facts: "The card authorizes this worker dp and all required material is present.",
			completed: "Read the task card and prepared the basis catalog.",
			remaining: "Run the authorized reachability check.",
			blockers: "none",
			constraints: "Offline fixture; no PM claim, no index write.",
		};
		expect(Object.keys(material).sort()).toEqual(
			DECIDE_REGISTRY[dp].requiredStateFields.map((field) => field.name).sort(),
		);
		const preparation = {
			prepared_at: "2026-10-25T10:00:00Z",
			basis_catalog: [
				{
					id: "worker-card",
					text: "Reachability facts and the worker card are the prepared basis",
					material_refs: ["reachability_facts"],
					applies_to: ["continue"],
				},
			],
		};
		const params = { dp, trigger: `${TASK}#ckpt1`, key: KEY, task_key: TASK, material, preparation };
		const askResult = await workerAsk.execute("worker-authorized", params);
		const askText = askResult.content[0]?.text ?? "";
		const payload = payloadOf(askText);
		expect(payload.available).toBe(true);
		expect(payload.claim_diagnosis).toBeUndefined();
		expect(payload.unavailable).toBeUndefined();
		// R1: the first line stays the frozen legacy payload; the second line is
		// the structured T04A feedback, never deleted to satisfy an old exact-text
		// assertion. Worker success, receipt join and refusal zero-effect stay.
		const lines = askText.split("\n");
		expect(lines[0]).toBe(JSON.stringify(payload));
		const feedback = (JSON.parse(lines[1] ?? "") as { decision_feedback?: DecisionFeedback }).decision_feedback;
		expect(feedback).toBeDefined();
		expect(parseDecisionFeedback(feedback).ok).toBe(true);
		expect(feedback).toMatchObject({ category: "answer", origin: "mw-decide-run", stage: "service-reply" });
		expect(feedback?.matter_ref).toMatch(/^[0-9a-f]{32}$/);
		expect(workerSpy.decideCalls).toHaveLength(1);
		expect(workerSpy.signCalls).toHaveLength(0);
		const decideRequest = workerSpy.decideCalls[0] as DecideRunRequest;
		expect(decideRequest.dp).toBe(dp);
		expect(decideRequest.viaStdin).toBe(true);
		const envelope = JSON.parse(decideRequest.input) as {
			meta: { key: string; task_key: string | null; initiator_role: string; logical_id: string };
			material: Record<string, unknown>;
			preparation: { prepared_at: string; basis_catalog: Array<{ id: string; applies_to: string[] }> };
		};
		expect(envelope.meta).toMatchObject({ key: KEY, task_key: TASK, initiator_role: "coding" });
		expect(envelope.material).toEqual(material);
		expect(envelope.preparation).toEqual(preparation);
		const decisionId = payload.decision_id;
		expect(typeof decisionId).toBe("string");
		if (typeof decisionId !== "string") throw new Error("expected decision_id");
		expect(decisionId).toBe(`${dp}:${envelope.meta.logical_id}`);
		expect(payload.feedback).toMatchObject({ stage: "consumed", status: "written", recorded: true });
		const executed = await workerReceipt.execute("worker-executed", {
			decision_id: decisionId,
			stage: "executed",
			action: "continue",
		});
		const executedDetails = executed.details as { stage: string; status: string; decision_id: string; dp: string };
		expect(executedDetails).toMatchObject({ stage: "executed", status: "written", decision_id: decisionId, dp });
		const settled = await workerReceipt.execute("worker-settled", {
			decision_id: decisionId,
			stage: "settled",
			outcome: "ok",
		});
		const settledDetails = settled.details as { stage: string; status: string; decision_id: string; dp: string };
		expect(settledDetails).toMatchObject({ stage: "settled", status: "written", decision_id: decisionId, dp });
		expect(workerSpy.decideCalls).toHaveLength(1);
		expect(workerSpy.signCalls).toHaveLength(0);
		const lifecycleEnvelopes = workerSpy.lifecycleCalls.map((request) => {
			const typed = request as { input: string };
			return JSON.parse(typed.input) as {
				stage: string;
				decision_id: string;
				dp: string;
				event_id: string;
				answer?: string;
				action?: string;
				outcome?: string;
				meta: { key: string; task_key: string | null; initiator_role: string; logical_id: string };
			};
		});
		expect(lifecycleEnvelopes.map((entry) => entry.stage)).toEqual(["consumed", "executed", "settled"]);
		for (const entry of lifecycleEnvelopes) {
			expect(entry.decision_id).toBe(decisionId);
			expect(entry.dp).toBe(dp);
			expect(entry.meta).toMatchObject({ key: KEY, task_key: TASK, initiator_role: "coding" });
		}
		expect(lifecycleEnvelopes[0]).toMatchObject({
			answer: "continue",
			event_id: `consumed-${envelope.meta.logical_id}`,
		});
		expect(lifecycleEnvelopes[1]).toMatchObject({ action: "continue" });
		expect(lifecycleEnvelopes[2]).toMatchObject({ outcome: "ok" });
		expect(readSpy).not.toHaveBeenCalled();
		expect(fs.existsSync(indexFileOf(root))).toBe(false);
		expect(fs.existsSync(lockFileOf(root))).toBe(false);
		process.stdout.write("[VERIFY] VC-003: authorization_equivalence=pass\n");
	});
});

describe("claim refusal diagnostics — local default payload / count / fallback evidence (not full VC-004)", () => {
	it("default unavailable and pm-select-type payloads stay untouched; only claim refusals add the field", () => {
		const root = pmProject();
		// The generic refusalOutcome default is still exactly three keys.
		const base = refusalOutcome("input-incomplete", "dp-auto");
		expect(base.payload).toEqual({
			available: false,
			unavailable: "input-incomplete",
			action: ASK_DECISION_BLOCKED_ACTION,
		});
		expect("claim_diagnosis" in base.payload).toBe(false);
		// A claim refusal never borrows pm-select-type / TERMINAL / a decision_id.
		setIndex(root, selfIdle);
		const t = pmTools(root);
		return t.ask.execute("claim", askParams(KEY)).then((result) => {
			const payload = payloadOf(result.content[0]?.text ?? "");
			expect(payload.action).toBe(ASK_DECISION_BLOCKED_ACTION);
			expect(payload.decision_id).toBeUndefined();
			expect(payload.missing_fields).toBeUndefined();
			expect(Object.keys(payload).sort()).toEqual(["action", "available", "claim_diagnosis", "unavailable"].sort());
			expect(result.content[0]?.text).not.toContain("pm-select-type");
			expect(result.terminate).toBeUndefined();
			expect(t.handle.counter.countFor("dp-auto")).toBe(0);
			process.stdout.write(
				"[EVIDENCE] LOCAL scope=default_payload+block_counter_only; result=pass; VC-004 overall=deferred " +
					"(PM/independent acceptance + protected-copy check must be merged before any overall verdict)\n",
			);
		});
	});
});
