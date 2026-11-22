/** T04B host offer / submit — offline L1 suite.
 *
 *  - CapturingApi drives the REAL registrations by calling `tool.execute`
 *    directly (isolated runner / configReader / clock), so ask->offer->submit->
 *    store runs for real with zero network.
 *  - A createHarness + faux/provider test proves session-level registration.
 *  - The L1 host adapter (real-shaped TrustedHostContext + finite
 *    MatterBudgetV1 + granted reservation) is injected ONLY into the isolated
 *    test branch. The DEFAULT production branch registers NO adapter and every
 *    controlled write must fail closed. This suite never claims a production
 *    budget / execution is wired (that is T05/T06).
 */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	ASK_DECISION_TOOL,
	type DecideConfigReader,
	type DecisionInitiatorRole,
	registerAskDecisionTool,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import {
	registerSubmitDecisionHandoffTool,
	SUBMIT_DECISION_HANDOFF_PARAMETERS,
	SUBMIT_DECISION_HANDOFF_TOOL,
	type SubmitDecisionHostHandle,
	type SubmitOfferMetadata,
} from "../../src/extensions/agent-team-loop/pm/host-submit.ts";
import type { DecideConfigFacts } from "../../src/extensions/agent-team-loop/shared/decide-policy.ts";
import type { HostFacts } from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import type {
	LocalSelectionHostAdapter,
	TrustedHostContext,
} from "../../src/extensions/agent-team-loop/shared/local-selection-store.ts";
import { createHarness, type Harness } from "./harness.ts";

const KEY = "fixture-key";
const NOW = "2026-11-13T10:00:00.000Z";
const DEADLINE = "2026-11-13T11:00:00.000Z";
const BUDGET_REF = "budget:T04B";
const CLAIM = currentClaimId();

function material(overrides: Record<string, unknown> = {}): Record<string, unknown> {
	return {
		question: "Which option should the PM take?",
		background: {
			task_goal: "host offer continuity",
			current_state: "DP transport is off",
			tried: "no retry of the same matter",
			unknowns: "none new",
			constraints: "existing claim, role and write face only",
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
				label: "collect",
				description: "collect evidence",
				consequence: "adds a step",
				risk: "low",
				conditions: "within budget",
			},
		],
		...overrides,
	};
}
function preparation(overrides: Record<string, unknown> = {}): Record<string, unknown> {
	return {
		prepared_at: NOW,
		basis_catalog: [
			{ id: "basis", text: "Review the referenced evidence", material_refs: ["question"], applies_to: ["c1", "c2"] },
		],
		...overrides,
	};
}

