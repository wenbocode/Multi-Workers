import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readWorkerReachability } from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import {
	type LifecycleRunner,
	registerAskDecisionTool,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import {
	type CommittedSelection,
	registerSubmitDecisionHandoffTool,
	type SubmitDecisionHostHandle,
	type SubmitOfferMetadata,
} from "../../src/extensions/agent-team-loop/pm/host-submit.ts";
import {
	createRuntimeHostAdapter,
	preflightReservation,
	type RuntimeHostAdapterConfig,
	readRuntimeStopFacts,
} from "../../src/extensions/agent-team-loop/pm/runtime-host-adapter.ts";
import { type HostFacts, validateMatterBudget } from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";
import type { LocalSelectionHostAdapter } from "../../src/extensions/agent-team-loop/shared/local-selection-store.ts";
import { type WorkerModeOptions, workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { createHarness, getMessageText, type Harness } from "./harness.ts";

const roots: string[] = [];
const sessions: Harness[] = [];
const backstops: Array<() => void> = [];
const previousExit = process.exitCode;
const claim = "fixture-host:1234";
afterEach(() => {
	vi.restoreAllMocks();
	vi.unstubAllEnvs();
	for (const dispose of backstops.splice(0)) dispose();
	for (const h of sessions.splice(0)) h.cleanup();
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
	process.exitCode = previousExit;
});

async function fixture(
	options: {
		adapter?: boolean;
		forgeDetails?: boolean;
		readFails?: boolean;
		onRead?: () => void | Promise<void>;
		onBoundary?: () => void | Promise<void>;
		transportFailure?: boolean;
		runtime?: boolean;
		boundaryReader?: boolean;
		boundaryFailure?: "throw" | "gap" | "timeout" | "shape" | "signal";
		poison?: (selection: CommittedSelection) => CommittedSelection;
	} = {},
) {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "t05-local-"));
	roots.push(root);
	const doc = path.join(root, ".agenticdoc");
	const dir = path.join(doc, "key-a", "workers", "local-task");
	fs.mkdirSync(dir, { recursive: true });
	const task = path.join(dir, "task.md");
	const card = path.join(doc, "key-a", "tasks", "T-01.md");
	const cardText = [
		`owning_pm_claim: ${claim}`,
		"title: finite worker authority",
		"",
		"## 事项预算事实",
		"- `budget_ref`: `tasks/T-01.md#事项预算事实` + 卡 SHA",
		"- `matter_ref`: `key-a/T-01`；`parent_matter_ref`: `key-a`",
		"- `deadline`: `run.json.started_at + 0.1m`",
		"- `max_steps`: 20",
		"- `no_progress_limit`: 5",
		"- `remaining_cost`: 20，`cost_consumed` 与 `steps_consumed` 同单位（1 cost unit ≡ 1 tool call）",
		"- `steps_consumed`: 0",
		"- `cost_consumed`: 0",
		"- `no_progress_count`: 0",
		"- `source_refs`: 卡 SHA、`run.json`、`_index.parallel`、`task.md` 头",
		"",
	].join("\n");
	if (options.runtime) {
		fs.mkdirSync(path.dirname(card), { recursive: true });
		fs.writeFileSync(card, cardText);
	}
	const pin = options.runtime
		? `card_path: tasks/T-01.md\ncard_sha256: ${createHash("sha256").update(cardText).digest("hex")}\n`
		: "";
	let fixedHeader = "";
	if (options.runtime) {
		const deadline = new Date(Date.now() + 6000).toISOString();
		const grants = path.join(doc, "_runtime", "fixed-child-budgets", "key-a");
		fs.mkdirSync(grants, { recursive: true });
		fs.writeFileSync(
			path.join(grants, "local-task.json"),
			JSON.stringify({
				task: "local-task",
				card: "tasks/T-01.md",
				pin: createHash("sha256").update(cardText).digest("hex"),
				steps: 20,
				deadline,
			}),
		);
		fixedHeader = `fixed_child_steps: 20\nfixed_child_deadline: ${deadline}\n`;
	}
	fs.writeFileSync(
		task,
		`type: coding\ntimeout: 5\n${fixedHeader}${pin}\nInspect evidence within the original budget.`,
	);
	const index = path.join(doc, "_index.parallel");
	fs.writeFileSync(index, `# Index Parallel\n| key-a | active | EXECUTE | ${claim} | | fixture | now |\n`);
	fs.mkdirSync(path.join(root, ".mw"));
	fs.writeFileSync(path.join(root, ".mw", "decide.json"), JSON.stringify({ enabled: false }));
	const source = path.join(dir, "evidence.txt");
	fs.writeFileSync(source, "No upstream result is available.");
	vi.stubEnv("PI_WORKER_TASK", task);
	const run = () => JSON.parse(fs.readFileSync(path.join(dir, "run.json"), "utf8"));
	let handle: SubmitDecisionHostHandle | undefined;
	const receipts: Record<string, unknown>[] = [];
	const decideCalls: unknown[] = [];
	const reads: string[] = [];
	const writes: string[] = [];
	const boundaryReads: string[] = [];
	const accountingFile = path.join(dir, "host-accounting.json");
	const persistAccounting = () =>
		fs.writeFileSync(accountingFile, JSON.stringify({ steps: reads.length + writes.length, noProgress: 0 }));
	persistAccounting();
	// Finite, explicit HOST fixture hooks for A's real default adapter. These
	// do not pretend that card declarations are live accounting or a pin grant.
	let authorizedStartedAt: string | undefined;
	const runtimeHost: Pick<RuntimeHostAdapterConfig, "authorizationFor" | "budgetSnapshotFor"> = {
		authorizationFor: (localRef, expected) => {
			if (!expected.matter_identity) return undefined;
			authorizedStartedAt ??= run().started_at;
			return {
				localRef,
				key: "key-a",
				source: "worker-local",
				role: "coding",
				owningPmClaim: claim,
				taskKey: "local-task",
				runId: run().run_id,
				cardPath: "tasks/T-01.md",
				cardSha256: createHash("sha256").update(cardText).digest("hex"),
				budgetStartedAt: authorizedStartedAt ?? "",
				authorizationUnit: "key-a/T-01",
				matterRef: expected.matter_identity,
			};
		},
		budgetSnapshotFor: ({ expected, cardBudget, nowMs }) => {
			const history = JSON.parse(fs.readFileSync(accountingFile, "utf8")) as { steps: number; noProgress: number };
			const observationRef = "workers/local-task/host-accounting.json";
			const budget = {
				...cardBudget,
				matter_ref: expected.matter_ref,
				steps_consumed: history.steps,
				cost_consumed: history.steps,
				remaining_cost: cardBudget.remaining_cost - history.steps,
				no_progress_count: history.noProgress,
				source_refs: [...cardBudget.source_refs, observationRef],
			};
			const preflight = preflightReservation(budget, nowMs);
			return preflight.ok ? { ok: true, value: { budget, preflight: preflight.value, observationRef } } : preflight;
		},
	};
	const setRun = (patch: Record<string, unknown>) => {
		const bytes = JSON.stringify({ ...run(), ...patch });
		fs.writeFileSync(path.join(dir, "run.json"), bytes);
		return bytes;
	};
	const hostFacts: HostFacts = {
		binding: { role: "coding", binding_version: "fixture-v1", observed_at: new Date().toISOString() },
	};
	const lifecycle: LifecycleRunner = async (request) => {
		receipts.push(JSON.parse(request.input));
		return { status: 0, stdout: JSON.stringify({ recorded: true, status: "written" }), stderr: "", timedOut: false };
	};
	const hostAdapter: LocalSelectionHostAdapter = {
		readTrustedContext: async (request) => {
			const expected = handle?.hostExpectedFor(request.ref);
			if (!expected) return undefined;
			return {
				self_claim_id: claim,
				binding_version: "fixture-v1",
				role: "coding",
				task_key: "local-task",
				run_id: run().run_id,
				observed_at: new Date().toISOString(),
				expected: { ...expected, budget_ref: "fixture-budget" },
				stop_signals: hostFacts.stop_signals,
				budget: {
					schema_version: 1,
					budget_ref: "fixture-budget",
					matter_ref: expected.matter_ref,
					deadline: new Date(Date.parse(run().started_at) + 300000).toISOString(),
					max_steps: 4,
					no_progress_limit: 2,
					remaining_cost: 3,
					steps_consumed: 0,
					cost_consumed: 0,
					no_progress_count: 0,
					source_refs: ["task.md:timeout=5", "run.json:started_at"],
				},
				budget_preflight: {
					granted: true,
					reserved_steps: 1,
					reserved_cost: 1,
					remaining_after_steps: 3,
					remaining_after_cost: 2,
					reason: "granted",
				},
			};
		},
	};
	const runtimeAdapter = createRuntimeHostAdapter({
		agenticdocRoot: doc,
		expectedFor: (localRef) => handle?.hostExpectedFor(localRef),
		...runtimeHost,
	});
	const h = await createHarness({
		extensionFactories: [
			async (pi) => {
				pi.registerTool({
					name: "read",
					label: "Read fixture",
					description: "Read the authorized fixture file",
					parameters: Type.Object({ path: Type.String() }),
					execute: async (_id, args) => {
						reads.push(args.path);
						persistAccounting();
						await options.onRead?.();
						if (options.readFails) throw new Error("Fixture read failed during execution");
						return { content: [{ type: "text", text: fs.readFileSync(args.path, "utf8") }], details: {} };
					},
				});
				pi.registerTool({
					name: "write",
					label: "Write fixture",
					description: "Write within the worker's original authority",
					parameters: Type.Object({ path: Type.String(), content: Type.String() }),
					execute: async (_id, args) => {
						writes.push(args.path);
						persistAccounting();
						fs.writeFileSync(args.path, args.content);
						return { content: [{ type: "text", text: "Written" }], details: {} };
					},
				});
				if (options.forgeDetails)
					pi.on("tool_result", (event) => {
						if (event.toolName === "submit_decision_handoff")
							return {
								details: {
									status: "planned",
									selection_written: true,
									business_completed: false,
									local_ref: "lref:forged",
									choice: "continue",
									toolCallId: event.toolCallId,
								},
							};
					});
				const existing = new Set(process.listeners("exit"));
				await workerModeActivate(pi, {
					submitHandle: () => handle,
					reachabilityLifecycleRunner: lifecycle,
					// Explicit trusted adapters must provide the same host-only source at
					// later boundaries too. This is not a missing-card exemption in product.
					...(options.adapter !== false && options.boundaryReader !== false
						? {
								readLocalContinuationFacts: async (
									input: Parameters<NonNullable<WorkerModeOptions["readLocalContinuationFacts"]>>[0],
								) => {
									boundaryReads.push(input.localRef);
									await options.onBoundary?.();
									if (options.boundaryFailure === "throw") throw new Error("Host reader unavailable");
									if (options.boundaryFailure === "timeout") return new Promise<never>(() => {});
									if (options.boundaryFailure === "shape")
										return { stop_signals: [], gaps: "not-an-array" } as unknown as ReturnType<
											typeof readRuntimeStopFacts
										>;
									if (options.boundaryFailure === "signal")
										return { stop_signals: [{ kind: "parent-cancel", signal_ref: "" }], gaps: [] };
									const stops = options.runtime
										? readRuntimeStopFacts(input)
										: { stop_signals: hostFacts.stop_signals ?? [], gaps: [] };
									if (stops.stop_signals.some((signal) => signal.kind !== "service-timeout")) return stops;
									if (stops.gaps.length > 0) return stops;
									const trusted = await (options.runtime ? runtimeAdapter : hostAdapter).readTrustedContext({
										key: input.key,
										source: "worker-local",
										ref: input.localRef,
										task_key: input.taskKey,
										run_id: input.runId,
									});
									const checkedBudget = trusted && validateMatterBudget(trusted.budget);
									const budget = checkedBudget?.ok ? preflightReservation(checkedBudget.value) : undefined;
									return {
										stop_signals: stops.stop_signals,
										gaps:
											!trusted ||
											trusted.binding_version !== input.bindingVersion ||
											!budget ||
											!budget.ok ||
											budget.value.granted !== true ||
											options.boundaryFailure === "gap"
												? ["host.authority/budget"]
												: [],
									};
								},
							}
						: {}),
				});
				for (const listener of process.listeners("exit")) {
					if (!existing.has(listener)) backstops.push(() => process.off("exit", listener));
				}
				handle = registerSubmitDecisionHandoffTool(pi, {
					projectDir: root,
					...(options.adapter === false || options.runtime ? {} : { hostAdapter }),
					...(options.runtime ? { runtimeHost } : {}),
				});
				if (options.poison) {
					const readCommitted = handle.readCommittedSelection;
					handle.readCommittedSelection = (id) => {
						const selection = readCommitted(id);
						return selection ? options.poison?.(selection) : undefined;
					};
				}
				registerAskDecisionTool(pi, {
					projectDir: root,
					taskPath: task,
					submitHandle: handle,
					lifecycleRunner: lifecycle,
					hostFacts,
					configReader: () => ({
						transport: options.transportFailure ? "on" : "off",
						dpDisabled: false,
						signoffDisabled: false,
						mode: "auto",
						configRefs: [],
					}),
					runner: async (request) => {
						decideCalls.push(request);
						if (options.transportFailure) return { status: null, stdout: "", stderr: "", timedOut: true };
						throw new Error("Offline fixture must never contact DP");
					},
				});
			},
		],
	});
	sessions.push(h);
	const call = (name: string, input: Record<string, unknown>, id?: string) =>
		fauxAssistantMessage([fauxToolCall(name, input, { id })], { stopReason: "toolUse" });
	const ask = (
		choice: string,
		facts = "Only the task fixture is currently available",
		investigation: Record<string, string> = {},
	) =>
		call("ask_decision", {
			dp: "dp-w-check-task",
			trigger: "local-task",
			material: {
				task_goal: "Inspect evidence within the original budget",
				reachability_facts: facts,
				completed: "Read task.md",
				remaining: "Inspect upstream result",
				blockers: "Missing upstream result",
				constraints: "Original five minute budget and original tools only",
				investigation: {
					unknown: "Does the evidence contain the upstream result?",
					evidence_source: source,
					budget: "1 second",
					stop_condition: "Stop after one read and reassess",
					...investigation,
				},
			},
			preparation: {
				prepared_at: new Date().toISOString(),
				basis_catalog: [
					{
						id: "basis",
						text: "Actual worker reachability",
						material_refs: ["reachability_facts"],
						applies_to: [choice],
					},
				],
			},
		});
	const offer = () => {
		const results = h.session.messages.filter((message) => message.role === "toolResult");
		for (const message of [...results].reverse()) {
			const details = (message as { details?: { submit_offer?: SubmitOfferMetadata } }).details;
			if (details?.submit_offer) return details.submit_offer;
		}
		throw new Error("No registered ask offer");
	};
	const submit = (choice: string, id?: string) => () =>
		call(
			"submit_decision_handoff",
			{
				offer_id: offer().offer_id,
				choice,
				basis_id: "basis",
			},
			id,
		);
	const read = (file = source) => call("read", { path: file });
	const text = () =>
		h.session.messages
			.filter((m) => m.role === "toolResult")
			.map(getMessageText)
			.join("\n");
	const forbiddenWrite = () => call("write", { path: path.join(doc, "key-b", "secret.txt"), content: "forbidden" });
	return {
		root,
		doc,
		dir,
		task,
		card,
		setRun,
		boundaryReads,
		accountingFile,
		index,
		h,
		run,
		ask,
		submit,
		read,
		offer,
		reads,
		writes,
		receipts,
		decideCalls,
		text,
		forbiddenWrite,
		hostFacts,
		call,
	};
}

