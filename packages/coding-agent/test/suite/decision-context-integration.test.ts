/**
 * mw-decision-context T08 — the real integration lane (TS producer -> real
 * Python CLI).
 *
 * Behaviour locked here (no pure-constructor substitutes):
 *  1. dp1: the real `dispatch_worker` consumer -> real `mw decide run` ->
 *     loopback HTTP -> real `mw decide lifecycle` consumed/executed/settled for
 *     the SAME logical_id/decision_id, with the `record` fact the run CLI writes
 *     itself kept separate from the business action.
 *  2. A failing feedback write never redoes the dispatch action.
 *  3. dp2 (PM-only, with and without a real worker), dp3 (both asking roles) and
 *     dp25 (finalize/continue/user-confirm) reach the real CLI.
 *  4. dp25 `runAskDecision` asks and signs in ONE judgment: the sign CLI calls
 *     the model once, writes the sign-off file itself (finalize) or hands a
 *     concrete next step back (continue/user-confirm), never a PM second batch.
 *  5. The worker window's full `activate()` on a synthetic card registers the
 *     shared decision entry and tears its timers down on session shutdown.
 *
 * No real provider, credential, Jev, browser, build, install or service is used:
 * the decision transport is a synthetic loopback backend, the agent model is the
 * faux provider, and every project/key/ledger lives under a temp HOME.
 */

import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { emitSessionShutdownEvent } from "../../src/core/extensions/runner.ts";
import { activate } from "../../src/extensions/agent-team-loop/index.ts";
import { ASK_DECISION_MAX_STATE_BYTES, runAskDecision } from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import {
	canonicalStateBytes,
	MAX_STRUCTURED_STATE_BYTES,
} from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import type { PmWatchState } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { computeDispatchTriage, registerWorkerTools } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { findMwPy, PYTHON_EXE } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import type { ExtensionFactory, InlineExtension } from "../../src/index.ts";
import { createHarness, type Harness } from "./harness.ts";

const tempDirs: string[] = [];
const harnesses: Harness[] = [];
const savedEnv = new Map<string, string | undefined>();
const servers: Loopback[] = [];

const KEY = "mw-decision-context";
const OWNER = KEY;
const TASK = "dc-t08-dispatch";
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function mkTemp(prefix = "mwdctx-t08-"): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

beforeEach(() => {
	for (const name of [
		"HOME",
		"USERPROFILE",
		"PI_CODING_AGENT_DIR",
		"PI_WORKER_TASK",
		"MW_PY",
		"TIMI_API_KEY",
		"TIMI_BASE_URL",
	]) {
		savedEnv.set(name, process.env[name]);
	}
	const home = mkTemp("mwdctx-t08-home-");
	process.env.HOME = home;
	process.env.USERPROFILE = home;
	process.env.PI_CODING_AGENT_DIR = path.join(home, ".pi", "agent");
	delete process.env.PI_WORKER_TASK;
	// The real mw.py is resolved from the extension source tree; no sidecar, no
	// stale override, and no inherited provider credentials.
	delete process.env.MW_PY;
	delete process.env.TIMI_API_KEY;
	delete process.env.TIMI_BASE_URL;
});

afterEach(async () => {
	while (harnesses.length > 0) harnesses.pop()?.cleanup();
	for (const server of servers.splice(0)) server.close();
	while (tempDirs.length > 0) {
		const dir = tempDirs.pop();
		if (dir !== undefined) fs.rmSync(dir, { recursive: true, force: true });
	}
	for (const [name, value] of savedEnv) {
		if (value === undefined) delete process.env[name];
		else process.env[name] = value;
	}
	savedEnv.clear();
});

function hasPython(): boolean {
	return (
		spawnSync(process.platform === "win32" ? "python" : "python3", ["-c", "import sys; sys.exit(0)"], {
			windowsHide: true,
		}).status === 0
	);
}

const PYTHON_MISSING = !hasPython();
const describeWithPython = PYTHON_MISSING ? describe.skip : describe;

// ── loopback decision backend (synthetic, no paid provider) ─────────────────
//
// The backend runs in its OWN Python process: the dp1 producer path uses
// `spawnSync` for its `mw decide run` child (existing production behaviour), so
// an in-process HTTP server would deadlock the event loop it needs to answer.
// A separate process keeps the wire real (a true HTTP POST + a true JSON reply)
// and records every request for assertions.

const LOOPBACK_SOURCE = String.raw`
import http.server
import json
import sys

port_file, requests_file, answers_file, ordered_file = sys.argv[1:5]
with open(answers_file, encoding="utf-8") as handle:
    DEFAULTS = json.load(handle)
with open(ordered_file, encoding="utf-8") as handle:
    ORDERED = json.load(handle)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            body = json.loads(raw)
        except ValueError:
            body = {}
        record = {
            "model": body.get("model", ""),
            "state": body.get("state", {}),
            "questions": {qid: {"type": spec.get("type")} for qid, spec in (body.get("questions") or {}).items()},
        }
        with open(requests_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
        answers = {}
        for qid, spec in (body.get("questions") or {}).items():
            if ORDERED:
                choice = ORDERED.pop(0)
            else:
                choice = DEFAULTS.get(qid, DEFAULTS.get("__default", "unknown"))
            answers[qid] = {"type": spec.get("type", "choice"), "choice": choice, "confidence": 0.9}
        payload = json.dumps({"model": body.get("model"), "answers": answers}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        return


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
with open(port_file, "w", encoding="utf-8") as handle:
    handle.write(str(server.server_address[1]))
    handle.flush()
server.serve_forever()
`;

interface LoopbackRequest {
	model: string;
	state: Record<string, unknown>;
	questions: Record<string, { type?: string }>;
}

interface Loopback {
	baseUrl: string;
	requests(): LoopbackRequest[];
	answers: string[];
	close(): void;
}

/** A local HTTP endpoint (own process) that answers the registry question ids
 * it was asked, echo-ing the requested model (the decoder refuses a substituted
 * model). */