interface CapTool {
	name: string;
	parameters: unknown;
	execute: (
		id: string,
		params: Record<string, unknown>,
	) => Promise<{ content: Array<{ type: string; text: string }>; details: Record<string, unknown> }>;
}
class CapPi {
	readonly tools = new Map<string, CapTool>();
	active: string[] = [];
	readonly handlers = new Map<string, Array<() => unknown>>();
	registerTool(tool: unknown): void {
		const t = tool as CapTool;
		this.tools.set(t.name, t);
	}
	on(event: string, handler: () => unknown): void {
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
}
function toolOf(pi: CapPi, name: string): CapTool {
	const t = pi.tools.get(name);
	if (t === undefined) throw new Error(`tool ${name} not registered`);
	return t;
}
function firstPayload(result: { content: Array<{ type: string; text: string }> }): Record<string, unknown> {
	return JSON.parse(result.content[0].text.split("\n")[0]) as Record<string, unknown>;
}
function offerOf(result: { details: Record<string, unknown> }): SubmitOfferMetadata | undefined {
	return result.details.submit_offer as SubmitOfferMetadata | undefined;
}

interface Control {
	offReason: "off" | "unconfigured";
	hostFacts: HostFacts;
	trusted: (ctx: TrustedHostContext) => TrustedHostContext | undefined;
}

interface Env {
	pi: CapPi;
	handle: SubmitDecisionHostHandle;
	root: string;
	agenticdoc: string;
	control: Control;
	decideCalls: number;
	cleanup: () => void;
}

function offReader(control: Control): DecideConfigReader {
	return () =>
		({
			transport: control.offReason,
			dpDisabled: false,
			signoffDisabled: false,
			mode: "auto",
			configRefs: [".mw/decide-points.json", ".mw/decide.json"],
		}) as DecideConfigFacts;
}

function makeEnv(
	opts: {
		withAdapter?: boolean;
		indexContent?: string;
		initiatorRole?: DecisionInitiatorRole;
		taskPath?: string;
	} = {},
): Env {
	const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "t04b-submit-"));
	const root = tmp;
	const agenticdoc = path.join(tmp, ".agenticdoc");
	fs.mkdirSync(agenticdoc, { recursive: true });
	fs.mkdirSync(path.join(tmp, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(tmp, ".mw", "decide.json"), `${JSON.stringify({ enabled: false })}\n`, "utf8");
	const index =
		opts.indexContent ??
		`# Index Parallel\n| Key | Status | Phase | Claim-Id | Deps | Desc | Updated |\n| --- | --- | --- | --- | --- | --- | --- |\n| ${KEY} | active | EXECUTE | ${CLAIM} |  |  | 2026-11-12T12:00:00Z |\n`;
	fs.writeFileSync(path.join(agenticdoc, "_index.parallel"), index, "utf8");

	const control: Control = {
		offReason: "off",
		hostFacts: { binding: { role: "pm", binding_version: "v-fixture", observed_at: NOW } },
		trusted: (ctx) => ctx,
	};
	const pi = new CapPi();
	let handleRef: SubmitDecisionHostHandle | undefined;
	const adapter: LocalSelectionHostAdapter = {
		readTrustedContext: async (req) => {
			const exp = handleRef?.hostExpectedFor(req.ref);
			if (exp === undefined) return undefined;
			const ctx: TrustedHostContext = {
				self_claim_id: CLAIM,
				binding_version: "v3",
				role: "pm",
				observed_at: NOW,
				expected: { ...exp, budget_ref: BUDGET_REF },
				budget: {
					schema_version: 1,
					budget_ref: BUDGET_REF,
					matter_ref: exp.matter_ref,
					deadline: DEADLINE,
					max_steps: 3,
					no_progress_limit: 2,
					remaining_cost: 5,
					steps_consumed: 1,
					cost_consumed: 1,
					no_progress_count: 0,
					source_refs: ["tasks/T04B:timeout=40", "run.json:remaining"],
				},
				budget_preflight: {
					granted: true,
					reserved_steps: 1,
					reserved_cost: 1,
					remaining_after_steps: 2,
					remaining_after_cost: 4,
					reason: "granted",
				},
			};
			return control.trusted(ctx);
		},
	};
	const decideCalls = { count: 0 };
	const submitConfig: Parameters<typeof registerSubmitDecisionHandoffTool>[1] = {
		projectDir: root,
		agenticdocRootOverride: agenticdoc,
		clock: () => Date.parse(NOW),
		...(opts.withAdapter === false ? {} : { hostAdapter: adapter }),
	};
	const handle = registerSubmitDecisionHandoffTool(pi as unknown as ExtensionAPI, submitConfig);
	handleRef = handle;
	const runner = async () => {
		decideCalls.count += 1;
		return { status: 0, stdout: "", stderr: "", timedOut: false };
	};
	registerAskDecisionTool(pi as unknown as ExtensionAPI, {
		projectDir: root,
		initiatorRole: opts.initiatorRole ?? "pm",
		// Force the PM structural branch even when a real worker env is present
		// in the test process (PI_WORKER_TASK is a worker identity, not ours).
		taskPath: opts.taskPath ?? "",
		submitHandle: handle,
		configReader: offReader(control),
		runner,
		hostFacts: control.hostFacts,
	});
	return {
		pi,
		handle,
		root,
		agenticdoc,
		control,
		get decideCalls() {
			return decideCalls.count;
		},
		cleanup: () => fs.rmSync(tmp, { recursive: true, force: true }),
	};
}