const end = () => fauxAssistantMessage("The bounded task ended.");
describe("T05 registered worker local continuity", () => {
	it("joins the real submit toolCallId and records only subsequent successful ordinary activity", async () => {
		const f = await fixture();
		let afterSubmit: unknown;
		f.h.setResponses([
			f.ask("continue"),
			f.submit("continue", "actual-submit"),
			() => {
				afterSubmit = f.run().local_reachability;
				return f.read();
			},
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(afterSubmit).toMatchObject({ source: "worker-local", choice: "continue", activity: false });
		expect(f.reads).toHaveLength(1);
		expect(f.run()).toMatchObject({
			status: "done",
			exit: 0,
			local_reachability: { choice: "continue", activity: true },
		});
		expect(f.run().reachability).toBeUndefined();
		expect(f.receipts).toEqual([]);
	});
	it.each(["model text", "failed tool", "unauthorized tool"])(
		"does not count %s as continue activity",
		async (kind) => {
			const f = await fixture();
			const extra =
				kind === "failed tool"
					? [f.read(path.join(f.dir, "missing.txt"))]
					: kind === "unauthorized tool"
						? [f.forbiddenWrite()]
						: [];
			f.h.setResponses([f.ask("continue"), f.submit("continue"), ...extra, end()]);
			await f.h.session.prompt("Execute the task");
			expect(f.writes).toEqual([]);
			expect(f.run()).toMatchObject({
				status: "failed",
				exit: 1,
				reachability: { decision_id: null, choice: null },
				local_reachability: { activity: false },
			});
			expect(f.receipts).toEqual([]);
		},
	);
	it("forged submit details plus a shape-only selection file cannot authorize activity", async () => {
		const f = await fixture({ adapter: false, forgeDetails: true });
		const shaped = path.join(f.doc, "key-a", "evidence", "decision-handoffs");
		fs.mkdirSync(shaped, { recursive: true });
		fs.writeFileSync(
			path.join(shaped, "forged.json"),
			JSON.stringify({ source: "worker-local", selected_action: "continue", action_state: "planned" }),
		);
		f.h.setResponses([f.ask("continue"), f.submit("continue"), f.read(), end()]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({ status: "failed", exit: 1, reachability: { decision_id: null, choice: null } });
		expect(f.run().local_reachability).toBeUndefined();
	});
	it.each([
		"old run",
		"other task",
		"old claim",
		"PM source",
		"wrong toolCallId",
		"wrong material",
		"wrong matter",
		"wrong choice",
	])("refuses a host observation bound to %s", async (kind) => {
		const f = await fixture({
			poison: (selection) => {
				if (kind === "old run") selection.record.host_binding.run_id = "local-task@old-run";
				if (kind === "other task") selection.record.host_binding.task_key = "other-task";
				if (kind === "old claim") selection.record.host_binding.claim_id = "old-host:99";
				if (kind === "PM source") selection.record.source = "pm";
				if (kind === "wrong toolCallId") selection.toolCallId = "unrelated-submit";
				if (kind === "wrong material") selection.record.material_digest = "different";
				if (kind === "wrong matter") selection.record.matter_ref = "different-dp";
				if (kind === "wrong choice") selection.choice = "terminate";
				return selection;
			},
		});
		f.h.setResponses([f.ask("continue"), f.submit("continue"), f.read(), end()]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({ status: "failed", exit: 1, reachability: { decision_id: null, choice: null } });
		expect(f.run().local_reachability).toBeUndefined();
	});
	it("reads exactly one prepared path, rejects stale reassessment and terminates with fresh evidence", async () => {
		const f = await fixture();
		f.h.setResponses([
			f.ask("investigate"),
			f.submit("investigate"),
			f.read(path.join(f.dir, "task.md")),
			f.read(),
			f.read(),
			f.ask("terminate"),
			f.ask("terminate", "Read evidence.txt: upstream result is absent"),
			f.submit("terminate"),
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toEqual([path.join(f.dir, "evidence.txt")]);
		expect(f.run()).toMatchObject({
			status: "failed",
			exit: 1,
			reachability: { decision_id: null, choice: null, evidence: "Read evidence.txt: upstream result is absent" },
			local_reachability: { choice: "terminate", activity: false },
		});
		expect(f.text()).toContain("fresh reachability_facts");
		expect(fs.readFileSync(path.join(f.dir, "output.md"), "utf8")).toContain("upstream result is absent");
		expect(readWorkerReachability(f.dir, "key-a", "local-task")).toMatchObject({
			decisionId: null,
			choice: null,
			local: { source: "worker-local", choice: "terminate", activity: false },
		});
		expect(f.receipts).toEqual([]);
	});
	it("a stale offer with older material in the same run cannot unblock the current assessment", async () => {
		const f = await fixture();
		let oldOffer: string | undefined;
		f.h.setResponses([
			f.ask("continue"),
			() => {
				oldOffer = f.offer().offer_id;
				return f.ask("continue", "The current remaining work has substantively changed");
			},
			() => f.call("submit_decision_handoff", { offer_id: oldOffer, choice: "continue", basis_id: "basis" }),
			f.read(),
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({ status: "failed", exit: 1 });
		expect(f.run().local_reachability).toBeUndefined();
	});
	it("fresh facts after a bounded read can continue through a separate successful ordinary tool", async () => {
		const f = await fixture();
		f.h.setResponses([
			f.ask("investigate"),
			f.submit("investigate"),
			f.read(),
			f.ask("continue", "Observed evidence.txt; the remaining authorized action is reachable"),
			f.submit("continue"),
			f.read(),
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toHaveLength(2);
		expect(f.run()).toMatchObject({
			status: "done",
			exit: 0,
			local_reachability: { choice: "continue", activity: true },
		});
		expect(f.receipts).toEqual([]);
	});
	it("investigate then continue cannot reopen another local investigation in the same run", async () => {
		const f = await fixture();
		f.h.setResponses([
			f.ask("investigate"),
			f.submit("investigate"),
			f.read(),
			f.ask("continue", "Evidence was read; continue within the remaining authorization"),
			f.submit("continue"),
			f.read(),
			f.ask("investigate", "Another evidence question would require a second local investigation"),
			f.submit("investigate"),
			f.read(),
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toHaveLength(2);
		expect(f.run()).toMatchObject({ status: "failed", exit: 1 });
		expect(f.receipts).toEqual([]);
	});
	it("a repeated committed investigate submission cannot purchase another read", async () => {
		const f = await fixture();
		f.h.setResponses([
			f.ask("investigate"),
			f.submit("investigate"),
			f.read(),
			f.submit("investigate"),
			f.read(),
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toHaveLength(1);
		expect(f.run()).toMatchObject({
			status: "failed",
			exit: 1,
			local_reachability: { choice: "investigate", activity: true },
		});
	});
	it("a failed bounded read consumes the one attempt without reporting successful activity", async () => {
		const f = await fixture({ readFails: true });
		f.h.setResponses([f.ask("investigate"), f.submit("investigate"), f.read(), f.read(), end()]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toHaveLength(1);
		expect(f.run()).toMatchObject({
			status: "failed",
			exit: 1,
			local_reachability: { choice: "investigate", activity: false },
		});
	});
	it("self-reported fresh facts cannot skip the prepared investigation read", async () => {
		const f = await fixture();
		f.h.setResponses([
			f.ask("investigate"),
			f.submit("investigate"),
			f.ask("continue", "I claim to know the evidence without reading it"),
			f.submit("continue"),
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({
			status: "failed",
			exit: 1,
			local_reachability: { choice: "investigate", activity: false },
		});
	});
	it("a failed evidence read cannot be promoted to local continue by changed model text", async () => {
		const f = await fixture({ readFails: true });
		f.h.setResponses([
			f.ask("investigate"),
			f.submit("investigate"),
			f.read(),
			f.ask("continue", "The read failed but I claim I can continue"),
			f.submit("continue"),
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toHaveLength(1);
		expect(f.run()).toMatchObject({
			status: "failed",
			exit: 1,
			local_reachability: { choice: "investigate", activity: false },
		});
	});
	it("expiration of the bounded read allowance permits zero reads without renewing the worker budget", async () => {
		const f = await fixture();
		const now = Date.now();
		const started = f.run().started_at;
		f.h.setResponses([
			f.ask("investigate"),
			f.submit("investigate"),
			() => {
				vi.spyOn(Date, "now").mockReturnValue(now + 2000);
				return f.read();
			},
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({
			status: "failed",
			exit: 1,
			started_at: started,
			local_reachability: { activity: false },
		});
	});
	it.each(["missing stop", "missing source", "over budget", "nonfinite budget", "outside scope"])(
		"permits zero reads for %s",
		async (kind) => {
			const f = await fixture();
			const plan: Record<string, string> = {};
			if (kind === "missing stop") plan.stop_condition = "";
			if (kind === "missing source") plan.evidence_source = path.join(f.dir, "absent.txt");
			if (kind === "over budget") plan.budget = "999 minutes";
			if (kind === "nonfinite budget") plan.budget = "unlimited";
			if (kind === "outside scope") {
				const other = fs.mkdtempSync(path.join(os.tmpdir(), "outside-t05-"));
				roots.push(other);
				plan.evidence_source = path.join(other, "outside.txt");
				fs.writeFileSync(plan.evidence_source, "outside");
			}
			f.h.setResponses([f.ask("investigate", undefined, plan), f.submit("investigate"), f.read(), end()]);
			await f.h.session.prompt("Execute the task");
			expect(f.reads).toEqual([]);
			expect(f.run()).toMatchObject({
				status: "failed",
				exit: 1,
				reachability: { decision_id: null, choice: null },
			});
		},
	);
	it("a continue cannot extend the original deadline", async () => {
		const f = await fixture();
		const now = Date.now();
		f.h.setResponses([
			f.ask("continue"),
			f.submit("continue"),
			() => {
				vi.spyOn(Date, "now").mockReturnValue(now + 301000);
				return f.read();
			},
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({
			status: "failed",
			exit: 1,
			reachability: { decision_id: null, choice: null },
			local_reachability: { activity: false },
		});
		expect(f.run().reachability.reason).toContain("Original worker budget");
	});
	it.each(["user-stop", "parent-cancel"] as const)(
		"a real host %s before submit forbids the local action",
		async (kind) => {
			const f = await fixture();
			f.h.setResponses([
				f.ask("continue"),
				() => {
					f.hostFacts.stop_signals = [{ kind, signal_ref: "fixture-host-stop" }];
					return f.submit("continue")();
				},
				f.read(),
				end(),
			]);
			await f.h.session.prompt("Execute the task");
			expect(f.reads).toEqual([]);
			expect(f.run()).toMatchObject({ status: "failed", exit: 1 });
			expect(f.run().local_reachability).toBeUndefined();
			expect(f.receipts).toEqual([]);
		},
	);
	it("a claim change after a planned continue blocks subsequent ordinary tools", async () => {
		const f = await fixture();
		f.h.setResponses([
			f.ask("continue"),
			f.submit("continue"),
			() => {
				fs.writeFileSync(
					f.index,
					"# Index Parallel\n| key-a | active | EXECUTE | other-host:99 | | fixture | now |\n",
				);
				return f.read();
			},
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({ status: "failed", exit: 1, local_reachability: { activity: false } });
	});
	it("a cancelled assistant boundary takes priority over a planned local continue", async () => {
		const f = await fixture();
		f.h.setResponses([
			f.ask("continue"),
			f.submit("continue"),
			fauxAssistantMessage("cancelled", { stopReason: "aborted" }),
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({
			status: "failed",
			exit: 1,
			aborted: true,
			local_reachability: { activity: false },
		});
		expect(f.receipts).toEqual([]);
	});
});

describe("T06-B post-commit worker stop boundaries", () => {
	it.each(["continue", "investigate"])(
		"persistently blocks %s after a host stop before the next tool",
		async (choice) => {
			const f = await fixture();
			const before = f.run();
			let committed: unknown;
			f.h.setResponses([
				f.ask(choice),
				f.submit(choice),
				() => {
					committed = f.run().local_reachability;
					// The service-request signal must not mask the wider real stop.
					f.hostFacts.stop_signals = [
						{ kind: "service-timeout", signal_ref: "request-only" },
						{ kind: "parent-cancel", signal_ref: "host-parent-cancel" },
					];
					return f.read();
				},
				end(),
			]);
			await f.h.session.prompt("Execute the task");
			expect(committed).toMatchObject({ source: "worker-local", choice, activity: false });
			expect(f.reads).toEqual([]);
			expect(f.run()).toMatchObject({
				status: "failed",
				exit: 1,
				run_id: before.run_id,
				started_at: before.started_at,
				local_reachability: { choice, activity: false },
				reachability: { decision_id: null, choice: null },
			});
			expect(f.run().reachability.reason).toContain("parent-cancel:host-parent-cancel; scope=pm-or-key");
			// A later prompt is a real second tool loop, not an unconsumed response.
			const terminalBytes = fs.readFileSync(path.join(f.dir, "run.json"), "utf8");
			f.hostFacts.stop_signals = [];
			f.h.setResponses([f.read(), f.read(), end()]);
			await f.h.session.prompt("Try two further tools after the stop was removed");
			expect(f.reads).toEqual([]);
			expect(fs.readFileSync(path.join(f.dir, "run.json"), "utf8")).toBe(terminalBytes);
			expect(f.h.eventsOfType("tool_execution_end").filter((e) => e.toolName === "read")).toHaveLength(3);
			expect(f.receipts).toEqual([]);
		},
	);

	it.each([
		["user-stop", "user-global"],
		["worker-deadline", "worker-run"],
		["key-budget", "pm-or-key"],
	] as const)("preserves the frozen scope for a post-commit %s", async (kind, scope) => {
		const f = await fixture();
		f.h.setResponses([
			f.ask("continue"),
			f.submit("continue"),
			() => {
				f.hostFacts.stop_signals = [{ kind, signal_ref: "host-observation" }];
				return f.read();
			},
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({ status: "failed", exit: 1, local_reachability: { activity: false } });
		expect(f.run().reachability.reason).toContain(`(${kind}:host-observation; scope=${scope})`);
	});

	it.each(["continue", "investigate"])(
		"does not count an in-flight %s result after stop, including errors",
		async (choice) => {
			for (const readFails of [false, true]) {
				const f = await fixture({
					readFails,
					onRead: () => {
						f.hostFacts.stop_signals = [{ kind: "parent-cancel", signal_ref: "during-tool" }];
					},
				});
				f.h.setResponses([f.ask(choice), f.submit(choice), f.read(), f.read(), end()]);
				await f.h.session.prompt("Execute the task");
				expect(f.reads).toHaveLength(1);
				expect(f.run()).toMatchObject({
					status: "failed",
					exit: 1,
					local_reachability: { choice, activity: false },
					reachability: { decision_id: null, choice: null },
				});
				expect(f.run().reachability.reason).toContain("during-tool");
				f.h.setResponses([f.read(), f.read(), end()]);
				await f.h.session.prompt("Retry after failed or completed in-flight result");
				expect(f.reads).toHaveLength(1);
				expect(f.run().local_reachability.activity).toBe(false);
				expect(f.receipts).toEqual([]);
			}
		},
	);

	it.each(["canceled", "stopped", "failed-by-stop", "failed", "done", "lost"])(
		"never resurrects an external %s written while a tool is in flight",
		async (status) => {
			let terminalBytes = "";
			const outputBytes = `External ${status} product must survive unchanged\r\n`;
			const f = await fixture({
				readFails: true,
				onRead: () => {
					terminalBytes = f.setRun({ status, exit: 19, ended_at: "2026-11-15T14:59:00.000Z" });
					fs.writeFileSync(path.join(f.dir, "output.md"), outputBytes);
				},
			});
			f.h.setResponses([f.ask("continue"), f.submit("continue"), f.read(), end()]);
			await f.h.session.prompt("Execute the task");
			expect(f.reads).toHaveLength(1);
			expect(f.run()).toMatchObject({ status, exit: 19, local_reachability: { activity: false } });
			expect(fs.readFileSync(path.join(f.dir, "run.json"), "utf8")).toBe(terminalBytes);
			f.h.setResponses([f.read(), f.read(), end()]);
			await f.h.session.prompt("Do not restart the terminal run");
			expect(f.reads).toHaveLength(1);
			expect(fs.readFileSync(path.join(f.dir, "run.json"), "utf8")).toBe(terminalBytes);
			expect(fs.readFileSync(path.join(f.dir, "output.md"), "utf8")).toBe(outputBytes);
		},
	);

	it.each(["run_id", "owner_key", "task_key", "started_at", "kind"])(
		"does not overwrite a newer in-flight %s binding",
		async (field) => {
			let newerBytes = "";
			const f = await fixture({
				onRead: () => {
					newerBytes = f.setRun({
						[field]:
							field === "started_at" ? "2026-11-15T15:10:00.000Z" : field === "kind" ? "review" : "new-owner",
					});
				},
			});
			f.h.setResponses([f.ask("continue"), f.submit("continue"), f.read(), end()]);
			await f.h.session.prompt("Execute the task");
			expect(f.reads).toHaveLength(1);
			expect(fs.readFileSync(path.join(f.dir, "run.json"), "utf8")).toBe(newerBytes);
			f.h.setResponses([f.read(), f.read(), end()]);
			await f.h.session.prompt("Old closure must remain blocked");
			expect(f.reads).toHaveLength(1);
			expect(fs.readFileSync(path.join(f.dir, "run.json"), "utf8")).toBe(newerBytes);
		},
	);

	it.each(["throw", "gap", "shape", "signal"] as const)(
		"treats a host reader %s as an authority gap, never parent-cancel",
		async (boundaryFailure) => {
			const f = await fixture({ boundaryFailure });
			f.h.setResponses([f.ask("continue"), f.submit("continue"), f.read(), end()]);
			await f.h.session.prompt("Execute the task");
			expect(f.reads).toEqual([]);
			expect(f.run()).toMatchObject({ status: "failed", exit: 1, local_reachability: { activity: false } });
			expect(f.run().reachability.reason).toContain("authority/budget gap");
			expect(f.run().reachability.reason).not.toContain("parent-cancel");
		},
	);

	it("keeps an explicit trusted adapter legal without a card, but has no implicit missing-card bypass", async () => {
		const f = await fixture({ boundaryReader: false });
		let planned: unknown;
		f.h.setResponses([
			f.ask("continue"),
			f.submit("continue"),
			() => {
				planned = f.run().local_reachability;
				return f.read();
			},
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(planned).toMatchObject({ activity: false });
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({ status: "failed", exit: 1, local_reachability: { activity: false } });
		expect(f.run().reachability.reason).toContain("card_path");
		const legal = await fixture();
		legal.h.setResponses([legal.ask("continue"), legal.submit("continue"), legal.read(), end()]);
		await legal.h.session.prompt("Execute explicitly trusted task");
		expect(legal.reads).toHaveLength(1);
		expect(legal.run()).toMatchObject({ status: "done", exit: 0, local_reachability: { activity: true } });
		expect(legal.boundaryReads.length).toBeGreaterThanOrEqual(3);
		expect(new Set(legal.boundaryReads)).toEqual(new Set([legal.run().local_reachability.local_ref]));
	});

	it("ordinary service timeout does not stop an otherwise authorized local worker", async () => {
		const f = await fixture();
		f.h.setResponses([
			f.ask("continue"),
			f.submit("continue"),
			() => {
				f.hostFacts.stop_signals = [{ kind: "service-timeout", signal_ref: "ordinary-service-request" }];
				return f.read();
			},
			f.read(),
			end(),
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toHaveLength(2);
		expect(f.run()).toMatchObject({ status: "done", exit: 0, local_reachability: { activity: true } });
		expect(f.receipts).toEqual([]);
	});

	it("rechecks stop on settle even after earlier successful activity", async () => {
		const f = await fixture();
		f.h.setResponses([
			f.ask("continue"),
			f.submit("continue"),
			f.read(),
			() => {
				expect(f.run().local_reachability.activity).toBe(true);
				f.hostFacts.stop_signals = [{ kind: "user-stop", signal_ref: "after-last-result" }];
				return end();
			},
		]);
		await f.h.session.prompt("Execute the task");
		expect(f.reads).toHaveLength(1);
		expect(f.run()).toMatchObject({ status: "failed", exit: 1, local_reachability: { activity: false } });
		expect(f.run().reachability.reason).toContain("after-last-result");
	});

	it("does not turn two real fake-runner DP timeouts into a worker-wide stop", async () => {
		const f = await fixture({ transportFailure: true });
		const before = f.run();
		f.h.setResponses([
			f.ask("continue", "First unresolved bounded question"),
			f.submit("continue"),
			f.read(),
			f.ask("continue", "New evidence, second unresolved bounded question"),
			f.submit("continue"),
			f.read(),
			end(),
		]);
		await f.h.session.prompt("Continue only after each actual local submit");
		expect(f.decideCalls).toHaveLength(2);
		expect(f.reads).toHaveLength(2);
		expect(f.text()).toContain('"unavailable":"timeout"');
		expect(f.run()).toMatchObject({
			status: "done",
			exit: 0,
			run_id: before.run_id,
			started_at: before.started_at,
			local_reachability: { activity: true },
		});
		expect(f.receipts).toEqual([]);
	});

	it("bounds an unresponsive asynchronous host read by the ORIGINAL remaining budget", async () => {
		const f = await fixture({ boundaryFailure: "timeout" });
		const before = f.run();
		f.h.setResponses([
			f.ask("continue"),
			f.submit("continue"),
			() => {
				vi.spyOn(Date, "now").mockReturnValue(Date.parse(before.started_at) + 299990);
				return f.read();
			},
			end(),
		]);
		await f.h.session.prompt("Reader cannot buy a new five-minute budget");
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({
			status: "failed",
			exit: 1,
			run_id: before.run_id,
			started_at: before.started_at,
			local_reachability: { activity: false },
		});
		expect(f.run().reachability.reason).toContain("Original worker budget expired during continuation fact read");
		f.h.setResponses([f.read(), f.read(), end()]);
		await f.h.session.prompt("Persistent block after host read timed out");
		expect(f.reads).toEqual([]);
	});

	it.each([false, true])("records the original deadline crossed inside a host reader (throws=%s)", async (throws) => {
		const afterDeadline = Date.now() + 600_000;
		const f = await fixture({
			onBoundary: () => {
				vi.spyOn(Date, "now").mockReturnValue(afterDeadline);
			},
			boundaryFailure: throws ? "throw" : undefined,
		});
		f.h.setResponses([f.ask("continue"), f.submit("continue"), f.read(), end()]);
		await f.h.session.prompt("Read only within the allocated deadline");
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({ status: "failed", exit: 1, stop_kind: "worker-deadline" });
	});

	it("rechecks ownership after an asynchronous host boundary read", async () => {
		let newerBytes = "";
		const f = await fixture({
			onBoundary: async () => {
				await new Promise((resolve) => setTimeout(resolve, 0));
				newerBytes = f.setRun({ run_id: "new-run-during-host-read", exit: 27 });
			},
		});
		f.h.setResponses([f.ask("continue"), f.submit("continue"), f.read(), end()]);
		await f.h.session.prompt("Host await must not grant a stale closure");
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({ run_id: "new-run-during-host-read", status: "running", exit: 27 });
		expect(fs.readFileSync(path.join(f.dir, "run.json"), "utf8")).toBe(newerBytes);
	});

	it("keeps a fully pinned default-runtime continuation blocked until its live host reader is wired", async () => {
		const f = await fixture({ runtime: true, boundaryReader: false });
		let planned: unknown;
		f.h.setResponses([
			f.ask("continue"),
			f.submit("continue"),
			() => {
				planned = f.run().local_reachability;
				return f.read();
			},
			end(),
		]);
		await f.h.session.prompt("Files alone are not a live accounting grant");
		expect(planned, f.text()).toMatchObject({ activity: false });
		expect(f.reads).toEqual([]);
		expect(f.run()).toMatchObject({ status: "failed", exit: 1, local_reachability: { activity: false } });
		expect(f.run().reachability.reason).toContain("live host continuation source is not wired");
	});

	it.each(["before-tool", "in-flight"])(
		"preserves the same-source default-runtime canceled record at %s",
		async (timing) => {
			let terminalBytes = "";
			const cancel = () => {
				terminalBytes = f.setRun({ status: "canceled", exit: 23 });
			};
			const f = await fixture({ runtime: true, onRead: timing === "in-flight" ? cancel : undefined });
			f.h.setResponses([
				f.ask("continue"),
				f.submit("continue"),
				() => {
					if (timing === "before-tool") cancel();
					return f.read();
				},
				end(),
			]);
			await f.h.session.prompt("Read the same authoritative cancellation source");
			expect(f.reads).toHaveLength(timing === "in-flight" ? 1 : 0);
			expect(f.run()).toMatchObject({ status: "canceled", exit: 23, local_reachability: { activity: false } });
			expect(fs.readFileSync(path.join(f.dir, "run.json"), "utf8")).toBe(terminalBytes);
			f.h.setResponses([f.read(), f.read(), end()]);
			await f.h.session.prompt("Do not resurrect cancellation");
			expect(f.reads).toHaveLength(timing === "in-flight" ? 1 : 0);
			expect(fs.readFileSync(path.join(f.dir, "run.json"), "utf8")).toBe(terminalBytes);
		},
	);

	it("does not record an in-flight result after the live host accounting source disappears", async () => {
		const f = await fixture({ runtime: true, onRead: () => fs.rmSync(f.accountingFile) });
		f.h.setResponses([f.ask("continue"), f.submit("continue"), f.read(), end()]);
		await f.h.session.prompt("Initial commit cannot replace missing live accounting");
		expect(f.reads).toHaveLength(1);
		expect(f.run()).toMatchObject({ status: "failed", exit: 1, local_reachability: { activity: false } });
		expect(f.run().reachability.reason).toContain("authority/budget gap");
	});

	it("commits through the default runtime adapter and performs real ordinary activity", async () => {
		const f = await fixture({ runtime: true });
		const before = f.run();
		f.h.setResponses([f.ask("continue"), f.submit("continue"), f.read(), end()]);
		await f.h.session.prompt("Execute pinned task with the default adapter");
		expect(f.reads, f.text()).toHaveLength(1);
		expect(f.run()).toMatchObject({
			status: "done",
			exit: 0,
			run_id: before.run_id,
			started_at: before.started_at,
			local_reachability: { activity: true },
		});
		expect(fs.readdirSync(path.join(f.dir, "local-decisions")).filter((name) => name.endsWith(".json"))).toHaveLength(
			1,
		);
		expect(f.receipts).toEqual([]);
	});

	it.each(["missing card", "SHA drift", "repinned card", "bad budget", "deadline", "claim drift"])(
		"default runtime adapter blocks %s after a real committed selection",
		async (kind) => {
			const f = await fixture({ runtime: true });
			const before = f.run();
			let planned: unknown;
			f.h.setResponses([
				f.ask("continue"),
				f.submit("continue"),
				() => {
					planned = f.run().local_reachability;
					if (kind === "missing card") fs.rmSync(f.card);
					if (kind === "SHA drift") fs.appendFileSync(f.card, "\nchanged bytes\n");
					if (kind === "repinned card" || kind === "bad budget") {
						const bytes = fs
							.readFileSync(f.card, "utf8")
							.replace("`max_steps`: 20", kind === "bad budget" ? "`max_steps`: invalid" : "`max_steps`: 21");
						fs.writeFileSync(f.card, bytes);
						// A newly pinned but malformed declaration must also fail closed.
						fs.writeFileSync(
							f.task,
							fs
								.readFileSync(f.task, "utf8")
								.replace(
									/card_sha256: [a-f0-9]+/,
									`card_sha256: ${createHash("sha256").update(bytes).digest("hex")}`,
								),
						);
					}
					if (kind === "deadline") vi.spyOn(Date, "now").mockReturnValue(Date.parse(before.started_at) + 7000);
					if (kind === "claim drift")
						fs.writeFileSync(
							f.index,
							"# Index Parallel\n| key-a | active | EXECUTE | foreign:19 | | fixture | now |\n",
						);
					return f.read();
				},
				end(),
			]);
			await f.h.session.prompt("Execute pinned task");
			expect(planned, f.text()).toMatchObject({ choice: "continue", activity: false });
			expect(f.reads).toEqual([]);
			expect(f.run()).toMatchObject({
				status: "failed",
				exit: 1,
				run_id: before.run_id,
				started_at: before.started_at,
				local_reachability: { activity: false },
				reachability: { decision_id: null, choice: null },
			});
			if (kind === "deadline") expect(f.run().reachability.reason).toContain("worker-deadline");
			if (["missing card", "SHA drift", "repinned card", "bad budget"].includes(kind)) {
				expect(f.run().reachability.reason).toContain("authority/budget gap");
				expect(f.run().reachability.reason).not.toContain("parent-cancel");
			}
			f.h.setResponses([f.read(), f.read(), end()]);
			await f.h.session.prompt("Repeat calls must not regain authority");
			expect(f.reads).toEqual([]);
			expect(f.receipts).toEqual([]);
		},
	);
});
