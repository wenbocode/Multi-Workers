/**
 * T15-J: a REAL typed PM stage source from the authenticated private channel,
 * plus the typed local QG consumer. No fake worker dispatch/run.json, no live
 * root policy, no provider calls and no QG PASS/gate/sign/Done path.
 */

import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall, registerFauxProvider } from "@earendil-works/pi-ai/compat";
import { Type } from "typebox";
import { afterEach, describe, expect, it, vi } from "vitest";
import { emitSessionShutdownEvent } from "../../src/core/extensions/runner.ts";
import type { ExtensionContext } from "../../src/core/extensions/types.ts";
import {
	grantDigest,
	PmChannel,
	type PmStageGrantV1,
	registerPmChannel,
} from "../../src/extensions/agent-team-loop/pm/codex-channel.ts";
import { ASK_DECISION_TOOL, registerAskDecisionTool } from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import {
	registerSubmitDecisionHandoffTool,
	SUBMIT_DECISION_HANDOFF_TOOL,
} from "../../src/extensions/agent-team-loop/pm/host-submit.ts";
import {
	evaluateLocalQg,
	LOCAL_QG_VERIFIER,
	type LocalQgReview,
	localQgReviewDigest,
} from "../../src/extensions/agent-team-loop/pm/local-qg-consumer.ts";
import {
	findPmStageDirection,
	PM_STAGE_ENTRY_TYPE,
	PM_STAGE_SOURCE_ENTRY_TYPE,
	PmStageLedger,
	stageSourceDigest,
} from "../../src/extensions/agent-team-loop/pm/pm-stage-source.ts";
import {
	ProductionRuntimeHost,
	type RuntimeOfferExpected,
	registerProductionRuntimeEvents,
} from "../../src/extensions/agent-team-loop/pm/runtime-host-adapter.ts";
import { dispatchTask } from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import { registerWorkerTools } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { sha256EolNormalizedBytes } from "../../src/extensions/agent-team-loop/shared/card-digest.ts";
import type {
	LocalExecutionRecordV1,
	LocalSelectionRecordV1,
} from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { readRunState } from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { createTestExtensionsResult, createTestResourceLoader } from "../utilities.ts";
import { createHarness } from "./harness.ts";