const envs: Array<{ cleanup: () => void }> = [];
const harnesses: Harness[] = [];
function track(env: Env): Env {
	envs.push(env);
	return env;
}
afterEach(() => {
	for (const env of envs.splice(0)) env.cleanup();
	for (const h of harnesses.splice(0)) h.cleanup();
});

function askParams(overrides: Record<string, unknown> = {}): Record<string, unknown> {
	return { dp: "dp-auto", trigger: "t04b#c1", material: material(), preparation: preparation(), ...overrides };
}
function submitParams(offer: SubmitOfferMetadata, overrides: Record<string, unknown> = {}): Record<string, unknown> {
	return { offer_id: offer.offer_id, choice: "c1", basis_id: "basis", ...overrides };
}

async function ask(env: Env, overrides: Record<string, unknown> = {}) {
	return toolOf(env.pi, ASK_DECISION_TOOL).execute("ask-1", askParams(overrides));
}
async function submit(env: Env, params: Record<string, unknown>, id = "submit-1") {
	return toolOf(env.pi, SUBMIT_DECISION_HANDOFF_TOOL).execute(id, params);
}

describe("T04B strict submit schema", () => {
	it("exposes exactly {offer_id,choice,basis_id}, additionalProperties=false", () => {
		const env = track(makeEnv());
		const schema = toolOf(env.pi, SUBMIT_DECISION_HANDOFF_TOOL).parameters as {
			properties: Record<string, unknown>;
			required: string[];
			additionalProperties: boolean;
		};
		expect(Object.keys(schema.properties).sort()).toEqual(["basis_id", "choice", "offer_id"]);
		expect(schema.additionalProperties).toBe(false);
		expect(SUBMIT_DECISION_HANDOFF_PARAMETERS).toBeDefined();
	});

	it("rejects model-supplied host/role/source/key/budget/parent/proof params", async () => {
		const env = track(makeEnv());
		const a = await ask(env);
		const offer = offerOf(a)!;
		const r = await submit(
			env,
			submitParams(offer, {
				role: "pm",
				source: "pm",
				key: KEY,
				budget: "x",
				decision_id: "dp-auto:1",
				parent: "p",
				proof: true,
			}),
		);
		expect(firstPayload(r).status).toBe("refused");
		expect(firstPayload(r).reason).toBe("invalid-parameters");
	});
});

describe("T04B disabled/off zero-POST + valid independent offer", () => {
	it("disabled path sends ZERO DP POST yet prepares a legal offer; first-line payload unchanged", async () => {
		const env = track(makeEnv());
		const a = await ask(env);
		expect(env.decideCalls).toBe(0);
		expect(firstPayload(a).available).toBe(false);
		expect(firstPayload(a).unavailable).toBe("disabled");
		const offer = offerOf(a);
		expect(offer?.submittable).toBe(true);
		expect(typeof offer?.offer_id).toBe("string");
		expect(typeof offer?.local_ref).toBe("string");
		expect(offer?.submit_tool).toBe(SUBMIT_DECISION_HANDOFF_TOOL);
		// first line is the frozen legacy payload; offer is a separate line/field.
		expect(a.content[0].text.split("\n")[0]).not.toContain("submit_offer");
		expect(a.content[0].text).toContain('"submit_offer"');
		expect(a.details.decision_feedback).toBeDefined();
	});

	it("incomplete material yields fillable gaps, never a fabricated offer", async () => {
		const env = track(makeEnv());
		const a = await ask(env, { material: { question: "only one field" } });
		const offer = offerOf(a);
		expect(offer?.submittable).toBe(false);
		expect((offer?.gaps ?? []).length).toBeGreaterThan(0);
	});
});