async function startLoopback(defaults: Record<string, string>, answers: string[] = []): Promise<Loopback> {
	const dir = mkTemp("mwdctx-t08-loopback-");
	const portFile = path.join(dir, "port.txt");
	const requestsFile = path.join(dir, "requests.jsonl");
	const answersFile = path.join(dir, "answers.json");
	const orderedFile = path.join(dir, "ordered.json");
	const script = path.join(dir, "loopback.py");
	fs.writeFileSync(script, LOOPBACK_SOURCE, "utf8");
	fs.writeFileSync(answersFile, JSON.stringify(defaults), "utf8");
	fs.writeFileSync(orderedFile, JSON.stringify(answers), "utf8");
	const child = spawn(
		hasPython() ? "python" : "python3",
		["-X", "utf8", script, portFile, requestsFile, answersFile, orderedFile],
		{
			stdio: "ignore",
			windowsHide: true,
		},
	);
	const deadline = Date.now() + 15_000;
	while (!fs.existsSync(portFile) || fs.readFileSync(portFile, "utf8").trim() === "") {
		if (Date.now() > deadline) throw new Error("loopback did not publish a port");
		if (child.exitCode !== null) throw new Error(`loopback exited early (code ${child.exitCode})`);
		await new Promise((resolve) => setTimeout(resolve, 50));
	}
	const port = fs.readFileSync(portFile, "utf8").trim();
	const loopback: Loopback = {
		baseUrl: `http://127.0.0.1:${port}`,
		requests: () =>
			fs.existsSync(requestsFile)
				? fs
						.readFileSync(requestsFile, "utf8")
						.split(/\r?\n/)
						.filter((line) => line.trim() !== "")
						.map((line) => JSON.parse(line) as LoopbackRequest)
				: [],
		answers,
		close: () => {
			child.kill("SIGKILL");
		},
	};
	servers.push(loopback);
	return loopback;
}

function writeDecideConfig(projectDir: string, baseUrl: string): void {
	fs.mkdirSync(path.join(projectDir, ".mw"), { recursive: true });
	fs.writeFileSync(
		path.join(projectDir, ".mw", "decide.json"),
		`${JSON.stringify({
			enabled: true,
			base_url: baseUrl,
			api_key: "synthetic-t08-loopback-key",
			timeout_s: 30.0,
			max_retries: 0,
			backoff_base_s: 0.0,
		})}\n`,
		"utf8",
	);
}

/** A temp project with the key dir the sign-off writer targets. */
function project(baseUrl: string): string {
	const root = mkTemp("mwdctx-t08-proj-");
	fs.mkdirSync(path.join(root, ".agenticdoc", KEY, "evidence", "review"), { recursive: true });
	writeDecideConfig(root, baseUrl);
	return root;
}

// ── the Python ledger (read-only assertions) ────────────────────────────────

interface LedgerRow {
	kind?: string;
	logical_id?: string;
	decision_id?: string | null;
	lifecycle?: string;
	action?: string | null;
	outcome?: string | null;
	answer?: string | null;
	result?: string | null;
	initiator_role?: string;
	key?: string;
	task_key?: string | null;
}

function readLedger(projectDir: string): LedgerRow[] {
	const file = path.join(projectDir, ".agenticdoc", "_autopilot", "decision-lifecycle.jsonl");
	if (!fs.existsSync(file)) return [];
	return fs
		.readFileSync(file, "utf8")
		.split(/\r?\n/)
		.filter((line) => line.trim() !== "")
		.map((line) => JSON.parse(line) as LedgerRow);
}

function lifecycleRows(projectDir: string): LedgerRow[] {
	return readLedger(projectDir).filter((row) => row.kind === "lifecycle");
}

function startRows(projectDir: string): LedgerRow[] {
	return readLedger(projectDir).filter((row) => row.kind === "record-start");
}

// ── business material fixtures (the four-DP contract) ─────────────────────

function dp3Material(): Record<string, unknown> {
	return {
		question: "dp3 澄清：本次只改 TS 生产面还是同时改 Python writer？",
		background: {
			task_goal: "把四个 DP 的 TS producer 接到真实 Python CLI 上。",
			current_state: "TS producer 已存在，Python CLI 已交付 run/lifecycle/sign。",
			decision_reason: "两条 lane 并行，写面不能相互踩踏。",
			constraints_impact: "改 Python 会让另一 lane 的 diff 冲突。",
		},
		handling_options: [
			{ id: "c1", label: "只改 TS 面", description: "保持 Python lane 的写面不变，TS 通过既有 CLI 契约接线。" },
			{ id: "c2", label: "交 PM 判定", description: "把材料交给 PM，由 PM 判定是否需要用户确认。" },
			{ id: "c3", label: "走人工澄清", description: "直接向用户提出这个具体问题并等待人工答复。" },
		],
	};
}

function dp2Material(withWorker: boolean): Record<string, unknown> {
	const material: Record<string, unknown> = {
		task_goal: "把 dp2 的 PM 主动决策接到真实 CLI。",
		task_requirements: "只 PM 发起；问题与标签不改；不自动 narrow。",
		task_deliverables: "report.md + 证据。",
		pm_decision_background: "worker 已到 30 分钟检查点，需要判断继续/拆小/直执/上抛。",
	};
	if (withWorker) material.worker_execution = "done: 接线; remaining: 证据; blocked: none; tried: 无。";
	return material;
}

function dp25Material(): Record<string, unknown> {
	return {
		delivery_goal: "四个 DP 的 TS 接线与旧断言迁移完成，PM 可独立复验。",
		actual_completion: "run/lifecycle/sign 三面已接线，定向测试 GREEN。",
		verification_evidence: {
			verified: ["decision-context-integration.test.ts"],
			unverified: ["真实 Jev 端到端"],
		},
		unfinished_impact: ["phase gate 仍是独立框架门"],
	};
}

function signoffFile(projectDir: string): string {
	return path.join(projectDir, ".agenticdoc", KEY, "evidence", "review", "sign-final.md");
}

// ── 1. dp1: the real dispatch consumer ──────────────────────────────────────