const roots: string[] = [];
afterEach(() => {
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

const KEY = "mw-pm-dp-continuity";
const CARD_PATH = "tasks/T15-J-pm-stage-qg-repair.md";
const SCOPE = "pm-stage-source-qg-repair-v1";
const MATTER = `${KEY}/T15-J`;
const PARENT_MATTER = KEY;
const STAGE_ID = "pm-stage-ac015";
const RECEIVED_AT = Date.parse("2026-11-18T10:00:00.000Z");
const NOW_MS = RECEIVED_AT + 5 * 60_000;

interface Fixture {
	root: string;
	home: string;
	claim: string;
	sessionId: string;
	eventId: string;
	grant: PmStageGrantV1;
	channel: PmChannel;
	entries: Array<{ id?: string; type?: string; customType?: string; data?: unknown }>;
	host: ProductionRuntimeHost;
	appendSource(direction: ReturnType<typeof findPmStageDirection>): void;
}

function fixture(
	options: {
		typed?: boolean;
		badReceiptDigest?: boolean;
		mutate?: (grant: PmStageGrantV1) => void;
		root?: string;
		key?: string;
		receivedAt?: number;
		durable?: boolean;
	} = {},
): Fixture {
	const root = options.root ?? fs.mkdtempSync(path.join(os.tmpdir(), "t15j-stage-root-"));
	const home = fs.mkdtempSync(path.join(os.tmpdir(), "t15j-stage-home-"));
	roots.push(root, home);
	const doc = path.join(root, ".agenticdoc");
	const key = options.key ?? KEY;
	const receivedAt = options.receivedAt ?? RECEIVED_AT;
	const now = options.receivedAt === undefined ? NOW_MS : receivedAt + 5_000;
	const claim = currentClaimId();
	const sessionId = randomUUID();
	const binding = randomUUID();
	const eventId = randomUUID();
	fs.mkdirSync(path.join(doc, key, "tasks"), { recursive: true });
	fs.writeFileSync(path.join(doc, "_index.parallel"), `| ${key} | active | EXECUTE | ${claim} | | | |\n`, "utf8");
	const cardText = [
		`owning_pm_claim: ${claim}`,
		"",
		"## 事项预算事实",
		`- \`budget_ref\`: \`${CARD_PATH}#事项预算事实\` + 其 SHA`,
		`- \`matter_ref\`: \`${MATTER}\`；\`parent_matter_ref\`: \`${PARENT_MATTER}\``,
		"- `deadline`: `run.json.started_at + 30m`（由 harness 派生）",
		"- `max_steps`: 4",
		"- `no_progress_limit`: 2",
		"- `remaining_cost`: 3，`cost_consumed` 与 `steps_consumed` 同单位（1 cost unit ≡ 1 tool call；卡明确约定）",
		"- `steps_consumed` / `no_progress_count`：本运行初始 0",
		"- `source_refs`: 卡 SHA、`run.json`、`_index.parallel`、`task.md` 头",
		"",
	].join("\n");
	fs.writeFileSync(path.join(doc, key, CARD_PATH), cardText, "utf8");
	const cardSha = sha256EolNormalizedBytes(Buffer.from(cardText, "utf8"));
	const channel = new PmChannel(root, home);
	fs.mkdirSync(channel.dir, { recursive: true });
	const grant: PmStageGrantV1 = {
		kind: "mw:pm-stage-grant-v1",
		authority: "user-delegated-duty-pm",
		project_ref: path.basename(channel.dir),
		key,
		stage_id: STAGE_ID,
		scope_ref: SCOPE,
		matter_ref: MATTER,
		parent_matter_ref: PARENT_MATTER,
		card_path: CARD_PATH,
		card_sha256: cardSha,
		write_face: ["packages/coding-agent/src/extensions/agent-team-loop/pm/runtime-host-adapter.ts"],
		max_steps: 4,
		remaining_cost: 3,
		no_progress_limit: 2,
		deadline: new Date(receivedAt + 60 * 60_000).toISOString(),
		qg_consumer: "local-qg-consumer-v1",
		allowed_disposition: "repair-required",
		producer_history: {
			matter_ref: PARENT_MATTER,
			steps_consumed: 4,
			deadline: new Date(receivedAt - 60 * 60_000).toISOString(),
			expired: true,
			source_ref: "pm-channel://expired-producer",
		},
	};
	options.mutate?.(grant);
	const typed = options.typed !== false;
	const digest = grantDigest(grant);
	const request = {
		id: eventId,
		key,
		claim,
		binding,
		text: "Continue the typed PM stage from the original sender",
		at: receivedAt - 1_000,
		...(typed ? { stage: grant } : {}),
	};
	const receipt = {
		state: "started",
		id: eventId,
		key,
		claim,
		binding,
		session: sessionId,
		receivedAt,
		observedAt: receivedAt + 1_000,
		observation: "Starting the typed stage admission",
		...(typed ? { stage_digest: options.badReceiptDigest ? "0".repeat(64) : digest } : {}),
	};
	const requestFile = channel.messagePath(key, binding, eventId, "request");
	const receiptFile = channel.messagePath(key, binding, eventId, "receipt");
	const windowFile = channel.windowPath(key, claim);
	fs.mkdirSync(path.dirname(requestFile), { recursive: true });
	fs.mkdirSync(path.dirname(windowFile), { recursive: true });
	fs.writeFileSync(requestFile, JSON.stringify(request), { mode: 0o600 });
	fs.writeFileSync(receiptFile, JSON.stringify(receipt), { mode: 0o600 });
	fs.writeFileSync(windowFile, JSON.stringify({ claim, binding, session: sessionId, at: now }), {
		mode: 0o600,
	});
	fs.writeFileSync(
		path.join(channel.dir, key, "_index.json"),
		JSON.stringify([{ event_id: eventId, state: "started", at: receivedAt }]),
		{ mode: 0o600 },
	);
	const entries: Fixture["entries"] = [];
	const sessionFile = path.join(root, "session.json");
	if (options.durable) fs.writeFileSync(sessionFile, `${JSON.stringify({ type: "session", id: sessionId })}\n`);
	const ctx = {
		sessionManager: {
			getEntries: () => entries,
			getSessionFile: () => sessionFile,
			getSessionId: () => sessionId,
		},
	} as unknown as ExtensionContext;
	const host = new ProductionRuntimeHost(root, () => now);
	host.attachSession(ctx, (customType, data) => {
		const entry = { id: randomUUID(), type: "custom", customType, data };
		entries.push(entry);
		if (options.durable) fs.appendFileSync(sessionFile, `${JSON.stringify(entry)}\n`);
	});
	return {
		root,
		home,
		claim,
		sessionId,
		eventId,
		grant,
		channel,
		entries,
		host,
		appendSource(direction: ReturnType<typeof findPmStageDirection>): void {
			if (!direction.ok) throw new Error(`expected typed direction: ${direction.reason}`);
			entries.push({
				type: "custom",
				customType: PM_STAGE_SOURCE_ENTRY_TYPE,
				data: {
					event_id: direction.value.event_id,
					stage_digest: direction.value.grant_digest,
					source_digest: stageSourceDigest(direction.value),
					source_text: "authenticated private-channel request + receipt + current window/session + pinned card",
				},
			});
		},
	};
}

function expected(f: Fixture, stageMatterRef = f.grant.matter_ref): RuntimeOfferExpected {
	return {
		matter_ref: f.grant.matter_ref,
		matter_version: "test-matter-v1",
		material_digest: "a".repeat(64),
		basis_digest: "b".repeat(64),
		matter_identity: "typed-pm-stage-matter",
		stage_matter_ref: stageMatterRef,
		identity: {
			key: f.grant.key,
			source: "pm",
			role: "pm",
			claimId: f.claim,
			taskKey: f.grant.stage_id,
			stageId: f.grant.stage_id,
			scopeRef: f.grant.scope_ref,
		},
	};
}

it("reserves one new allocation after a timeout and resumes queue publication with the persisted approval", async () => {
	const f = fixture({
		key: "demo",
		receivedAt: Date.now() - 60_000,
		durable: true,
		mutate(grant) {
			grant.write_face = ["src/recover.py"];
		},
	});
	const mw = path.resolve("../multi-workers");
	const wrapper = path.join(f.root, "mw-fixture");
	fs.mkdirSync(wrapper);
	fs.writeFileSync(path.join(wrapper, "mw.py"), "");
	const importer = [
		"import sys",
		"from pathlib import Path",
		`sys.path.insert(0, ${JSON.stringify(mw)})`,
		"import replan_tasks",
		`replan_tasks.Path.home = lambda: Path(${JSON.stringify(f.home)})`,
	].join("\n");
	fs.writeFileSync(path.join(wrapper, "replan_tasks.py"), `${importer}\nreplan_tasks.main()\n`);
	const setup = path.join(wrapper, "setup.py");
	fs.writeFileSync(
		setup,
		`${importer}
import json
from test_replan_tasks import fixture, deadline_plan
print(json.dumps(deadline_plan(fixture.__wrapped__(Path(sys.argv[1])), sys.argv[2], sys.argv[3], sys.argv[4])))
`,
	);
	const deadline = new Date(Date.now() + 5 * 60_000).toISOString();
	const [parent, pin] = JSON.parse(
		execFileSync(
			process.platform === "win32" ? "python" : "python3",
			["-B", "-X", "utf8", setup, f.root, f.claim, f.grant.matter_ref, deadline],
			{ encoding: "utf8" },
		),
	) as [string, string];
	expect(
		f.host.admitPmStageFromChannel({
			projectDir: f.root,
			home: f.home,
			claimId: f.claim,
			sessionId: f.sessionId,
		}).ok,
	).toBe(true);
	const doc = path.join(f.root, ".agenticdoc");
	const taskDir = path.join(doc, "demo", "workers", "recover");
	const taskPath = path.join(taskDir, "task.md");
	const oldDir = path.join(doc, "demo", "workers", "old");
	const oldRun = fs.readFileSync(path.join(oldDir, "run.json"), "utf8");
	const cardRef = "tasks/recover.md";
	const store = new WorkerStore(doc);
	const entry = { taskKey: "recover", status: "pending" as const, cli: "pi", provider: "", model: "", taskPath };
	const options = {
		card: {
			headerPath: cardRef,
			sha256: pin,
			resolvedPath: path.join(doc, "demo", cardRef),
			sections: { parentWorkerRun: parent },
		},
		publishCard() {
			fs.mkdirSync(taskDir, { recursive: true });
			fs.writeFileSync(
				taskPath,
				[
					"type: coding",
					"timeout: 8",
					`card_path: ${cardRef}`,
					`card_sha256: ${pin}`,
					`parent_worker_run: ${parent}`,
					"write_face: src/recover.py",
					"",
					"Check the remaining acceptance.",
					"",
				].join("\n"),
			);
		},
	};
	const rows = vi.spyOn(store, "upsertWithinLock").mockImplementationOnce(() => {
		throw new Error("simulated interruption after the budget was reserved");
	});
	const previousExit = process.exitCode;
	const listeners = new Set(process.listeners("exit"));
	vi.stubEnv("MW_PY", path.join(wrapper, "mw.py"));
	try {
		const pm = await createHarness({
			extensionFactories: [
				(pi) =>
					registerWorkerTools(pi, store, new AckStore(doc), new IndexStore(doc), doc, { key: "demo" }, f.root),
			],
		});
		try {
			pm.setResponses([
				fauxAssistantMessage(
					[fauxToolCall("read_worker_progress", { key: "demo", task_key: "old", run_id: parent })],
					{ stopReason: "toolUse" },
				),
				fauxAssistantMessage("Carry forward remaining verification."),
			]);
			await pm.session.prompt("Read the terminal evidence for the timed-out worker.");
			expect(pm.session.messages).toContainEqual(
				expect.objectContaining({
					role: "toolResult",
					toolName: "read_worker_progress",
					details: expect.objectContaining({
						run_id: parent,
						stop_kind: "worker-deadline",
						progress: expect.objectContaining({
							status: "stale",
							milestone: expect.objectContaining({ current: "finishing", remaining: "AC-002" }),
						}),
					}),
				}),
			);
		} finally {
			pm.cleanup();
		}
		await expect(dispatchTask(entry, store, { ...options, budgetHost: f.host })).rejects.toThrow(
			"simulated interruption",
		);
		expect(store.readAll().some((row) => row.taskKey === "recover")).toBe(false);
		expect(await dispatchTask(entry, store, options)).toEqual({ ok: true });
		expect(store.readAll().filter((row) => row.taskKey === "recover")).toHaveLength(1);
		expect(f.entries.filter((e) => JSON.stringify(e).includes('"kind":"reserve-child"'))).toHaveLength(1);
		expect(fs.readFileSync(taskPath, "utf8")).toContain(
			`deadline_successor: yes\nfixed_child_steps: 2\nfixed_child_deadline: ${deadline}`,
		);
		vi.stubEnv("PI_WORKER_TASK", taskPath);
		const worker = await createHarness({
			extensionFactories: [
				async (pi) => {
					await workerModeActivate(pi);
				},
			],
		});
		try {
			const newRun = readRunState(taskDir);
			expect(newRun).toMatchObject({ status: "running", parent_worker_run: parent, task_key: "recover" });
			expect(newRun?.run_id).not.toBe(parent);
			expect(fs.readFileSync(path.join(oldDir, "run.json"), "utf8")).toBe(oldRun);
		} finally {
			worker.cleanup();
		}
	} finally {
		rows.mockRestore();
		vi.unstubAllEnvs();
		for (const listener of process.listeners("exit")) {
			if (!listeners.has(listener)) process.off("exit", listener);
		}
		process.exitCode = previousExit;
	}
}, 20_000);

describe("T15-J typed PM stage source", () => {
	it("refuses the historical plain-text event with channel.typed-stage-grant-missing", () => {
		const f = fixture({ typed: false });
		const read = findPmStageDirection({
			projectDir: f.root,
			home: f.home,
			sessionId: f.sessionId,
			claimId: f.claim,
			nowMs: NOW_MS,
			eventId: f.eventId,
		});
		expect(read.ok).toBe(false);
		if (read.ok) return;
		expect(read.gaps).toContain("channel.typed-stage-grant-missing");
		expect(read.reason).toMatch(/plain text\/receipt\/eventId is not a grant/);
		const admitted = f.host.admitPmStageFromChannel({
			projectDir: f.root,
			home: f.home,
			sessionId: f.sessionId,
			claimId: f.claim,
			nowMs: NOW_MS,
		});
		expect(admitted.ok).toBe(false);
		expect(f.host.stageAdmissionState()).toMatchObject({
			admitted: false,
			refusal: { gaps: ["channel.typed-stage-grant-missing"] },
		});
		expect(f.host.stageIdentity()).toBeUndefined();
	});

	it("refuses a receipt whose typed grant digest does not match the original request", () => {
		const f = fixture({ badReceiptDigest: true });
		const read = findPmStageDirection({
			projectDir: f.root,
			home: f.home,
			sessionId: f.sessionId,
			claimId: f.claim,
			nowMs: NOW_MS,
			eventId: f.eventId,
		});
		expect(read.ok).toBe(false);
		if (read.ok) return;
		expect(read.gaps).toContain("stage.grant-digest");
	});

	it("automatically authors the typed session source from the validated private channel", () => {
		const f = fixture();
		const admitted = f.host.admitPmStageFromChannel({
			projectDir: f.root,
			home: f.home,
			sessionId: f.sessionId,
			claimId: f.claim,
			nowMs: NOW_MS,
		});
		expect(admitted.ok).toBe(true);
		expect(f.entries.filter((entry) => entry.customType === PM_STAGE_SOURCE_ENTRY_TYPE)).toHaveLength(1);
		expect(f.host.stageAdmissionState().admitted).toBe(true);
	});

	it("refuses wrong claim, invalid grant, wrong scope/matter, expired grant, over-limit grant and changed card pin", () => {
		const read = (f: Fixture, claimId = f.claim): ReturnType<typeof findPmStageDirection> =>
			findPmStageDirection({
				projectDir: f.root,
				home: f.home,
				sessionId: f.sessionId,
				claimId,
				nowMs: NOW_MS,
				eventId: f.eventId,
			});
		const foreign = read(fixture(), "foreign:1");
		expect(foreign.ok).toBe(false);
		if (!foreign.ok) expect(foreign.gaps).toContain("index.claim");
		const invalid = read(
			fixture({
				mutate: (g) => {
					(g as unknown as Record<string, unknown>).dp_decision_id = "forged";
				},
			}),
		);
		expect(invalid.ok).toBe(false);
		if (!invalid.ok) expect(invalid.gaps).toContain("stage.dp_decision_id");
		const wrongScope = read(
			fixture({
				mutate: (g) => {
					g.scope_ref = "wrong-scope";
				},
			}),
		);
		expect(wrongScope.ok).toBe(false);
		if (!wrongScope.ok) expect(wrongScope.gaps).toContain("stage.wrong-scope");
		const expired = read(
			fixture({
				mutate: (g) => {
					g.deadline = new Date(RECEIVED_AT - 1_000).toISOString();
				},
			}),
		);
		expect(expired.ok).toBe(false);
		if (!expired.ok) expect(expired.gaps).toContain("grant-expired");
		const overLimit = read(
			fixture({
				mutate: (g) => {
					g.max_steps = 5;
				},
			}),
		);
		expect(overLimit.ok).toBe(false);
		if (!overLimit.ok) expect(overLimit.gaps).toContain("stage.limits");
		const changedPin = read(
			fixture({
				mutate: (g) => {
					g.card_sha256 = "0".repeat(64);
				},
			}),
		);
		expect(changedPin.ok).toBe(false);
		if (!changedPin.ok) expect(changedPin.gaps).toContain("stage.card-pin");
		const wrongMatter = fixture({
			mutate: (g) => {
				g.matter_ref = `${MATTER}-other`;
			},
		});
		const wrongDirection = read(wrongMatter);
		expect(wrongDirection.ok).toBe(true);
		if (!wrongDirection.ok) return;
		wrongMatter.appendSource(wrongDirection);
		const refused = wrongMatter.host.admitPmStageFromChannel({
			projectDir: wrongMatter.root,
			home: wrongMatter.home,
			sessionId: wrongMatter.sessionId,
			claimId: wrongMatter.claim,
			nowMs: NOW_MS,
		});
		expect(refused.ok).toBe(false);
		if (!refused.ok) expect(refused.gaps).toContain("stage.card-budget");
	});

	it("keeps ONE finite genesis per stage lifecycle and refuses a second event id as a reset", () => {
		const first = fixture();
		const second = fixture();
		const d1 = findPmStageDirection({
			projectDir: first.root,
			home: first.home,
			sessionId: first.sessionId,
			claimId: first.claim,
			nowMs: NOW_MS,
			eventId: first.eventId,
		});
		const d2 = findPmStageDirection({
			projectDir: second.root,
			home: second.home,
			sessionId: second.sessionId,
			claimId: second.claim,
			nowMs: NOW_MS,
			eventId: second.eventId,
		});
		expect(d1.ok && d2.ok).toBe(true);
		if (!d1.ok || !d2.ok) return;
		const entries: Array<{ type: string; customType: string; data: unknown }> = [];
		const session = {
			read: () => ({ entries }),
			append: (customType: string, data: unknown) => {
				entries.push({ type: "custom", customType, data });
			},
		};
		const ledger = new PmStageLedger();
		expect(ledger.admit(session, d1.value).ok).toBe(true);
		const replay = ledger.admit(session, d2.value);
		expect(replay.ok).toBe(false);
		if (!replay.ok) expect(replay.gaps).toContain("stage-lifecycle-replay");
		const same = ledger.admit(session, d1.value);
		expect(same.ok).toBe(true);
		if (same.ok) expect(same.value.replayed).toBe(true);
	});

	it("admits a REAL PM stage without a worker dispatch/run and binds the stage matter to offers", () => {
		const f = fixture();
		const direction = findPmStageDirection({
			projectDir: f.root,
			home: f.home,
			sessionId: f.sessionId,
			claimId: f.claim,
			nowMs: NOW_MS,
			eventId: f.eventId,
		});
		expect(direction.ok).toBe(true);
		if (!direction.ok) return;
		expect(direction.value.authority_kind).toBe("user-delegated-duty-pm");
		expect(direction.value.stage_ref).toMatch(/^pm-channel:\/\//);
		f.appendSource(direction);
		const admitted = f.host.admitPmStageFromChannel({
			projectDir: f.root,
			home: f.home,
			sessionId: f.sessionId,
			claimId: f.claim,
			nowMs: NOW_MS,
		});
		expect(admitted.ok).toBe(true);
		expect(f.host.stageAdmissionState()).toMatchObject({
			admitted: true,
			attribution: {
				authority_kind: "user-delegated-duty-pm",
				stage_matter_ref: MATTER,
				limits: { max_steps: 4, remaining_cost: 3, no_progress_limit: 2 },
				producer: { expired: true, immutable: true, borrowed: false },
			},
		});
		expect(f.host.stageIdentity()).toMatchObject({
			key: KEY,
			claimId: f.claim,
			stageId: STAGE_ID,
			scopeRef: SCOPE,
			matterRef: MATTER,
			grantDigest: grantDigest(f.grant),
		});
		expect(f.host.authorizationGapsFor(expected(f))).toEqual([]);
		expect(f.host.authorizationGapsFor(expected(f, `${MATTER}-drift`))).toEqual(["host.authorization-binding-drift"]);
		expect(fs.existsSync(path.join(f.root, ".agenticdoc", KEY, "workers", STAGE_ID, "run.json"))).toBe(false);
		const qg = f.host.evaluateLocalQg({ localRef: "selection:none", actionToolCallId: "tool:none" });
		expect(qg).toMatchObject({
			verdict: "insufficient",
			qg_pass: false,
			gate_released: false,
			sign_written: false,
			business_completed: false,
		});
	});
});

describe("T15-L production lifecycle composition", () => {
	it("automatically authors the typed source before a real agent tool call", async () => {
		const f = fixture();
		const host = new ProductionRuntimeHost(f.root, () => NOW_MS);
		let executed = 0;
		const h = await createHarness({
			extensionFactories: [
				(pi) => {
					registerProductionRuntimeEvents(pi, host, {
						pmStage: { projectDir: f.root, home: f.home, claimId: f.claim, nowMs: NOW_MS },
					});
					pi.registerTool({
						name: "read",
						label: "read",
						description: "event probe",
						parameters: Type.Object({ path: Type.String() }),
						execute: async () => {
							executed += 1;
							expect(host.stageIdentity()?.stageId).toBe(STAGE_ID);
							return { content: [{ type: "text", text: "observed" }], details: {} };
						},
					});
				},
			],
		});
		try {
			const directory = path.join(f.channel.dir, KEY);
			for (const binding of fs
				.readdirSync(directory, { withFileTypes: true })
				.filter((entry) => entry.isDirectory())) {
				const file = f.channel.messagePath(KEY, binding.name, f.eventId, "receipt");
				const receipt = JSON.parse(fs.readFileSync(file, "utf8"));
				fs.writeFileSync(file, JSON.stringify({ ...receipt, session: h.sessionManager.getSessionId() }));
				fs.writeFileSync(
					f.channel.windowPath(KEY, f.claim),
					JSON.stringify({
						claim: f.claim,
						binding: binding.name,
						session: h.sessionManager.getSessionId(),
						at: NOW_MS,
					}),
				);
			}
			await h.session.bindExtensions({});
			h.setResponses([
				fauxAssistantMessage([fauxToolCall("read", { path: "probe" })], { stopReason: "toolUse" }),
				fauxAssistantMessage("done"),
			]);
			await h.session.prompt("observe the production stage lifecycle");
			expect(executed).toBe(1);
			expect(host.stageAdmissionState().admitted).toBe(true);
			expect(
				h.sessionManager
					.getEntries()
					.filter((entry) => entry.type === "custom" && entry.customType === PM_STAGE_SOURCE_ENTRY_TYPE),
			).toHaveLength(1);
		} finally {
			h.cleanup();
		}
	});
});

async function liveStage(channelFirst: boolean) {
	const resources = createTestResourceLoader();
	const h = await createHarness({ resourceLoader: resources });
	const f = fixture({ root: h.tempDir });
	// Baseline fixture delivery is removed. Only the real sender/receiver may
	// create the request, receipt and heartbeat used by these event tests.
	fs.rmSync(f.channel.dir, { recursive: true, force: true });
	f.grant.deadline = new Date(Date.now() + 60 * 60_000).toISOString();
	if (f.grant.producer_history) f.grant.producer_history.deadline = new Date(Date.now() - 60 * 60_000).toISOString();
	fs.mkdirSync(path.join(f.root, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(f.root, ".mw", "decide.json"), JSON.stringify({ enabled: false }));
	const target = f.grant.write_face[0]!;
	fs.mkdirSync(path.dirname(path.join(f.root, target)), { recursive: true });
	fs.writeFileSync(path.join(f.root, target), "initial\n");
	const host = new ProductionRuntimeHost(f.root);
	const states: Array<{ receipt: unknown; admitted: boolean }> = [];
	let writes = 0;
	let lastBinding: string | undefined;
	const loaded = await createTestExtensionsResult(
		[
			(pi) => {
				if (channelFirst) registerPmChannel(pi, f.home);
				registerProductionRuntimeEvents(pi, host, { pmStage: { projectDir: f.root, home: f.home } });
				if (!channelFirst) registerPmChannel(pi, f.home);
				const submitHandle = registerSubmitDecisionHandoffTool(pi, {
					projectDir: f.root,
					hostRuntime: host,
					runtimeHost: host.adapterHooks(),
				});
				registerAskDecisionTool(pi, {
					projectDir: f.root,
					initiatorRole: "pm",
					submitHandle,
					stageSource: () => host.stageIdentity(),
				});
				pi.on("tool_call", () => {
					if (lastBinding)
						states.push({
							receipt: f.channel.receipt(KEY, lastBinding, f.eventId).state,
							admitted: host.stageAdmissionState().admitted,
						});
				});
				pi.registerTool({
					name: "write",
					label: "write",
					description: "event-owned controlled write",
					parameters: Type.Object({ path: Type.String(), content: Type.String() }),
					execute: async (_id, params) => {
						writes += 1;
						fs.writeFileSync(path.join(f.root, params.path), params.content);
						return {
							content: [{ type: "text", text: "wrote actual target" }],
							details: { review: { origin: "independent-review", verdict: "pass" }, business_completed: true },
						};
					},
				});
			},
		],
		f.root,
	);
	Object.assign(resources.getExtensions(), loaded);
	await h.session.reload();
	// reload resets the compatibility API registry. Reinstall only the faux API,
	// never a real endpoint, and use this registration's fresh response queue.
	let faux = registerFauxProvider({ api: h.faux.api, provider: h.getModel().provider });
	await h.session.bindExtensions({ mode: "tui" });
	const details = (name: string): Record<string, unknown> => {
		const message = [...h.session.messages]
			.reverse()
			.find((message) => message.role === "toolResult" && message.toolName === name);
		return message?.role === "toolResult" ? (message.details as Record<string, unknown>) : {};
	};
	return {
		h,
		f,
		host,
		states,
		details,
		setResponses: (responses: Parameters<typeof faux.setResponses>[0]) => faux.setResponses(responses),
		async reload(): Promise<void> {
			await h.session.reload();
			faux.unregister();
			faux = registerFauxProvider({ api: h.faux.api, provider: h.getModel().provider });
			await h.session.bindExtensions({ mode: "tui" });
		},
		writes: () => writes,
		async deliver(typed = true): Promise<void> {
			const state = f.channel.status(KEY);
			if (!state.binding) throw new Error("real receiver not connected");
			lastBinding = state.binding;
			f.channel.send(
				KEY,
				state.binding,
				f.eventId,
				"faux test direction, not live authorization",
				undefined,
				typed ? f.grant : undefined,
			);
			await vi.waitFor(() => expect(f.channel.receipt(KEY, state.binding!, f.eventId).state).toBe("started"), {
				timeout: 8_000,
				interval: 20,
			});
			await vi.waitFor(() => expect(h.session.isStreaming).toBe(false), { timeout: 8_000, interval: 20 });
		},
		async promptTool(name: string, args: Record<string, unknown>): Promise<void> {
			faux.setResponses([
				fauxAssistantMessage([fauxToolCall(name, args)], { stopReason: "toolUse" }),
				fauxAssistantMessage("done"),
			]);
			await h.session.prompt(`event lifecycle ${name}`);
		},
		async cleanup() {
			await emitSessionShutdownEvent(h.session.extensionRunner, { type: "session_shutdown", reason: "quit" });
			faux.unregister();
			h.cleanup();
		},
	};
}

const liveAsk = {
	dp: "dp-auto",
	trigger: STAGE_ID,
	key: KEY,
	material: {
		question: "Choose one bounded event-harness action",
		background: {
			task_goal: "Test production wiring",
			current_state: "Typed stage admitted by real receiver",
			tried: "none",
			unknowns: "none",
			constraints: "one finite write; no review or release",
		},
		handling_options: [
			{
				id: "continue",
				label: "Continue",
				description: "One controlled write",
				consequence: "byte observation only",
				risk: "isolated fixture",
				conditions: "trusted host source",
			},
			{
				id: "defer",
				label: "Defer",
				description: "No action",
				consequence: "no effect",
				risk: "none",
				conditions: "no further authority",
			},
		],
	},
	preparation: {
		prepared_at: new Date().toISOString(),
		basis_catalog: [
			{
				id: "basis",
				text: "Authenticated stage and finite card",
				material_refs: ["background.current_state"],
				applies_to: ["continue"],
			},
		],
	},
};

for (const channelFirst of [false, true]) {
	it(`real receipt -> in-run stage -> ask/submit -> actual result -> typed insufficient (channelFirst=${channelFirst})`, async () => {
		const live = await liveStage(channelFirst);
		try {
			live.setResponses([fauxAssistantMessage("prior assistant history")]);
			await live.h.session.prompt("an earlier unrelated turn");
			expect(live.host.stageAdmissionState().admitted).toBe(false);
			live.setResponses([
				fauxAssistantMessage([fauxToolCall(ASK_DECISION_TOOL, liveAsk)], { stopReason: "toolUse" }),
				fauxAssistantMessage("offer prepared"),
			]);
			await live.deliver();
			expect(live.states[0]).toEqual({ receipt: "started", admitted: true });
			const offer = live.details(ASK_DECISION_TOOL).submit_offer as
				| { offer_id?: string; submittable?: boolean }
				| undefined;
			expect(offer?.submittable, JSON.stringify(live.details(ASK_DECISION_TOOL))).toBe(true);
			await live.promptTool(SUBMIT_DECISION_HANDOFF_TOOL, {
				offer_id: offer?.offer_id,
				choice: "continue",
				basis_id: "basis",
			});
			expect(
				live.details(SUBMIT_DECISION_HANDOFF_TOOL),
				JSON.stringify(live.details(SUBMIT_DECISION_HANDOFF_TOOL)),
			).toMatchObject({ status: "planned", business_completed: false });
			await live.promptTool("write", { path: live.f.grant.write_face[0], content: "changed\n" });
			expect(live.writes(), JSON.stringify(live.details("write"))).toBe(1);
			expect(live.host.countsSnapshot()).toMatchObject({ reserves: 1, observes: 1, appends: 1, dispositions: 1 });
			const qg = live.h.sessionManager
				.getEntries()
				.filter((entry) => entry.type === "custom" && entry.customType === "mw-local-qg-result-v1");
			expect(qg).toHaveLength(1);
			expect(qg[0]).toMatchObject({
				data: {
					review_source: "missing-independent-current-stage-review",
					disposition: {
						verdict: "insufficient",
						gaps: ["empty-result-no-release"],
						qg_pass: false,
						gate_released: false,
						sign_written: false,
						business_completed: false,
					},
				},
			});
			const sourceCount = live.h.sessionManager
				.getEntries()
				.filter((entry) => entry.type === "custom" && entry.customType === PM_STAGE_SOURCE_ENTRY_TYPE).length;
			const genesisCount = () =>
				live.h.sessionManager
					.getEntries()
					.filter((entry) => entry.type === "custom" && entry.customType === PM_STAGE_ENTRY_TYPE).length;
			expect(genesisCount()).toBe(1);
			await live.promptTool(SUBMIT_DECISION_HANDOFF_TOOL, {
				offer_id: offer?.offer_id,
				choice: "continue",
				basis_id: "basis",
			});
			expect(live.host.countsSnapshot().reserves).toBe(1);
			// A new host object reads the same actual persisted session. It may
			// replay its budget, but cannot recover all three cost units after one
			// was genuinely consumed by the controlled write above.
			const restarted = new ProductionRuntimeHost(live.f.root);
			restarted.attachSession(live.h.session.extensionRunner.createContext(), (type, data) =>
				live.h.sessionManager.appendCustomEntry(type, data),
			);
			const admitted = restarted.admitPmStageFromChannel({
				projectDir: live.f.root,
				home: live.f.home,
				sessionId: live.h.sessionManager.getSessionId(),
			});
			expect(admitted.ok, JSON.stringify(admitted)).toBe(true);
			expect(restarted.countsSnapshot().replayedActionRefs).toBeGreaterThanOrEqual(2);
			const replenished = restarted.reserveChild({
				taskKey: STAGE_ID,
				reservationId: "cannot-reset-spent-cost",
				steps: 3,
				cost: 3,
				deadline: new Date(Date.now() + 10 * 60_000).toISOString(),
			});
			expect(replenished.ok, JSON.stringify(replenished)).toBe(false);
			if (!replenished.ok) expect(replenished.gaps).toContain("insufficient-remaining");
			// A real receiver reload rotates its private binding. The old grant
			// cannot silently migrate to that binding or reopen a fresh genesis.
			await live.reload();
			expect(live.host.stageAdmissionState().admitted).toBe(false);
			await live.promptTool(SUBMIT_DECISION_HANDOFF_TOOL, {
				offer_id: offer?.offer_id,
				choice: "continue",
				basis_id: "basis",
			});
			expect(live.details(SUBMIT_DECISION_HANDOFF_TOOL).status).not.toBe("planned");
			expect(live.host.countsSnapshot().reserves).toBe(1);
			expect(genesisCount()).toBe(1);
			expect(
				live.h.sessionManager
					.getEntries()
					.filter((entry) => entry.type === "custom" && entry.customType === PM_STAGE_SOURCE_ENTRY_TYPE),
			).toHaveLength(sourceCount);
		} finally {
			await live.cleanup();
		}
	}, 20_000);
}

for (const refusal of ["plain", "cancel", "card-drift", "claim-drift", "binding-drift"] as const) {
	it(`real channel/event refusal remains closed: ${refusal}`, async () => {
		const live = await liveStage(false);
		try {
			live.setResponses([
				fauxAssistantMessage([fauxToolCall(ASK_DECISION_TOOL, liveAsk)], { stopReason: "toolUse" }),
				fauxAssistantMessage("done"),
			]);
			await live.deliver(refusal !== "plain");
			const offer = live.details(ASK_DECISION_TOOL).submit_offer as { offer_id?: string } | undefined;
			if (refusal === "cancel") {
				const state = live.f.channel.status(KEY);
				const receipt = live.f.channel.messagePath(KEY, state.binding!, live.f.eventId, "receipt");
				// Isolated negative tamper: the real STARTED receipt is revoked.
				fs.writeFileSync(
					receipt,
					JSON.stringify({ ...JSON.parse(fs.readFileSync(receipt, "utf8")), state: "canceled" }),
				);
			} else if (refusal === "card-drift") {
				fs.appendFileSync(path.join(live.f.root, ".agenticdoc", KEY, CARD_PATH), "\nchanged pinned card\n");
			} else if (refusal === "claim-drift") {
				const index = path.join(live.f.root, ".agenticdoc", "_index.parallel");
				fs.writeFileSync(index, fs.readFileSync(index, "utf8").replace(live.f.claim, "another-host:999"));
			} else if (refusal === "binding-drift") {
				const window = live.f.channel.windowPath(KEY, live.f.claim);
				fs.writeFileSync(
					window,
					JSON.stringify({ ...JSON.parse(fs.readFileSync(window, "utf8")), binding: randomUUID() }),
				);
			}
			await live.promptTool(SUBMIT_DECISION_HANDOFF_TOOL, {
				offer_id: offer?.offer_id ?? "no-typed-offer",
				choice: "continue",
				basis_id: "basis",
			});
			expect(live.host.stageAdmissionState().admitted, JSON.stringify(live.host.stageAdmissionState())).toBe(false);
			if (refusal === "plain")
				expect(live.host.stageAdmissionState().refusal?.gaps).toContain("channel.typed-stage-grant-missing");
			expect(live.details(SUBMIT_DECISION_HANDOFF_TOOL).business_completed).toBe(false);
			expect(live.details(SUBMIT_DECISION_HANDOFF_TOOL).status).not.toBe("planned");
			expect(live.writes()).toBe(0);
			expect(live.host.countsSnapshot().reserves).toBe(0);
			expect(
				live.h.sessionManager
					.getEntries()
					.filter((entry) => entry.type === "custom" && entry.customType === "mw-local-qg-result-v1"),
			).toHaveLength(0);
		} finally {
			await live.cleanup();
		}
	}, 20_000);
}

describe("T15-J typed local QG consumer", () => {
	const stage = {
		authority_kind: "user-delegated-duty-pm" as const,
		key: KEY,
		claim_id: "claim",
		stage_id: STAGE_ID,
		scope_ref: SCOPE,
		matter_ref: MATTER,
		grant_digest: "a".repeat(64),
	};
	const binding = {
		role: "pm" as const,
		owner: "claim",
		claim_id: "claim",
		key: KEY,
		binding_version: "test-binding-v1",
		observed_at: new Date(RECEIVED_AT).toISOString(),
	};
	const selection: LocalSelectionRecordV1 = {
		schema_version: 1,
		kind: "local-selection",
		origin: "local-decision",
		source: "pm",
		local_ref: "selection:current",
		matter_ref: MATTER,
		host_binding: binding,
		matter_version: "test-matter-v1",
		material_digest: "c".repeat(64),
		basis_digest: "d".repeat(64),
		selected_action: "continue",
		selected_basis_id: "basis",
		budget_ref: `${CARD_PATH}#事项预算事实`,
		action_state: "planned",
		business_completed: false,
		created_at: new Date(RECEIVED_AT).toISOString(),
	};
	const execution: LocalExecutionRecordV1 = {
		schema_version: 1,
		kind: "local-execution",
		origin: "local-decision",
		source: "pm",
		local_ref: selection.local_ref,
		host_binding: binding,
		action_ref: "tool:real-1",
		result_ref: "result:real-1",
		executor: "runtime-execution-v1",
		target_digest: "e".repeat(64),
		observed_effect: "target bytes changed; business-correctness=unverified",
		effect_state: "known",
		verified_by: "target-digest-v1",
		budget_ref: `${CARD_PATH}#事项预算事实`,
		created_at: new Date(RECEIVED_AT + 2_000).toISOString(),
	};
	const observation = {
		tool_call_id: execution.action_ref,
		local_ref: selection.local_ref,
		result_ref: execution.result_ref,
		executor: execution.executor,
		run_id: `pm-stage:${STAGE_ID}`,
		is_error: false,
		completion: "complete" as const,
	};
	function review(verdict: "fix" | "partial" | "pass" | "empty"): LocalQgReview {
		const facts = {
			origin: "independent-review" as const,
			verdict,
			selection_ref: selection.local_ref,
			execution_ref: execution.result_ref,
			tool_call_ref: execution.action_ref,
			verifier_ref: LOCAL_QG_VERIFIER,
			reviewed_at: new Date(RECEIVED_AT + 3_000).toISOString(),
			findings: verdict === "empty" ? [] : ["PARTIAL: current-ref business review is incomplete"],
			refs:
				verdict === "empty"
					? []
					: ["packages/coding-agent/src/extensions/agent-team-loop/pm/runtime-host-adapter.ts:1"],
		};
		return { ...facts, source_digest: localQgReviewDigest(facts) };
	}

	it("never releases a QG gate from a planned selection or empty/byte-only result", () => {
		const selectionOnly = evaluateLocalQg({
			stage,
			selection,
			execution: undefined,
			observation: undefined,
			review: undefined,
		});
		expect(selectionOnly).toMatchObject({
			verdict: "insufficient",
			qg_pass: false,
			gate_released: false,
			sign_written: false,
			business_completed: false,
		});
		expect(selectionOnly.gaps).toEqual(
			expect.arrayContaining(["selection-only-no-release", "business-result-empty"]),
		);
		const byteOnly = evaluateLocalQg({ stage, selection, execution, observation, review: review("empty") });
		expect(byteOnly).toMatchObject({
			verdict: "insufficient",
			qg_pass: false,
			gate_released: false,
			sign_written: false,
			business_completed: false,
		});
		expect(byteOnly.gaps).toContain("empty-result-no-release");
	});

	it("rejects a copied/non-current review digest as business verification", () => {
		const stale = { ...review("fix"), source_digest: "f".repeat(64) };
		const result = evaluateLocalQg({ stage, selection, execution, observation, review: stale });
		expect(result).toMatchObject({
			verdict: "insufficient",
			qg_pass: false,
			gate_released: false,
			sign_written: false,
			business_completed: false,
		});
		expect(result.gaps).toEqual(
			expect.arrayContaining(["business-verification-missing", "byte-proof-not-business-verification"]),
		);
	});

	it("returns ONLY repair-required for PARTIAL/fix and fails closed on PASS", () => {
		for (const verdict of ["partial", "fix"] as const) {
			const result = evaluateLocalQg({ stage, selection, execution, observation, review: review(verdict) });
			expect(result).toMatchObject({
				verdict: "repair-required",
				qg_pass: false,
				gate_released: false,
				sign_written: false,
				business_completed: false,
				result_consumer: "owning-pm:repair",
				target_verifier: LOCAL_QG_VERIFIER,
			});
			expect(result.findings.length).toBeGreaterThan(0);
			if (verdict === "partial") expect(result.gaps).toContain("partial-review-no-pass");
		}
		const pass = evaluateLocalQg({ stage, selection, execution, observation, review: review("pass") });
		expect(pass).toMatchObject({
			verdict: "unsupported-pass",
			qg_pass: false,
			gate_released: false,
			sign_written: false,
			business_completed: false,
		});
		expect(pass.gaps).toContain("pass-path-unsupported");
	});
});