describe("T04B ask identity refusal → no submittable offer", () => {
	it("no active self claim → no offer", async () => {
		const env = track(makeEnv({ indexContent: "# empty\n" }));
		const a = await ask(env);
		expect(firstPayload(a).claim_diagnosis).toBeDefined();
		expect(offerOf(a)).toBeUndefined();
	});
	it("foreign owner → no offer", async () => {
		const idx = `# Index Parallel\n| Key | Status | Phase | Claim-Id | Deps | Desc | Updated |\n| --- | --- | --- | --- | --- | --- | --- |\n| ${KEY} | active | EXECUTE | SOMEONE-ELSE:1 |  |  | now |\n`;
		const env = track(makeEnv({ indexContent: idx }));
		const a = await ask(env);
		expect(offerOf(a)).toBeUndefined();
	});
	it("multiple active self claims → no offer", async () => {
		const idx = `# Index Parallel\n| Key | Status | Phase | Claim-Id | Deps | Desc | Updated |\n| --- | --- | --- | --- | --- | --- | --- |\n| ${KEY} | active | EXECUTE | ${CLAIM} |  |  | now |\n| ${KEY}-b | active | EXECUTE | ${CLAIM} |  |  | now |\n`;
		const env = track(makeEnv({ indexContent: idx }));
		const a = await ask(env);
		expect(offerOf(a)).toBeUndefined();
	});
	it("worker role on a PM-only dp → offer refused with role gap (direct host junction)", () => {
		const env = track(makeEnv());
		const r = env.handle.prepareOffer({
			dp: "dp-auto",
			identity: { source: "worker-local", key: KEY, role: "coding", taskKey: "t", runId: "r" },
			material: material(),
			preparation: preparation() as never,
			matterRef: "m",
			feedbackEffectUnknown: false,
			revalidate: () => ({
				configSignature: "c",
				hostSignature: "h",
				identity: { source: "worker-local", key: KEY, role: "coding" },
				trustedStop: false,
			}),
		});
		expect(r.prepared).toBe(false);
		expect(r.metadata.gaps).toContain("identity.role-forbidden");
	});
});