const CARD_BODY = [
	"type: coding",
	"",
	"## 上下文",
	"",
	"目标 .agenticdoc/goal.md:1；这是 T08 dp1 的真实派发卡。",
	"",
	"## 要求",
	"",
	"1. dp1 材料必须是任务卡原文。",
	"2. 消费回执必须走唯一 Python writer。",
	"",
	"## 交付格式",
	"",
	"report.md + 证据。",
	"",
	"## 写入允许面",
	"",
	"- packages/coding-agent/src/x.ts",
	"",
	"## 写入禁止面",
	"",
	"- 其它文件",
	"",
	"## 验收命令",
	"",
	"node vitest",
	"",
	"## 改动历史",
	"",
	"初派",
	"",
].join("\n");

function writePhaseDocs(agenticdocRoot: string, key: string): void {
	const keyDir = path.join(agenticdocRoot, key);
	fs.mkdirSync(path.join(keyDir, "evidence", "research"), { recursive: true });
	fs.writeFileSync(path.join(keyDir, "spec.md"), `# Spec\n${"x".repeat(600)}\n\n| AC-001 | ok |\n`, "utf8");
	fs.writeFileSync(path.join(keyDir, "design.md"), `# Design\n${"x".repeat(600)}`, "utf8");
	fs.writeFileSync(path.join(keyDir, "evidence", "research", "spec-topic-2026-01-01.md"), "# research\n", "utf8");
	fs.writeFileSync(path.join(keyDir, "evidence", "research", "design-topic-2026-01-01.md"), "# research\n", "utf8");
}

interface DispatchRun {
	harness: Harness;
	text: string;
}

async function dispatchThroughTool(
	projectDir: string,
	options: { lifecycleRun?: Parameters<typeof registerWorkerTools>[8] } = {},
): Promise<DispatchRun> {
	const agenticdocRoot = path.join(projectDir, ".agenticdoc");
	const cardPath = path.join(agenticdocRoot, "cards", "T08-dispatch.md");
	fs.mkdirSync(path.dirname(cardPath), { recursive: true });
	fs.writeFileSync(cardPath, CARD_BODY, "utf8");
	writePhaseDocs(agenticdocRoot, OWNER);
	const extensionFactories: Array<ExtensionFactory | InlineExtension> = [
		(pi) => {
			registerWorkerTools(
				pi,
				new WorkerStore(agenticdocRoot),
				new AckStore(agenticdocRoot),
				new IndexStore(agenticdocRoot),
				agenticdocRoot,
				{ key: OWNER } satisfies PmWatchState,
				projectDir,
				// No triageRun: the production `mw decide run` child is under test.
				undefined,
				options.lifecycleRun,
			);
		},
	];
	const harness = await createHarness({ extensionFactories });
	harnesses.push(harness);
	harness.setResponses([
		fauxAssistantMessage(
			fauxToolCall("dispatch_worker", {
				task_key: TASK,
				card_path: cardPath,
				description: "T08 真实 dp1 派发。",
				type: "coding",
				key: OWNER,
			}),
			{ stopReason: "toolUse" },
		),
		fauxAssistantMessage("done"),
	]);
	await harness.session.prompt("dispatch the T08 card");
	const results = harness.session.messages.filter((message) => message.role === "toolResult");
	return { harness, text: JSON.stringify(results.at(-1)?.content ?? "") };
}

describeWithPython("dp1: the real dispatch consumer writes its own receipt", () => {
	it("sends the card material, then records consumed/executed/settled for the same decision", async () => {
		const loopback = await startLoopback({ triage_type: "coding" });
		const root = project(loopback.baseUrl);
		const { text } = await dispatchThroughTool(root);

		// The model really received the card's three bodies (no truncation).
		expect(loopback.requests()).toHaveLength(1);
		const sent = loopback.requests()[0]?.state ?? {};
		expect(Object.keys(sent).sort()).toEqual(["task_deliverables", "task_goal", "task_requirements"]);
		expect(String(sent.task_goal)).toContain("T08 dp1 的真实派发卡");
		expect(String(sent.task_requirements)).toContain("唯一 Python writer");

		// Same-decision association, produced by Python (never hand-filled here).
		const starts = startRows(root);
		expect(starts).toHaveLength(1);
		const logicalId = starts[0]?.logical_id ?? "";
		expect(logicalId).toMatch(UUID_V4);
		expect(starts[0]).toMatchObject({ initiator_role: "pm", key: OWNER, task_key: TASK });

		const rows = lifecycleRows(root);
		const decisionId = rows[0]?.decision_id ?? "";
		expect(decisionId.startsWith("dp1-dispatch-type:")).toBe(true);
		// The run CLI's own technical fact, then the consumer's three business
		// facts — all on the same logical_id/decision_id.
		const actions = rows.map((row) => `${row.lifecycle}:${row.action ?? ""}:${row.outcome ?? ""}`);
		expect(actions).toEqual(["executed:record:", "consumed::", "executed:type-read:", "settled::ok"]);
		for (const row of rows) {
			expect(row.logical_id).toBe(logicalId);
			expect(row.decision_id).toBe(decisionId);
		}
		const consumed = rows.find((row) => row.lifecycle === "consumed");
		const executed = rows.find((row) => row.lifecycle === "executed" && row.action === "type-read");
		const settled = rows.find((row) => row.lifecycle === "settled");
		expect(consumed?.answer).toBe("coding");
		expect(String(executed?.result)).toContain("dispatched");
		expect(settled?.outcome).toBe("ok");

		// The dispatch really landed and the adopted decision is the one recorded.
		const taskMd = fs.readFileSync(path.join(root, ".agenticdoc", OWNER, "workers", TASK, "task.md"), "utf8");
		expect(taskMd).toContain("type: coding");
		expect(taskMd).toContain(`decision: ${decisionId}`);
		expect(text).toContain("Dispatched worker");
		// The receipt the PM sees is the writer's own answers, not an assumption.
		expect(text).toContain("consumed=written");
		expect(text).toContain("executed=written");
		expect(text).toContain("settled=written");
		console.log(
			`[EVIDENCE] dp1 decision_id=${decisionId} logical_id=${logicalId} rows=${rows.length} material_bytes=${Buffer.byteLength(JSON.stringify(sent), "utf8")}`,
		);
		console.log("[VERIFY] VC-014: false_completions=0 dp1_stages=consumed/executed/settled");
	});

	it("keeps the dispatch when the feedback write fails (the action is never redone)", async () => {
		const loopback = await startLoopback({ triage_type: "coding" });
		const root = project(loopback.baseUrl);
		const failures: string[] = [];
		const lifecycleRun = async (request: { input: string }) => {
			failures.push(request.input);
			return { status: 1, stdout: "", stderr: "ledger unavailable", timedOut: false };
		};
		const { text } = await dispatchThroughTool(root, { lifecycleRun });

		// One decision, one dispatch, and NO repeated action after the write failed.
		expect(loopback.requests()).toHaveLength(1);
		const taskMd = fs.readFileSync(path.join(root, ".agenticdoc", OWNER, "workers", TASK, "task.md"), "utf8");
		expect(taskMd).toContain("type: coding");
		expect(text).toContain("Dispatched worker");
		// Only the run CLI's own technical `record` fact is in the ledger; the
		// consumer's three business facts all failed, and none was invented.
		const rows = lifecycleRows(root);
		expect(rows.map((row) => `${row.lifecycle}:${row.action ?? ""}`)).toEqual(["executed:record"]);
		// Every attempted fact carries the real decision id; the failure is reported.
		expect(failures.length).toBe(3);
		for (const payload of failures) {
			const parsed = JSON.parse(payload) as { decision_id?: string; stage?: string; event_id?: string };
			expect(parsed.decision_id?.startsWith("dp1-dispatch-type:")).toBe(true);
			expect(parsed.event_id).toContain(":");
		}
		expect(text).toContain("consumed=failed");
		expect(text).toContain("executed=failed");
		expect(text).toContain("settled=failed");
	});
});

