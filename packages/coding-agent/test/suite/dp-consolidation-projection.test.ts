import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import { renderGateCards } from "../../src/extensions/agent-team-loop/autopilot/console.ts";
import {
	type GateRecord,
	MISSING_FIELD_SENTINEL,
	parseGateFile,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import type { DecideRunner } from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import {
	parseDecideSignOutcome,
	registerWorkerTools,
	runMwDecideCommand,
	windowClaimId,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { createHarness, getMessageText, type Harness } from "./harness.ts";

describe("T30 typed key signoff projection", () => {
	const proof = {
		dp: "dp-sign-key",
		key: "projection-window",
		logical_id: "sign-fixture",
		decision_id: "dp-sign-key:sign-fixture",
		conclusion: "finalize",
		signoff_status: "written",
		signoff_path: "projection-window/evidence/review/sign-final.md",
	};

	it.each([
		{ path: "somewhere.md" },
		{ signed_via: "anything" },
		{ ...proof, conclusion: "continue" },
		{ ...proof, conclusion: "user-confirm" },
		{ ...proof, conclusion: "narrow" },
		{ ...proof, signoff_status: undefined },
		{ ...proof, signoff_status: "disabled" },
		{ ...proof, decision_id: undefined },
		{ ...proof, decision_id: "dp-sign-key:another-request" },
		{ ...proof, logical_id: undefined },
		{ ...proof, key: "" },
		{ ...proof, signoff_path: undefined },
		{ ...proof, signoff_status: "not-required" },
		{ ...proof, dp: "dp25-signoff-conclusion" },
	])("refuses incomplete or nonfinalize proof %j", (payload) => {
		expect(parseDecideSignOutcome(JSON.stringify(payload)).signed).toBe(false);
	});

	it.each(["written", "existing"])(
		"displays only typed finalize %s without authority or completion claims",
		async (status) => {
			const fixture = await windowFixture();
			const notify = vi.fn();
			const context = { hasUI: true, ui: { notify } } as unknown as ExtensionCommandContext;
			const runner = vi.fn(() => ({
				ok: true as const,
				output: JSON.stringify({ ...proof, signoff_status: status }),
			}));
			const text = await runMwDecideCommand(context, fixture.project, "sign", {
				runner,
				watchKey: () => OWNER,
			});
			expect(text).toContain(`已签收 ${OWNER}`);
			expect(text).toContain("conclusion: finalize");
			expect(text).not.toContain("authority-change");
			expect(text).not.toMatch(/stage.*closed|phase.*done|task completed/);
			expect(notify).toHaveBeenCalledWith(text, "info");
		},
	);
});

describe("T30 no-stdin sign refusal", () => {
	it("reports the CLI refusal and directs callers to the prepared producer", async () => {
		const fixture = await windowFixture();
		const notify = vi.fn();
		const context = { hasUI: true, ui: { notify } } as unknown as ExtensionCommandContext;
		const runner = vi.fn(() => ({ ok: false as const, error: "PM material required; nothing was written" }));
		const text = await runMwDecideCommand(context, fixture.project, "sign", { runner, watchKey: () => OWNER });
		expect(runner).toHaveBeenCalledTimes(1);
		expect(runner).toHaveBeenCalledWith(fixture.project, ["sign", "--key", OWNER, "--dry-run", "--json"]);
		expect(text).toContain("nothing was written");
		expect(text).toContain("ask_decision dp-sign-key");
		expect(text).toContain("preparation");
		expect(text).not.toContain("已签收");
		expect(text).not.toContain("authority-change");
		expect(notify).toHaveBeenCalledWith(text, "error");
	});
});

const OWNER = "projection-window";
const TASK = "prepared-window-task";
const projects: string[] = [];
const harnesses: Harness[] = [];

afterEach(() => {
	for (const harness of harnesses.splice(0)) harness.cleanup();
	for (const project of projects.splice(0)) fs.rmSync(project, { recursive: true, force: true });
});

async function windowFixture() {
	const project = fs.mkdtempSync(path.join(os.tmpdir(), "dpc-window-projection-"));
	projects.push(project);
	const root = path.join(project, ".agenticdoc");
	const keyDir = path.join(root, OWNER);
	fs.mkdirSync(path.join(project, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(project, ".mw/decide.json"), JSON.stringify({ enabled: false }));
	fs.mkdirSync(path.join(keyDir, "evidence/research"), { recursive: true });
	fs.mkdirSync(path.join(keyDir, "tasks"));
	fs.writeFileSync(path.join(root, "goal.md"), "# Goal\nKeep the authorized task moving.\n");
	fs.writeFileSync(
		path.join(root, "_index.parallel"),
		`| ${OWNER} | active | EXECUTE | ${windowClaimId()} | | fixture | 2026-11-10 |\n`,
	);
	fs.writeFileSync(path.join(keyDir, "spec.md"), `# Spec\n${"x".repeat(600)}\n| AC-001 | authorized work |\n`);
	fs.writeFileSync(path.join(keyDir, "design.md"), `# Design\n${"x".repeat(600)}\n`);
	fs.writeFileSync(path.join(keyDir, "evidence/research/spec-window-2026-11-10.md"), "# Spec research\n");
	fs.writeFileSync(path.join(keyDir, "evidence/research/design-window-2026-11-10.md"), "# Design research\n");
	const card = path.join(keyDir, "tasks/window.md");
	fs.writeFileSync(
		card,
		[
			"type: coding",
			"",
			"## 上下文",
			".agenticdoc/goal.md:1; implement the authorized window task.",
			"",
			"## 要求",
			"Preserve the requested deliverable and its evidence.",
			"",
			"## 交付格式",
			"Report the changed file and its verification.",
			"",
			"## 写入允许面",
			"- result.txt",
			"",
			"## 写入禁止面",
			"- credentials/",
			"",
			"## 验收命令",
			"node --version",
			"",
			"## 改动历史",
			"Initial authorized dispatch.",
			"",
		].join("\n"),
	);
	const store = new WorkerStore(root);
	const decisions = vi.fn<DecideRunner>(() => {
		throw new Error("disabled decision service must not be called");
	});
	const harness = await createHarness({
		extensionFactories: [
			(pi) => {
				registerWorkerTools(
					pi,
					store,
					new AckStore(root),
					new IndexStore(root),
					root,
					{ key: OWNER },
					project,
					decisions,
				);
			},
		],
	});
	harnesses.push(harness);
	return { project, root, card, store, harness, decisions };
}

async function dispatch(harness: Harness, card: string, task = TASK, key = OWNER): Promise<string> {
	harness.setResponses([
		fauxAssistantMessage(
			fauxToolCall("dispatch_worker", {
				task_key: task,
				key,
				type: "coding",
				card_path: card,
				description: "Implement the already authorized task.",
				decision_preparation: {
					prepared_at: "2026-11-10T00:00:00Z",
					basis_catalog: [
						{
							id: "prepared",
							text: "The deliverable requires implementation.",
							material_refs: ["task_deliverables"],
							applies_to: ["coding"],
						},
					],
				},
			}),
			{ stopReason: "toolUse" },
		),
		fauxAssistantMessage("reported"),
	]);
	await harness.session.prompt("Dispatch this authorized card.");
	const results = harness.session.messages.filter((message) => message.role === "toolResult");
	return getMessageText(results.at(-1));
}

function gate(overrides: Partial<GateRecord> = {}): GateRecord {
	return {
		id: "gate-0001",
		kind: "stage-close",
		status: "pending",
		stage: 1,
		key: OWNER,
		question: "Close the prepared stage?",
		createdAt: "2026-11-09T00:00:00Z",
		path: "fixture/gate-0001.md",
		contextRefs: [],
		evidenceRefs: [],
		reasonCode: null,
		observedAt: null,
		subjectSha256: null,
		proposalSha256: null,
		goalSha256: null,
		loop: null,
		usedRounds: null,
		roundLimit: null,
		creditsUsed: null,
		verdictsFinal: null,
		openItems: null,
		roadmapValidation: null,
		constraints: [],
		answerSource: null,
		expiresAt: null,
		defaultAction: null,
		outOfBandActions: [],
		authorizes: [],
		blockerClass: null,
		gateSchema: 2,
		answeredAt: "2026-11-09T00:00:01Z",
		answeredBy: null,
		note: null,
		decision: {
			transport: "answered",
			business: "approve",
			effect: "in-progress",
			decisionRef: "dp-gate-approve:fixture",
			matterRef: "stage:fixture:close",
			substantiveVersion: "version-1",
			pmNote: "PM: close only the current stage",
			modelBasis: "prepared basis: required evidence is complete",
			closureKind: null,
		},
		...overrides,
	};
}

describe("T30 real window tool with decisions disabled (harness and faux)", () => {
	it("queues authorized coding without asking the disabled decision service or claiming task completion", async () => {
		const fixture = await windowFixture();
		const text = await dispatch(fixture.harness, fixture.card);
		expect(text).toContain("Dispatched worker");
		expect(fixture.decisions).not.toHaveBeenCalled();
		expect(fixture.store.readAll()).toMatchObject([{ taskKey: TASK, status: "pending" }]);
		const taskPath = path.join(fixture.root, OWNER, "workers", TASK, "task.md");
		const task = fs.readFileSync(taskPath, "utf8");
		expect(task).toContain("Preserve the requested deliverable and its evidence.");
		expect(task).not.toContain("decision-id:");
		expect(text).not.toContain("task completed");
	});

	it("refuses duplicate dispatch and preserves the original task bytes", async () => {
		const fixture = await windowFixture();
		expect(await dispatch(fixture.harness, fixture.card)).toContain("Dispatched worker");
		const taskPath = path.join(fixture.root, OWNER, "workers", TASK, "task.md");
		const before = fs.readFileSync(taskPath);
		expect(await dispatch(fixture.harness, fixture.card)).toContain("already exists");
		expect(fs.readFileSync(taskPath)).toEqual(before);
		expect(fixture.store.readAll()).toHaveLength(1);
		expect(fixture.decisions).not.toHaveBeenCalled();
	});

	it("keeps the card hard gate when decisions are disabled", async () => {
		const fixture = await windowFixture();
		fs.writeFileSync(fixture.card, "type: coding\n\nAn incomplete card.\n");
		expect(await dispatch(fixture.harness, fixture.card)).toContain("dispatch refused");
		expect(fixture.store.readAll()).toEqual([]);
		expect(fs.existsSync(path.join(fixture.root, OWNER, "workers", TASK))).toBe(false);
		expect(fixture.decisions).not.toHaveBeenCalled();
	});
});

// GateRecord fixtures below exercise the real console projection only. They
// are not a substitute for the native producer/writer/consumer usage chain.
describe("T30 console decision facts", () => {
	it("shows an answered selection whose effect is still in progress, with separate note and prepared basis", async () => {
		const fixture = await windowFixture();
		const text = renderGateCards([gate()], fixture.project, Date.now()).join("\n");
		expect(text).toContain("transport=answered business=approve effect=in-progress");
		expect(text).toContain("pm-note: PM: close only the current stage");
		expect(text).toContain("model-basis: prepared basis: required evidence is complete");
		expect(text).toContain("decision-ref: dp-gate-approve:fixture");
		expect(text).toContain(`task-completion: ${MISSING_FIELD_SENTINEL}`);
		expect(text).not.toContain("stage -> closed");
	});

	it.each(["not-started", "failed", "applied"])("keeps effect=%s separate from task completion", async (effect) => {
		const fixture = await windowFixture();
		const current = gate();
		if (!current.decision) throw new Error("fixture requires decision facts");
		current.decision.effect = effect;
		const text = renderGateCards([current], fixture.project, Date.now()).join("\n");
		expect(text).toContain(`effect=${effect}`);
		expect(text).toContain(`task-completion: ${MISSING_FIELD_SENTINEL}`);
		expect(text).not.toContain("task-completion: done");
	});

	it("does not ask for a second human answer to an applied formal decision gate", async () => {
		const fixture = await windowFixture();
		// The formal producer retains legacy status=pending. The typed decision
		// fields, parsed by the shipped reader, carry the answer and its effect.
		const current = parseGateFile(
			[
				"---",
				"id: gate-0001",
				"gate_schema: 2",
				"kind: goal-change",
				"stage:",
				`key: ${OWNER}`,
				"created_at: 2026-11-09T00:00:00Z",
				"created_by: conductor",
				"question: Adopt the prepared goal?",
				"context_refs:",
				"  - family:goal-adoption",
				"status: pending",
				"answered_at: 2026-11-09T00:00:01Z",
				"answered_by: fixture:1",
				"note:",
				"transport: answered",
				"business: approve",
				"effect: applied",
				"decision_ref: dp-gate-approve:fixture",
				"matter_ref: goal:fixture",
				"substantive_version: version-1",
				"pm_note: Adopt the prepared version",
				"model_basis: The prepared evidence supports adoption",
				"closure_kind:",
				"---",
				"",
			].join("\n"),
			"fixture/gate-0001.md",
		);
		expect(current.status).toBe("pending");
		const text = renderGateCards([current], fixture.project, Date.now()).join("\n");
		expect(text).toContain("effect=applied");
		expect(text).not.toContain("1 pending gate(s)");
		expect(text).not.toContain("/autopilot gate gate-0001 approve|reject");
		expect(text).not.toContain("stage -> closed");
	});

	it("preserves long prepared facts and source identity within the console line width", async () => {
		const fixture = await windowFixture();
		const current = gate({ path: `fixture/${"source/".repeat(30)}gate-0001.md` });
		if (!current.decision) throw new Error("fixture requires decision facts");
		current.decision.pmNote = "PM prepared note with scope and conditions. ".repeat(12);
		current.decision.modelBasis = "Selected prepared basis with material references. ".repeat(12);
		current.decision.decisionRef = `dp-gate-approve:${"d".repeat(128)}`;
		current.decision.matterRef = "m".repeat(64);
		current.decision.substantiveVersion = "v".repeat(64);
		const lines = renderGateCards([current], fixture.project, Date.now());
		for (const [label, value] of Object.entries({
			"pm-note": current.decision.pmNote,
			"model-basis": current.decision.modelBasis,
			"decision-ref": current.decision.decisionRef,
			matter: current.decision.matterRef,
			version: current.decision.substantiveVersion,
			source: current.path,
		})) {
			const prefix = `${label}: `;
			expect(
				lines
					.filter((line) => line.startsWith(prefix))
					.map((line) => line.slice(prefix.length))
					.join(""),
			).toBe(value);
		}
		expect(lines.every((line) => line.length <= 110)).toBe(true);
	});

	it("distinguishes missing open items from an explicit empty list", async () => {
		const fixture = await windowFixture();
		expect(renderGateCards([gate({ openItems: null })], fixture.project, Date.now()).join("\n")).toContain(
			`open-items: ${MISSING_FIELD_SENTINEL}`,
		);
		expect(renderGateCards([gate({ openItems: [] })], fixture.project, Date.now()).join("\n")).toContain(
			"open-items: []",
		);
	});

	it("retains the existing explicit human gate command without projecting a model-only record into it", async () => {
		const fixture = await windowFixture();
		const legacy = gate({ status: "pending", decision: undefined });
		const lines = renderGateCards([legacy], fixture.project, Date.now());
		expect(lines).toHaveLength(14);
		expect(lines.join("\n")).toContain("/autopilot gate gate-0001 approve|reject --note <text>");
		expect(renderGateCards([gate()], fixture.project, Date.now()).join("\n")).not.toContain(
			"/autopilot gate gate-0001 approve|reject",
		);
	});
});