describe("T04B successful planned selection through the single frozen store", () => {
	it("ask->offer->submit commits ONLY a local-selection, binds real toolCallId, business_completed=false", async () => {
		const env = track(makeEnv());
		const a = await ask(env);
		const offer = offerOf(a)!;
		const r = await submit(env, submitParams(offer), "commit-call-7");
		expect(firstPayload(r).status).toBe("planned");
		expect(firstPayload(r).business_completed).toBe(false);
		expect(firstPayload(r).kind).toBe("local-selection");
		expect(firstPayload(r).selection_written).toBe(true);
		// not a DP id, no parent, no decision_id anywhere.
		expect(firstPayload(r).decision_id).toBeUndefined();
		const committed = env.handle.readCommittedSelection("commit-call-7");
		expect(committed).toBeDefined();
		expect(committed!.record.kind).toBe("local-selection");
		expect(committed!.record.action_state).toBe("planned");
		expect(committed!.record.business_completed).toBe(false);
		expect(committed!.record.parent_decision_ref).toBeUndefined();
		expect(env.handle.readCommittedSelection("unknown-call")).toBeUndefined();
		// no execution / receipt / sign files; no DP receipt increment.
		const files = fs.existsSync(path.join(env.agenticdoc, KEY, "evidence", "decision-handoffs"))
			? fs.readdirSync(path.join(env.agenticdoc, KEY, "evidence", "decision-handoffs"))
			: [];
		expect(files.some((f) => f.includes(".execution."))).toBe(false);
		expect(env.decideCalls).toBe(0);
		const trace = fs.existsSync(path.join(env.root, "trace.log"))
			? fs.readFileSync(path.join(env.root, "trace.log"), "utf8")
			: "";
		expect(trace).not.toContain("[DECISION_RECEIPT]");
	});

	it("a second identical submit is a store duplicate, never a re-execution", async () => {
		const env = track(makeEnv());
		const offer = offerOf(await ask(env))!;
		const first = await submit(env, submitParams(offer), "call-a");
		const second = await submit(env, submitParams(offer), "call-b");
		expect(firstPayload(first).code).toBe("written");
		expect(firstPayload(second).status).toBe("planned");
		expect(firstPayload(second).code).toBe("duplicate");
		expect(env.handle.readCommittedSelection("call-b")!.code).toBe("duplicate");
	});

	it("a different choice for the same offer → store conflict refusal", async () => {
		const env = track(makeEnv());
		const offer = offerOf(await ask(env))!;
		await submit(env, submitParams(offer), "call-a");
		const conflict = await submit(env, submitParams(offer, { choice: "c2" }), "call-b");
		expect(firstPayload(conflict).status).toBe("refused");
		expect(firstPayload(conflict).code).toBe("conflict");
		expect(env.handle.readCommittedSelection("call-b")).toBeUndefined();
	});

	it("same matter re-prepared across a replay reuses identity; unknown offer never binds", async () => {
		const env = track(makeEnv());
		const a1 = await ask(env);
		const a2 = await ask(env); // matter_suppressed replay
		expect(offerOf(a1)!.offer_id).toBe(offerOf(a2)!.offer_id);
		expect(firstPayload(a2).matter_suppressed).toBe(true);
		const unknown = await submit(env, { offer_id: "offer:forged", choice: "c1", basis_id: "basis" });
		expect(firstPayload(unknown).reason).toBe("unknown-or-unbound-offer");
	});
});

describe("T04B drift / invalid choice / unknown effect fail closed", () => {
	it("config change between prepare and submit → config-drift refusal", async () => {
		const env = track(makeEnv());
		const offer = offerOf(await ask(env))!;
		env.control.offReason = "unconfigured";
		const r = await submit(env, submitParams(offer));
		expect(firstPayload(r).status).toBe("refused");
		expect(firstPayload(r).gaps as string[]).toContain("config-drift");
	});
	it("typed stop / budget host-fact change → host-facts/stop drift refusal", async () => {
		const env = track(makeEnv());
		const offer = offerOf(await ask(env))!;
		env.control.hostFacts.stop_signals = [{ signal_ref: "s1", kind: "user-stop" }];
		const r = await submit(env, submitParams(offer));
		expect(firstPayload(r).status).toBe("refused");
	});
	it("choice/basis not in current candidates/catalog → choice-or-basis-invalid", async () => {
		const env = track(makeEnv());
		const offer = offerOf(await ask(env))!;
		const r = await submit(env, submitParams(offer, { choice: "not-a-candidate" }));
		expect(firstPayload(r).status).toBe("refused");
		expect((firstPayload(r).gaps as string[]).some((g) => g.includes("choice-or-basis-invalid"))).toBe(true);
	});
	it("unknown-effect offer cannot be committed (no blind re-execution)", async () => {
		const env = track(makeEnv());
		const prepared = env.handle.prepareOffer({
			dp: "dp-auto",
			identity: { source: "pm", key: KEY, role: "pm", claimId: CLAIM },
			material: material(),
			preparation: preparation() as never,
			matterRef: "unknown-effect-matter",
			parentDecisionId: undefined,
			feedbackEffectUnknown: true,
			revalidate: () => ({
				configSignature: "c",
				hostSignature: "h",
				identity: { source: "pm", key: KEY, role: "pm", claimId: CLAIM },
				trustedStop: false,
			}),
		});
		expect(prepared.prepared).toBe(true); // unknown feedback CAN still prepare
		const r = await submit(env, submitParams(prepared.metadata), "unknown-effect-call");
		expect(firstPayload(r).status).toBe("refused");
		expect(firstPayload(r).reason).toBe("effect-unknown-no-replay");
		expect(env.handle.readCommittedSelection("unknown-effect-call")).toBeUndefined();
	});
});