// ── 2. dp2 / dp3 through the real CLI ──────────────────────────────────────

describeWithPython("dp2: PM-only material with and without a real worker", () => {
	it("sends the PM background and omits worker_execution when nothing was dispatched", async () => {
		const loopback = await startLoopback({ checkpoint_action: "narrow" });
		const root = project(loopback.baseUrl);
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp2-checkpoint-split",
			trigger: `${TASK}#ckpt1`,
			material: dp2Material(false),
			initiatorRole: "pm",
			key: KEY,
			taskKey: TASK,
		});
		expect(outcome.payload.available, outcome.text).toBe(true);
		if (!outcome.payload.available) throw new Error("unreachable");
		expect(outcome.payload.selection?.id).toBe("narrow");
		const sent = loopback.requests()[0]?.state ?? {};
		expect(sent).not.toHaveProperty("worker_execution");
		expect(sent.task_goal).toBe(dp2Material(false).task_goal);
		// The registry question/labels are not re-declared by TS: the real
		// question id is the one Python answered.
		expect(Object.keys(loopback.requests()[0]?.questions ?? {})).toEqual(["checkpoint_action"]);
		const rows = lifecycleRows(root);
		expect(rows.map((row) => row.lifecycle)).toEqual(["executed", "consumed"]);
		expect(rows.find((row) => row.lifecycle === "consumed")?.answer).toBe("narrow");
		console.log("[VERIFY] VC-004: dp2_question=checkpoint_action selection=narrow auto_actions=0");
	});

	it("refuses a worker-initiated dp2 with zero spawn", async () => {
		const loopback = await startLoopback({ checkpoint_action: "split" });
		const root = project(loopback.baseUrl);
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp2-checkpoint-split",
			trigger: `${TASK}#ckpt2`,
			material: dp2Material(true),
			initiatorRole: "coding",
			key: KEY,
			taskKey: TASK,
		});
		expect(outcome.payload.available).toBe(false);
		expect(outcome.spawned).toBe(false);
		expect(loopback.requests()).toHaveLength(0);
		if (!outcome.payload.available) expect(outcome.payload.unavailable).toBe("role-forbidden");
	});

	it("carries worker_execution when a live worker really exists", async () => {
		const loopback = await startLoopback({ checkpoint_action: "split" });
		const root = project(loopback.baseUrl);
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp2-checkpoint-split",
			trigger: `${TASK}#ckpt3`,
			material: dp2Material(true),
			initiatorRole: "pm",
			key: KEY,
			taskKey: TASK,
		});
		expect(outcome.payload.available, outcome.text).toBe(true);
		const sent = loopback.requests()[0]?.state ?? {};
		expect(String(sent.worker_execution)).toContain("remaining");
	});
});

describeWithPython("dp3: both asking roles reach the real CLI", () => {
	it("worker -> PM: the card role travels in meta and the receipt names the sent candidate", async () => {
		const loopback = await startLoopback({ handling: "c2" });
		const root = project(loopback.baseUrl);
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp3-worker-clarify",
			trigger: `${TASK}#nc1`,
			material: dp3Material(),
			initiatorRole: "coding",
			key: KEY,
			taskKey: TASK,
		});
		expect(outcome.payload.available, outcome.text).toBe(true);
		if (!outcome.payload.available) throw new Error("unreachable");
		expect(outcome.payload.selection).toMatchObject({ id: "c2", label: "交 PM 判定" });
		const sent = loopback.requests()[0]?.state ?? {};
		expect(sent.question).toBe(dp3Material().question);
		expect(sent.background).toEqual(dp3Material().background);
		expect(sent.handling_options).toEqual(dp3Material().handling_options);
		const starts = startRows(root);
		expect(starts[0]?.initiator_role).toBe("coding");
		expect(starts[0]?.task_key).toBe(TASK);
		const rows = lifecycleRows(root);
		expect(rows.find((row) => row.lifecycle === "consumed")?.answer).toBe("c2");
		// The selection alone never executes or settles anything.
		expect(rows.some((row) => row.lifecycle === "settled")).toBe(false);
	});

	it("PM -> user: the same entry records the pm role and a task-less decision as null", async () => {
		const loopback = await startLoopback({ handling: "c1" });
		const root = project(loopback.baseUrl);
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp3-worker-clarify",
			trigger: `${KEY}#q1`,
			material: dp3Material(),
			initiatorRole: "pm",
			key: KEY,
			taskKey: null,
		});
		expect(outcome.payload.available, outcome.text).toBe(true);
		const starts = startRows(root);
		expect(starts[0]?.initiator_role).toBe("pm");
		expect(starts[0]?.task_key).toBeNull();
		expect(lifecycleRows(root).find((row) => row.lifecycle === "consumed")?.answer).toBe("c1");
		console.log("[VERIFY] VC-005: dp3_roles=pm/coding sent_candidates=3 receipt=c1/c2");
	});
});