describe("T04B default production fail-closed (no L1 grant in production branch)", () => {
	it("no host adapter → trusted-context-missing; no record written", async () => {
		const env = track(makeEnv({ withAdapter: false }));
		const offer = offerOf(await ask(env))!;
		const r = await submit(env, submitParams(offer));
		expect(firstPayload(r).status).toBe("refused");
		expect(firstPayload(r).reason).toBe("store-trusted-context-missing");
		expect(env.handle.readCommittedSelection("submit-1")).toBeUndefined();
	});
	it("adapter present but budget/preflight missing → store refusal with fillable gap", async () => {
		const env = track(makeEnv());
		const offer = offerOf(await ask(env))!;
		env.control.trusted = (ctx) => ({ ...ctx, budget_preflight: undefined as never });
		const r = await submit(env, submitParams(offer));
		expect(firstPayload(r).status).toBe("refused");
		expect(firstPayload(r).reason).toBe("store-budget-preflight-missing");
	});
	it("adapter returns no trusted context → store refusal", async () => {
		const env = track(makeEnv());
		const offer = offerOf(await ask(env))!;
		env.control.trusted = () => undefined;
		const r = await submit(env, submitParams(offer));
		expect(firstPayload(r).status).toBe("refused");
	});
});

describe("T04B real session registration (harness + faux provider)", () => {
	it("registers ask + submit under a session and an offline ask yields submit_offer", async () => {
		const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "t04b-harness-"));
		const agenticdoc = path.join(tmp, ".agenticdoc");
		fs.mkdirSync(agenticdoc, { recursive: true });
		fs.mkdirSync(path.join(tmp, ".mw"), { recursive: true });
		fs.writeFileSync(path.join(tmp, ".mw", "decide.json"), `${JSON.stringify({ enabled: false })}\n`, "utf8");
		fs.writeFileSync(
			path.join(agenticdoc, "_index.parallel"),
			`# Index Parallel\n| Key | Status | Phase | Claim-Id | Deps | Desc | Updated |\n| --- | --- | --- | --- | --- | --- | --- |\n| ${KEY} | active | EXECUTE | ${CLAIM} |  |  | now |\n`,
			"utf8",
		);
		const off: DecideConfigReader = () =>
			({
				transport: "off",
				dpDisabled: false,
				signoffDisabled: false,
				mode: "auto",
				configRefs: [],
			}) as DecideConfigFacts;
		const harness = await createHarness({
			extensionFactories: [
				(pi) => {
					const handle = registerSubmitDecisionHandoffTool(pi, {
						projectDir: tmp,
						agenticdocRootOverride: agenticdoc,
						clock: () => Date.parse(NOW),
					});
					registerAskDecisionTool(pi, {
						projectDir: tmp,
						initiatorRole: "pm",
						taskPath: "",
						submitHandle: handle,
						configReader: off,
						runner: async () => ({ status: 0, stdout: "", stderr: "", timedOut: false }),
					});
				},
			],
		});
		harnesses.push(harness);
		harness.setResponses([
			fauxAssistantMessage([fauxToolCall(ASK_DECISION_TOOL, askParams())], { stopReason: "toolUse" }),
			fauxAssistantMessage("done"),
		]);
		await harness.session.prompt("Continue.");
		const toolResults = harness.session.messages.filter((m) => m.role === "toolResult");
		const body = JSON.stringify(toolResults);
		expect(body).toContain("submit_offer");
		fs.rmSync(tmp, { recursive: true, force: true });
	});
});

// ── T04B-R1 regressions: F1 (detached trusted read-back) / F2 (sticky unknown) ──

function selectionFiles(env: Env): string[] {
	const dir = path.join(env.agenticdoc, KEY, "evidence", "decision-handoffs");
	if (!fs.existsSync(dir)) return [];
	return fs
		.readdirSync(dir)
		.filter((f) => f.endsWith(".json") && !f.endsWith(".execution.json") && !f.endsWith(".disposition.json"));
}

/** Direct host handle prepare (mirrors the existing unknown-effect test input),
 *  with feedbackEffectUnknown toggled to drive same-matter re-prepares. */
function directPrepare(env: Env, feedbackEffectUnknown: boolean) {
	const identity = { source: "pm" as const, key: KEY, role: "pm" as const, claimId: CLAIM };
	return env.handle.prepareOffer({
		dp: "dp-auto",
		identity,
		material: material(),
		preparation: preparation() as never,
		matterRef: "same-host-matter",
		parentDecisionId: undefined,
		feedbackEffectUnknown,
		revalidate: () => ({ configSignature: "c", hostSignature: "h", identity, trustedStop: false }),
	});
}

describe("T04B-R1 F1/F2 host boundary regressions", () => {
	it("F1: mutating returned choice / deep nested record cannot change a later trusted read; details carry no authorization", async () => {
		const env = track(makeEnv());
		const offer = offerOf(await ask(env))!;
		const submitted = await submit(env, submitParams(offer), "real-call");
		expect(firstPayload(submitted).status).toBe("planned");

		// No trusted record material is reconstructable from tool_result details.
		const detailsText = JSON.stringify(submitted.details);
		expect(detailsText).not.toContain("host_binding");
		expect(detailsText).not.toContain("action_state");
		expect(detailsText).not.toContain("selected_action");
		expect(submitted.details.record).toBeUndefined();

		const obtained = env.handle.readCommittedSelection("real-call")!;
		const originalChoice = obtained.choice;
		const originalSelectedAction = obtained.record.selected_action;
		const originalHostRole = obtained.record.host_binding.role;

		// Tamper with top-level metadata AND deep nested record fields. A
		// deep-frozen implementation may throw on write; tolerate that, but the
		// proof below must still hold: the next trusted read stays the original.
		try {
			const loose = obtained as unknown as {
				choice: string;
				record: { selected_action: string; action_state: string; host_binding: { role: string } };
			};
			loose.choice = "forged-choice";
			loose.record.selected_action = "forged-choice";
			loose.record.action_state = "done";
			loose.record.host_binding.role = "forged-role";
		} catch {
			// a deep-frozen copy legitimately rejects writes
		}

		const again = env.handle.readCommittedSelection("real-call")!;
		expect(again.choice).toBe("c1");
		expect(again.choice).toBe(originalChoice);
		expect(again.record.selected_action).toBe("c1");
		expect(again.record.selected_action).toBe(originalSelectedAction);
		expect(again.record.action_state).toBe("planned");
		expect(again.record.host_binding.role).toBe(originalHostRole);
		expect(again.record.host_binding.role).not.toBe("forged-role");
		// each read is an independent detached copy (no shared nested refs)
		expect(again).not.toBe(obtained);
		expect(again.record).not.toBe(obtained.record);
		expect(again.record.host_binding).not.toBe(obtained.record.host_binding);
	});

	it("F2: false -> true (same matter) -> submit refused; same id/local_ref; no record or selection write", async () => {
		const env = track(makeEnv());
		const initial = directPrepare(env, false);
		expect(initial.prepared).toBe(true);
		const uncertain = directPrepare(env, true);
		expect(uncertain.prepared).toBe(true);
		// the unknown observation buys NO new offer id / local_ref / budget
		expect(uncertain.metadata.offer_id).toBe(initial.metadata.offer_id);
		expect(uncertain.metadata.local_ref).toBe(initial.metadata.local_ref);
		const r = await submit(env, submitParams(uncertain.metadata), "uncertain-call");
		expect(firstPayload(r).status).toBe("refused");
		expect(firstPayload(r).reason).toBe("effect-unknown-no-replay");
		expect(env.handle.readCommittedSelection("uncertain-call")).toBeUndefined();
		expect(selectionFiles(env).length).toBe(0);
	});

	it("F2: false -> true -> false self-report still refused; old false offer cannot be revived", async () => {
		const env = track(makeEnv());
		const initial = directPrepare(env, false);
		directPrepare(env, true);
		const cleared = directPrepare(env, false);
		expect(cleared.prepared).toBe(true);
		expect(cleared.metadata.offer_id).toBe(initial.metadata.offer_id);
		const r = await submit(env, submitParams(cleared.metadata), "cleared-call");
		expect(firstPayload(r).status).toBe("refused");
		expect(firstPayload(r).reason).toBe("effect-unknown-no-replay");
		expect(env.handle.readCommittedSelection("cleared-call")).toBeUndefined();
		// the original false offer is now poisoned too, no new id bought
		const r2 = await submit(env, submitParams(initial.metadata), "initial-call");
		expect(firstPayload(r2).status).toBe("refused");
		expect(firstPayload(r2).reason).toBe("effect-unknown-no-replay");
		expect(env.handle.readCommittedSelection("initial-call")).toBeUndefined();
		expect(selectionFiles(env).length).toBe(0);
	});

	it("F2 positive control: normal same-matter reuse stays commit-capable; duplicate stays a positive control", async () => {
		const env = track(makeEnv());
		const a1 = await ask(env);
		const a2 = await ask(env);
		expect(offerOf(a2)!.offer_id).toBe(offerOf(a1)!.offer_id);
		const first = await submit(env, submitParams(offerOf(a1)!), "pos-a");
		const second = await submit(env, submitParams(offerOf(a2)!), "pos-b");
		expect(firstPayload(first).status).toBe("planned");
		expect(firstPayload(first).code).toBe("written");
		expect(firstPayload(second).status).toBe("planned");
		expect(firstPayload(second).code).toBe("duplicate");
		expect(env.handle.readCommittedSelection("pos-a")!.code).toBe("written");
		expect(env.handle.readCommittedSelection("pos-b")!.code).toBe("duplicate");
		expect(selectionFiles(env).length).toBeGreaterThan(0);
	});

	it("R10 replay negative: duplicate is ONE planned write, never an execution/disposition or a second selection; different choice is a conflict; forged ref unresolved", async () => {
		const env = track(makeEnv());
		const offer = offerOf(await ask(env))!;
		const first = await submit(env, submitParams(offer), "a");
		const second = await submit(env, submitParams(offer), "b");
		const third = await submit(env, submitParams(offer, { choice: "c2" }), "c");
		expect(firstPayload(first).code).toBe("written");
		expect(firstPayload(second).status).toBe("planned");
		expect(firstPayload(second).code).toBe("duplicate");
		expect(firstPayload(third).status).toBe("refused");
		expect(firstPayload(third).code).toBe("conflict");
		// The frozen store classified, and the replay/conflict produced NO second
		// selection write and NO execution / disposition record.
		expect(selectionFiles(env).length).toBe(1);
		const dir = path.join(env.agenticdoc, KEY, "evidence", "decision-handoffs");
		const all = fs.existsSync(dir) ? fs.readdirSync(dir) : [];
		expect(all.some((f) => f.endsWith(".execution.json"))).toBe(false);
		expect(all.some((f) => f.endsWith(".disposition.json"))).toBe(false);
		expect(env.handle.readCommittedSelection("b")!.code).toBe("duplicate");
		expect(env.handle.readCommittedSelection("c")).toBeUndefined();
		// Wrong-ref / wrong-source negative: only the authentic offer local_ref resolves.
		expect(env.handle.hostExpectedFor("disposition:forged")).toBeUndefined();
		expect(env.handle.hostExpectedFor(String(offer.local_ref))).toBeDefined();
	});
});