// ── 3. dp25: one judgment that really signs ────────────────────────────────

describeWithPython("dp25: the managed PM path asks and signs in one judgment", () => {
	it("finalize writes the valid sign-final.md for the same logical_id, with no second model call", async () => {
		const loopback = await startLoopback({ "q-conclusion": "finalize" });
		const root = project(loopback.baseUrl);
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp25-signoff-conclusion",
			trigger: KEY,
			material: dp25Material(),
			initiatorRole: "pm",
			key: KEY,
			taskKey: null,
		});
		const payload = outcome.payload;
		expect(payload.available, outcome.text).toBe(true);
		if (!payload.available) throw new Error("unreachable");
		expect(payload.selection?.id).toBe("finalize");
		// ONE judgment: the sign CLI called the model exactly once.
		expect(loopback.requests()).toHaveLength(1);
		expect(loopback.requests()[0]?.state).toEqual(dp25Material());
		const signoff = payload.signoff;
		expect(signoff?.status).toBe("written");
		expect(signoff?.second_approval).toBe(0);
		const file = signoffFile(root);
		expect(fs.existsSync(file)).toBe(true);
		const text = fs.readFileSync(file, "utf8");
		const logicalId = startRows(root)[0]?.logical_id ?? "";
		expect(logicalId).toMatch(UUID_V4);
		expect(text).toContain(`logical_id: ${logicalId}`);
		const rows = lifecycleRows(root);
		expect(rows.map((row) => row.lifecycle).sort()).toEqual(["consumed", "signoff"]);
		for (const row of rows) expect(row.logical_id).toBe(logicalId);
		expect(rows[0]?.decision_id).toBe(rows[1]?.decision_id);
		console.log(`[VERIFY] VC-014: dp25_signoff=written logical_id=${logicalId} model_calls=1`);
	});

	it("continue writes no sign-off and hands the concrete next step back to the PM", async () => {
		const loopback = await startLoopback({ "q-conclusion": "continue" });
		const root = project(loopback.baseUrl);
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp25-signoff-conclusion",
			trigger: KEY,
			material: dp25Material(),
			initiatorRole: "pm",
			key: KEY,
			taskKey: null,
		});
		const payload = outcome.payload;
		expect(payload.available, outcome.text).toBe(true);
		if (!payload.available) throw new Error("unreachable");
		expect(payload.selection?.id).toBe("continue");
		expect(payload.signoff?.status).toBe("not-required");
		expect(payload.signoff?.handoff).toMatchObject({ owner: "pm", kind: "continue", signoff_writes: 0 });
		expect(fs.existsSync(signoffFile(root))).toBe(false);
		const rows = lifecycleRows(root);
		expect(rows.map((row) => row.lifecycle)).toEqual(["executed"]);
		expect(rows[0]?.action).toBe("continue");
		expect(rows[0]?.outcome).toBeNull();
	});

	it("user-confirm writes no sign-off and names the items to confirm", async () => {
		const loopback = await startLoopback({ "q-conclusion": "user-confirm" });
		const root = project(loopback.baseUrl);
		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp25-signoff-conclusion",
			trigger: KEY,
			material: dp25Material(),
			initiatorRole: "pm",
			key: KEY,
			taskKey: null,
		});
		if (!outcome.payload.available) throw new Error(outcome.text);
		expect(outcome.payload.selection?.id).toBe("user-confirm");
		expect(outcome.payload.signoff?.handoff).toMatchObject({ kind: "user-confirm", signoff_writes: 0 });
		expect(fs.existsSync(signoffFile(root))).toBe(false);
		expect(lifecycleRows(root).map((row) => row.lifecycle)).toEqual(["executed"]);
	});
});

// ── 3b. the published 8192B material budget is the ONE authority ───────────
//
// The legacy 2000B constant describes the structured state of the other 21 dps.
// The four business-material dps are bounded by the Python transport/registry
// budget (8192B), which refuses the WHOLE material (never a truncation) with
// zero POST. A TS mirror of that number would be a second authority, so these
// tests drive the REAL CLI: >2000B material must reach the loopback byte-exact,
// and >8192B must be refused by the CLI with no request at all.

const REAL_CARD_MATERIAL = {
	task_goal:
		"\n目标`.agenticdoc/goal.md:1`，批准spec/design/plan " +
		"`.agenticdoc/mw-decision-context/`；源锚`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:528` " +
		"buildDp1DispatchState、`pm/pm-orchestrator.ts:2336`旧dp2调用/auto narrow。T01 " +
		"Python契约/T02反馈正在实现，T04后续独占decision-tool/index/worker-mode。不双写。",
	task_requirements:
		"\n按用户批准修改dp1 " +
		"producer用任务目标/要求/交付物完整原文，类型问题仅coding/research/review，不加risk/reason问；vision/rag等原生角色边界保留，派发建议不扩大自动改type授权。三固定说明用户原定义。\n" +
		"dp2只PM主动：去pm-orchestrator自动dp2调用及其旧自动narrow任务执行分支，保留通用watchdog/checkpoint告警，不新增自评产物/等待/异常阈值。PM手动入口由T04受管工具负责，你不写decision-tool。删除已明确替换路径获用户授权，无需重复问。\n" +
		"CLI T05将实现`mw decide run <dp> " +
		"--stdin`（本地envelope），Producer材料`{material:{task_goal,task_requirements,task_deliverables},meta:{record_version:2,logical_id,key,task_key,initiator_role:'PM',retry_of:null}}`，独立UUID生产，task派发前预留真实id、不猜最新。如现triage " +
		"transport必须复用现stdin wrapper，按现架构精准接线并报告T05要求；identity绝不进model。\n" +
		"现Python CLI稳定前验证真实TS producer→stdin或loopback " +
		"mock边界，后续集成T05一轮统一。dp1实际consumer收到及派发/保留类型/不一致告警结束后的真实反馈，T02唯一Python " +
		"writer/T05 " +
		"CLI精确签名交付后接，不TS裸append、不consumed当settled。先独立producer/去自动路径实现，不等接口空转。\n" +
		"正确行为RED先于实现；使用suite/harness.ts+faux，不激活真实provider/token/真实凭证。首写保存允许面基线hash/diff含untracked，外来review-split/claims功能保留，别覆盖。大文件完整分页read≤120行，不无限dump/研究；10分钟内产出行为RED计划。已批准设计最高优先，低影响债集中账。\n" +
		"不改extension " +
		"API，无需核心改动；若涉及API时先读pi对应完整docs/examples，禁止猜类型/内联imports/any，现node_modules类型可查。配置键绑定不能硬编码。",
	task_deliverables:
		"\nreport.md+自身evidence " +
		"RED/GREEN原日志/UTC/exit/hash、dp1最终材料原文与实际stdin例子、去自动dp2证据/告警仍在、consumer回执接线坐标/需T05精确CLI约束、局部 " +
		"vs全链分列。低影响债集中报告不研究。",
};

function realDp2Material(): Record<string, unknown> {
	return {
		...REAL_CARD_MATERIAL,
		pm_decision_background:
			"T08 收口：TS 仍用旧 2000B 客户端上限拒绝完整任务材料，Python 已发布 8192B 材料预算。" +
			"需要判断是取消客户端上限交由服务整份拒绝，还是对齐同一权威；不允许截断材料，也不允许降低其余 21 DP 的安全预算。",
	};
}

function realDp25Material(): Record<string, unknown> {
	return {
		delivery_goal:
			"T08 固定收口完成：四业务 material 由真实 Python CLI 按发布的 8192B/transport 边界整份拒绝、不截断；" +
			"REQUIRED_FIELDS_BY_DP 的三个业务 DP 行按 registry 统一，Python parity 对三 DP 真比较；" +
			"三份邻接 pytest 按新四部分 dp25/动态 dp3 契约迁移且不弱化 secret/空值/零 POST/记录失败断言。" +
			"验收只跑每个改动文件（各 suite 独立落盘完整 UTF-8 stdout/stderr/UTC/argv/exit），不跑全套、不做 build/install/commit。" +
			"产物每行登记精确路径，干净工作区不属于本卡；固定三缺口闭合后停写交接。",
		actual_completion:
			"dp2/dp3/dp25 三个业务 DP 的真实材料已通过真实 `mw decide run --stdin` 与 `mw decide sign --stdin` 发送；" +
			">8192B 材料由 CLI 整份拒绝且零 POST；三份邻接 suite 的 RED 已复现并逐类核过根因，迁移后逐文件实跑。" +
			"预算实测：canonical 8192B 是唯一权威，TS 不再镜像 2000B；legacy 21 DP 的结构化 state 仍保留原 2000B 上限。" +
			"dp25 签收路径与 dp2/dp3 material 路径共用同一真实 CLI 边界，错误 vocabulary（input-oversize/input-incomplete）原样上报。",
		verification_evidence: {
			verified: [
				"真实 loopback HTTP 捕获的请求正文与材料逐字段相等（>2000B 也整份到达）",
				">8192B 时 loopback requests=0，CLI detail 为 state is NB > 8192B",
				"dp25 一次判断即签收：loopback 只收到一次请求，sign-final.md 与 logical_id 精确关联",
				">2000B 的 dp25 材料由真实 `decide sign` 整份接收并写出签收文件，客户端无 2000B 镜像上限",
				"legacy 21 DP 的结构化 state 仍受 MAX_STRUCTURED_STATE_BYTES 保护，未被本次预算改动降低",
			],
			unverified: [
				"真实 Jev 付费模型的决策质量",
				"真实浏览器中的工作台渲染",
				"全仓 npm run check（PM 统一稳定后跑）",
			],
		},
		unfinished_impact: [
			"dp25 phase gate 词表仍是 continue|narrow|revoke，与 finalize 不兼容，属框架脚本写面外的结案阻塞",
			"其余低影响债（decision_book.py 注释、decide_signoff 旧计数构造）集中报告，不在本卡扩展",
		],
	};
}

interface CliReceipt {
	available?: boolean;
	reason?: string | null;
	escalated_reason?: string | null;
	attempts?: number;
	detail?: string | null;
	answers?: unknown;
	truncated?: unknown;
	conclusion?: string | null;
	signoff_status?: string | null;
	problems?: unknown;
}

function decisionCliMeta(): Record<string, unknown> {
	return {
		record_version: 2,
		logical_id: randomUUID(),
		key: KEY,
		task_key: null,
		initiator_role: "pm",
		retry_of: null,
	};
}

function parseCliReceipt(stdout: string): CliReceipt {
	const lines = stdout.trim().split(/\r?\n/);
	return JSON.parse(lines.at(-1) ?? "") as CliReceipt;
}

/** The REAL `mw decide run` child, driven directly (the CLI is under test). */
function runDecisionCli(root: string, dp: string, material: Record<string, unknown>): CliReceipt {
	const mwPy = findMwPy();
	if (mwPy === null) throw new Error("mw.py not found");
	const completed = spawnSync(
		PYTHON_EXE,
		["-X", "utf8", mwPy, "decide", "run", `--project=${root}`, "--dp", dp, "--stdin", "--json"],
		{
			input: JSON.stringify({ material, meta: decisionCliMeta() }),
			encoding: "utf8",
			timeout: 60_000,
			windowsHide: true,
			cwd: root,
		},
	);
	return parseCliReceipt(completed.stdout ?? "");
}

/** The REAL `mw decide sign` child (dp25's single-judgment writer). */
function runSignCli(root: string, material: Record<string, unknown>): CliReceipt {
	const mwPy = findMwPy();
	if (mwPy === null) throw new Error("mw.py not found");
	const completed = spawnSync(
		PYTHON_EXE,
		["-X", "utf8", mwPy, "decide", "sign", KEY, `--project=${root}`, "--stdin", "--json"],
		{
			input: JSON.stringify({ material, meta: decisionCliMeta() }),
			encoding: "utf8",
			timeout: 60_000,
			windowsHide: true,
			cwd: root,
		},
	);
	return parseCliReceipt(completed.stdout ?? "");
}

describeWithPython("the published 8192B material budget: real material posts, over-budget is refused whole", () => {
	it("sends a complete real dp2 task material > 2000B byte-exact (no client cap, no truncation)", async () => {
		const loopback = await startLoopback({ checkpoint_action: "narrow" });
		const root = project(loopback.baseUrl);
		const material = realDp2Material();
		const bytes = canonicalStateBytes(material);
		expect(bytes).toBeGreaterThan(2000);

		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp2-checkpoint-split",
			trigger: `${TASK}#budget1`,
			material,
			initiatorRole: "pm",
			key: KEY,
			taskKey: TASK,
		});

		expect(outcome.payload.available, outcome.text).toBe(true);
		expect(outcome.spawned).toBe(true);
		const requests = loopback.requests();
		expect(requests).toHaveLength(1);
		expect(requests[0]?.state).toEqual(material);
		expect(requests[0]?.state).not.toHaveProperty("key");
		const sentBytes = Buffer.byteLength(JSON.stringify(requests[0]?.state), "utf8");
		expect(sentBytes).toBeGreaterThan(2000);
		expect(lifecycleRows(root).find((row) => row.lifecycle === "consumed")?.answer).toBe("narrow");
		console.log(`[VERIFY] VC-020: real_material_bytes=${bytes} sent_body_bytes=${sentBytes} posts=1 truncation=0`);
	});

	it("refuses a >8192B dp2 material whole with zero POST (the CLI boundary, not a TS pre-check)", async () => {
		const loopback = await startLoopback({ checkpoint_action: "narrow" });
		const root = project(loopback.baseUrl);
		const material = {
			...realDp2Material(),
			task_requirements: `${REAL_CARD_MATERIAL.task_requirements}${"x".repeat(9000)}`,
		};
		const bytes = canonicalStateBytes(material);
		expect(bytes).toBeGreaterThan(8192);

		const cli = runDecisionCli(root, "dp2-checkpoint-split", material);
		expect(cli.available).toBe(false);
		expect(cli.escalated_reason).toBe("input-oversize");
		expect(cli.attempts).toBe(0);
		expect(String(cli.detail)).toContain("> 8192B");
		expect(cli.truncated ?? []).toEqual([]);
		expect(loopback.requests()).toHaveLength(0);

		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp2-checkpoint-split",
			trigger: `${TASK}#budget2`,
			material,
			initiatorRole: "pm",
			key: KEY,
			taskKey: TASK,
		});
		expect(outcome.spawned).toBe(true);
		expect(outcome.payload.available).toBe(false);
		if (!outcome.payload.available) {
			expect(outcome.payload.escalated_reason).toBe("input-oversize");
			expect(outcome.payload.unavailable).toBe("budget-exhausted");
		}
		expect(loopback.requests()).toHaveLength(0);
		expect(lifecycleRows(root).some((row) => row.lifecycle === "consumed")).toBe(false);
		console.log(`[VERIFY] VC-020: over_budget_bytes=${bytes} posts=0 truncated=0 detail_named_8192=1`);
	});

	it("sends a complete real dp1 card material > 2000B through the real producer and CLI", async () => {
		const loopback = await startLoopback({ triage_type: "coding" });
		const root = project(loopback.baseUrl);
		// A sync producer needs the loopback already listening in its own process.
		const sections = {
			context: REAL_CARD_MATERIAL.task_goal,
			requirements: REAL_CARD_MATERIAL.task_requirements,
			deliverables: REAL_CARD_MATERIAL.task_deliverables,
			extras: [],
		};
		const bytes = canonicalStateBytes({
			task_goal: sections.context.trim(),
			task_requirements: sections.requirements.trim(),
			task_deliverables: sections.deliverables.trim(),
		});
		expect(bytes).toBeGreaterThan(2000);
		const triage = computeDispatchTriage({
			projectDir: root,
			dispatchedType: "coding",
			dp1: { key: KEY, taskKey: TASK, taskType: "coding", sections },
		});
		expect(triage?.statePath).toBe("material");
		expect(triage?.result.reason).toBeUndefined();
		const requests = loopback.requests();
		expect(requests).toHaveLength(1);
		expect(requests[0]?.state).toEqual({
			task_goal: sections.context.trim(),
			task_requirements: sections.requirements.trim(),
			task_deliverables: sections.deliverables.trim(),
		});
		expect(Buffer.byteLength(JSON.stringify(requests[0]?.state), "utf8")).toBeGreaterThan(2000);
		console.log(`[VERIFY] VC-020: dp1_real_material_bytes=${bytes} posts=1 truncation=0`);
	});

	it("refuses a >8192B dp1 card material whole with zero POST", async () => {
		const loopback = await startLoopback({ triage_type: "coding" });
		const root = project(loopback.baseUrl);
		const sections = {
			context: REAL_CARD_MATERIAL.task_goal,
			requirements: `${REAL_CARD_MATERIAL.task_requirements}${"x".repeat(9000)}`,
			deliverables: REAL_CARD_MATERIAL.task_deliverables,
			extras: [],
		};
		const bytes = canonicalStateBytes({
			task_goal: sections.context.trim(),
			task_requirements: sections.requirements.trim(),
			task_deliverables: sections.deliverables.trim(),
		});
		expect(bytes).toBeGreaterThan(8192);
		const triage = computeDispatchTriage({
			projectDir: root,
			dispatchedType: "coding",
			dp1: { key: KEY, taskKey: TASK, taskType: "coding", sections },
		});
		expect(triage?.result.available).toBe(false);
		expect(triage?.result.escalated_reason).toBe("input-oversize");
		expect(loopback.requests()).toHaveLength(0);
		console.log(`[VERIFY] VC-020: dp1_over_budget_bytes=${bytes} posts=0 truncated=0`);
	});

	it("sends a complete real dp3 material > 2000B and refuses >8192B with zero POST", async () => {
		const loopback = await startLoopback({ handling: "c1" });
		const root = project(loopback.baseUrl);
		const material = {
			...dp3Material(),
			question: `${REAL_CARD_MATERIAL.task_goal}${REAL_CARD_MATERIAL.task_requirements}`,
		};
		const bytes = canonicalStateBytes(material);
		expect(bytes).toBeGreaterThan(2000);

		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp3-worker-clarify",
			trigger: `${TASK}#budget3`,
			material,
			initiatorRole: "coding",
			key: KEY,
			taskKey: TASK,
		});
		expect(outcome.payload.available, outcome.text).toBe(true);
		expect(loopback.requests()).toHaveLength(1);
		expect(loopback.requests()[0]?.state).toEqual(material);

		const oversize = { ...material, question: `${material.question}${"x".repeat(9000)}` };
		expect(canonicalStateBytes(oversize)).toBeGreaterThan(8192);
		const cli = runDecisionCli(root, "dp3-worker-clarify", oversize);
		expect(cli.escalated_reason).toBe("input-oversize");
		expect(cli.attempts).toBe(0);
		expect(String(cli.detail)).toContain("> 8192B");
		const refused = await runAskDecision({
			projectDir: root,
			dp: "dp3-worker-clarify",
			trigger: `${TASK}#budget4`,
			material: oversize,
			initiatorRole: "coding",
			key: KEY,
			taskKey: TASK,
		});
		expect(refused.spawned).toBe(true);
		expect(refused.payload.available).toBe(false);
		if (!refused.payload.available) expect(refused.payload.escalated_reason).toBe("input-oversize");
		expect(loopback.requests()).toHaveLength(1);
		console.log(
			`[VERIFY] VC-020: dp3_real_material_bytes=${bytes} dp3_over_budget_bytes=${canonicalStateBytes(oversize)} posts_over_budget=0`,
		);
	});

	it("sends a complete real dp25 sign material > 2000B and signs once", async () => {
		const loopback = await startLoopback({ "q-conclusion": "finalize" });
		const root = project(loopback.baseUrl);
		const material = realDp25Material();
		const bytes = canonicalStateBytes(material);
		expect(bytes).toBeGreaterThan(2000);

		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp25-signoff-conclusion",
			trigger: KEY,
			material,
			initiatorRole: "pm",
			key: KEY,
			taskKey: null,
		});

		expect(outcome.payload.available, outcome.text).toBe(true);
		if (!outcome.payload.available) throw new Error("unreachable");
		expect(outcome.payload.signoff?.status).toBe("written");
		expect(loopback.requests()).toHaveLength(1);
		expect(loopback.requests()[0]?.state).toEqual(material);
		expect(fs.existsSync(signoffFile(root))).toBe(true);
		console.log(`[VERIFY] VC-008: dp25_real_material_bytes=${bytes} posts=1 sign_writes=1 model_calls=1`);
	});

	it("refuses a >8192B dp25 sign material whole: zero POST, zero sign-off, explicit failure", async () => {
		const loopback = await startLoopback({ "q-conclusion": "finalize" });
		const root = project(loopback.baseUrl);
		const base = realDp25Material();
		const material = {
			...base,
			unfinished_impact: [`${String((base.unfinished_impact as string[])[0])}${"y".repeat(9000)}`],
		};
		const bytes = canonicalStateBytes(material);
		expect(bytes).toBeGreaterThan(8192);

		const cli = runSignCli(root, material);
		expect(cli.conclusion).toBeNull();
		expect(cli.signoff_status).toBe("failed");
		expect(String(JSON.stringify(cli.problems))).toContain("input-oversize");
		expect(loopback.requests()).toHaveLength(0);

		const outcome = await runAskDecision({
			projectDir: root,
			dp: "dp25-signoff-conclusion",
			trigger: KEY,
			material,
			initiatorRole: "pm",
			key: KEY,
			taskKey: null,
		});
		expect(outcome.spawned).toBe(true);
		expect(outcome.payload.available).toBe(false);
		if (!outcome.payload.available) expect(outcome.payload.escalated_reason).toBe("input-oversize");
		expect(loopback.requests()).toHaveLength(0);
		expect(fs.existsSync(signoffFile(root))).toBe(false);
		expect(lifecycleRows(root).map((row) => row.lifecycle)).not.toContain("consumed");
		console.log(`[VERIFY] VC-020: dp25_over_budget_bytes=${bytes} posts=0 sign_writes=0 refusal=input-oversize`);
	});

	it("keeps the legacy 21-dp structured state at its 2000B budget (no global lowering)", () => {
		expect(ASK_DECISION_MAX_STATE_BYTES).toBe(MAX_STRUCTURED_STATE_BYTES);
		expect(MAX_STRUCTURED_STATE_BYTES).toBe(2000);
	});
});

// ── 4. the worker window's full activate() ─────────────────────────────────

describe("worker full activate (synthetic card, isolated)", () => {
	it("registers the same decision entry with the card role and tears its timers down", async () => {
		const loopback = await startLoopback({ handling: "c3" });
		const root = project(loopback.baseUrl);
		const taskDir = path.join(root, ".agenticdoc", KEY, "workers", TASK);
		fs.mkdirSync(taskDir, { recursive: true });
		const taskPath = path.join(taskDir, "task.md");
		fs.writeFileSync(taskPath, "type: coding\nphase: EXECUTE\n\nsynthetic worker card\n", "utf8");
		process.env.PI_WORKER_TASK = taskPath;
		delete (globalThis as Record<string, unknown>).__agentTeamLoopActivated;
		const savedCwd = process.cwd();
		process.chdir(root);
		const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval");
		try {
			const harness = await createHarness({
				extensionFactories: [(pi) => activate(pi)],
			});
			harnesses.push(harness);
			harness.setResponses([fauxAssistantMessage("ready")]);
			await harness.session.prompt("start");
			const active = harness.session.getActiveToolNames();
			expect(active).toContain("ask_decision");
			expect(active).toContain("decision_receipt");
			// run.json proves the real worker entry ran (not a source grep).
			const runFile = path.join(taskDir, "run.json");
			expect(fs.existsSync(runFile)).toBe(true);
			// Session shutdown (the real replacement/reload path) clears the
			// watchdog/heartbeat timers; a disposed session must not leave them armed.
			clearIntervalSpy.mockClear();
			await emitSessionShutdownEvent(harness.session.extensionRunner, {
				type: "session_shutdown",
				reason: "reload",
			});
			harness.cleanup();
			harnesses.pop();
			expect(clearIntervalSpy.mock.calls.length).toBeGreaterThanOrEqual(1);
		} finally {
			clearIntervalSpy.mockRestore();
			process.chdir(savedCwd);
		}
	});
});
