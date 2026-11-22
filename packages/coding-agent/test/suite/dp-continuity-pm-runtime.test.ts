/**
 * T06 — runtime trusted-host adapter (`pm/runtime-host-adapter.ts`).
 *
 * These are host fixtures: real files in a temp project/.agenticdoc (index,
 * run/envelope, independently registered pin, host-owned accounting history).
 * Real registered tools use AgentSession + faux provider, no paid API/network.
 *
 * Regressions cover both real frozen-store disk success and fail-closed gaps:
 *  - unreadable/ambiguous/missing authority never mints a default grant;
 *  - the card supplies ceilings, independent host history supplies live counters;
 *  - post-commit stops are re-read from the same authority derivation;
 *  - target bytes alone cannot establish an observed action/execution.
 */

import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, describe, expect, it } from "vitest";
import {
	ASK_DECISION_TOOL,
	decisionMatterRef,
	decisionMatterVersion,
	registerAskDecisionTool,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import {
	registerSubmitDecisionHandoffTool,
	SUBMIT_DECISION_HANDOFF_TOOL,
	type SubmitDecisionHostHandle,
	type SubmitDecisionToolConfig,
	type SubmitOfferMetadata,
} from "../../src/extensions/agent-team-loop/pm/host-submit.ts";
import {
	buildMatterBudgetFromCard,
	createRuntimeHostAdapter,
	preflightReservation,
	type RuntimeHostAdapterConfig,
	type RuntimeHostAuthorization,
	type RuntimeOfferExpected,
	readRuntimeStopFacts,
	TARGET_DIGEST_VERIFIER_ID,
	targetFileDigest,
	verifyTargetProof,
} from "../../src/extensions/agent-team-loop/pm/runtime-host-adapter.ts";
import { sha256EolNormalizedBytes } from "../../src/extensions/agent-team-loop/shared/card-digest.ts";
import type { MatterBudgetV1 } from "../../src/extensions/agent-team-loop/shared/decision-handoff.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import { LocalSelectionStore } from "../../src/extensions/agent-team-loop/shared/local-selection-store.ts";
import { createHarness, type Harness } from "./harness.ts";

const harnesses: Harness[] = [];
const roots: string[] = [];
afterEach(() => {
	for (const h of harnesses.splice(0)) h.cleanup();
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

const claim = currentClaimId();
const keyName = "key-a";
const taskKey = "local-task";

const budgetBlock = [
	"## 事项预算事实",
	"- `budget_ref`: `tasks/T-01.md#事项预算事实` + 其 SHA",
	"- `matter_ref`: `key-a/T-01`；`parent_matter_ref`: `key-a`",
	"- `deadline`: `run.json.started_at + 30m`（由 harness 派生）",
	"- `max_steps`: 20",
	"- `no_progress_limit`: 5",
	"- `remaining_cost`: 20，`cost_consumed` 与 `steps_consumed` 同单位（1 cost unit ≡ 1 tool call；卡明确约定）",
	"- `steps_consumed` / `no_progress_count`：本运行初始 0",
	"- `source_refs`: 卡 SHA、`run.json`、`_index.parallel`、`task.md` 头",
	"",
];

function sha256(text: string): string {
	return crypto.createHash("sha256").update(Buffer.from(text, "utf8")).digest("hex");
}

interface Fixture {
	root: string;
	doc: string;
	dir: string;
	cardFile: string;
	authorization: RuntimeHostAuthorization;
	observedBudgets: MatterBudgetV1[];
	hooks: NonNullable<SubmitDecisionToolConfig["runtimeHost"]>;
	returns: {
		run: Record<string, unknown>;
		expected: RuntimeOfferExpected;
		adapter: ReturnType<typeof createRuntimeHostAdapter>;
	};
}

function fixture(options: { status?: string; card?: string; runStartedAt?: string } = {}): Fixture {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "t06-runtime-"));
	roots.push(root);
	const doc = path.join(root, ".agenticdoc");
	const dir = path.join(doc, keyName, "workers", taskKey);
	fs.mkdirSync(path.join(doc, keyName, "tasks"), { recursive: true });
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(
		path.join(doc, "_index.parallel"),
		`# Index Parallel\n| ${keyName} | active | EXECUTE | ${claim} | | fixture | now |\n`,
	);
	const startedAt = options.runStartedAt ?? new Date(Date.now() - 60_000).toISOString();
	const cardText =
		options.card ?? `# Real titled fixture\n\nowning_pm_claim: ${claim}\ntitle: fixture\n\n${budgetBlock.join("\n")}`;
	const cardFile = path.join(doc, keyName, "tasks", "T-01.md");
	fs.writeFileSync(cardFile, cardText);
	const run = {
		schema: 1,
		task_key: taskKey,
		run_id: `${taskKey}@${startedAt}`,
		owner_key: keyName,
		kind: "coding",
		status: options.status ?? "running",
		started_at: startedAt,
		artifacts: [],
	};
	fs.writeFileSync(path.join(dir, "run.json"), JSON.stringify(run));
	fs.writeFileSync(
		path.join(dir, "task.md"),
		`type: coding\ncard_path: tasks/T-01.md\ncard_sha256: ${sha256(cardText)}\n\nbody\n`,
	);
	const expected: RuntimeOfferExpected = {
		matter_identity: "business-matter",
		identity: {
			source: "worker-local",
			key: keyName,
			role: "coding",
			owner: keyName,
			taskKey,
			runId: String(run.run_id),
		},
		matter_ref: "matter-hash",
		matter_version: "v1",
		material_digest: "material-digest",
		basis_digest: "basis-digest",
		budget_ref: "tasks/T-01.md#事项预算事实",
	};
	const authorization: RuntimeHostAuthorization = {
		localRef: "local-ref-1",
		key: keyName,
		source: "worker-local",
		role: "coding",
		owningPmClaim: claim,
		taskKey,
		runId: String(run.run_id),
		cardPath: "tasks/T-01.md",
		cardSha256: sha256(cardText),
		budgetStartedAt: startedAt,
		authorizationUnit: "key-a/T-01",
		matterRef: "business-matter",
	};
	// Host-created history for this isolated fresh run. The seam reads actual
	// finite state, not card initial counters. Production C/I must observe tools.
	const historyFile = path.join(root, "host-budget-history.json");
	fs.writeFileSync(historyFile, JSON.stringify({ steps: 0, cost: 0, noProgress: 0, remaining: 20 }));
	const observedBudgets: MatterBudgetV1[] = [];
	const hooks: NonNullable<SubmitDecisionToolConfig["runtimeHost"]> = {
		authorizationFor: () => structuredClone(authorization),
		budgetSnapshotFor: ({ cardBudget, expected: offerExpected, nowMs }) => {
			const history = JSON.parse(fs.readFileSync(historyFile, "utf8")) as {
				steps: number;
				cost: number;
				noProgress: number;
				remaining: number;
			};
			const observationRef = "host-budget-history.json#fresh-host-run";
			const budget: MatterBudgetV1 = {
				...cardBudget,
				matter_ref: offerExpected.matter_ref,
				steps_consumed: history.steps,
				cost_consumed: history.cost,
				no_progress_count: history.noProgress,
				remaining_cost: history.remaining,
				source_refs: [...cardBudget.source_refs, observationRef],
			};
			observedBudgets.push(structuredClone(budget));
			const preflight = preflightReservation(budget, nowMs);
			if (!preflight.ok) return preflight;
			return { ok: true, value: { budget, preflight: preflight.value, observationRef } };
		},
	};
	const adapter = createRuntimeHostAdapter({ agenticdocRoot: doc, expectedFor: () => expected, ...hooks });
	return { root, doc, dir, cardFile, authorization, observedBudgets, hooks, returns: { run, expected, adapter } };
}

function request(run: Record<string, unknown>) {
	return {
		key: keyName,
		source: "worker-local" as const,
		ref: "local-ref-1",
		task_key: taskKey,
		run_id: String(run.run_id),
	};
}

describe("T06 runtime host adapter — authority facts", () => {
	it("builds the trusted context from real index/run/task/card files", async () => {
		const { returns } = fixture();
		const trusted = await returns.adapter.readTrustedContext(request(returns.run));
		expect(trusted).toBeDefined();
		expect(trusted?.self_claim_id).toBe(claim);
		expect(trusted?.role).toBe("coding");
		expect(trusted?.task_key).toBe(taskKey);
		expect(trusted?.run_id).toBe(String(returns.run.run_id));
		expect(trusted?.expected.budget_ref).toBe("tasks/T-01.md#事项预算事实");
		const budget = trusted?.budget as Record<string, unknown>;
		// The independently registered host grant binds the full offer to this
		// card/unit; the live snapshot projects the host hash, never an arbitrary
		// overwrite based only on expected.matter_ref.
		expect(budget.matter_ref).toBe("matter-hash");
		expect(budget.parent_matter_ref).toBe("key-a");
		expect(budget.source_refs).toContain("host-budget-history.json#fresh-host-run");
		expect(budget.max_steps).toBe(20);
		expect(budget.no_progress_limit).toBe(5);
		expect(budget.remaining_cost).toBe(20);
		expect(budget.steps_consumed).toBe(0);
		expect(budget.no_progress_count).toBe(0);
		expect(budget.deadline).toBe(new Date(Date.parse(String(returns.run.started_at)) + 30 * 60_000).toISOString());
		expect(Array.isArray(budget.source_refs)).toBe(true);
		expect(trusted?.stop_signals).toEqual([]);
	});

	it("refuses when the index has no active exact-self row", async () => {
		const { doc, returns } = fixture();
		fs.writeFileSync(
			path.join(doc, "_index.parallel"),
			`# Index Parallel\n| ${keyName} | idle | EXECUTE | ${claim} | | f | now |\n`,
		);
		expect(await returns.adapter.readTrustedContext(request(returns.run))).toBeUndefined();
	});

	it("refuses an ambiguous index (two active rows for the key)", async () => {
		const { doc, returns } = fixture();
		fs.writeFileSync(
			path.join(doc, "_index.parallel"),
			`# Index Parallel\n| ${keyName} | active | EXECUTE | ${claim} | | f | now |\n| ${keyName} | active | EXECUTE | other:1 | | f | now |\n`,
		);
		expect(await returns.adapter.readTrustedContext(request(returns.run))).toBeUndefined();
	});

	it("refuses when the run does not belong to this task/run/owner", async () => {
		const { dir, returns } = fixture();
		const drifted = { ...returns.run, owner_key: "other-key" };
		fs.writeFileSync(path.join(dir, "run.json"), JSON.stringify(drifted));
		expect(await returns.adapter.readTrustedContext(request(returns.run))).toBeUndefined();
	});

	it("refuses a terminal (non-running, non-stop) run instead of inventing a stop", async () => {
		const { returns } = fixture({ status: "done" });
		expect(await returns.adapter.readTrustedContext(request(returns.run))).toBeUndefined();
	});

	it("refuses when the pinned card bytes drifted from task.md card_sha256", async () => {
		const { cardFile, returns } = fixture();
		fs.writeFileSync(cardFile, `${fs.readFileSync(cardFile, "utf8")}\ntrailing drift\n`);
		expect(await returns.adapter.readTrustedContext(request(returns.run))).toBeUndefined();
	});

	it("refuses missing budget declarations without defaulting them", async () => {
		const card = `owning_pm_claim: ${claim}\n\n## 事项预算事实\n- \`budget_ref\`: \`tasks/T-01.md#b\`\n- \`matter_ref\`: \`key-a/T-01\`\n- \`deadline\`: \`run.json.started_at + 30m\`\n- \`remaining_cost\`: 20\n`;
		const { returns } = fixture({ card });
		expect(await returns.adapter.readTrustedContext(request(returns.run))).toBeUndefined();
	});

	it("refuses a non-finite relative deadline", async () => {
		const card = `owning_pm_claim: ${claim}\n\n${budgetBlock.map((line) => (line.startsWith("- `deadline`") ? "- `deadline`: `run.json.started_at + soon`" : line)).join("\n")}`;
		const { returns } = fixture({ card });
		expect(await returns.adapter.readTrustedContext(request(returns.run))).toBeUndefined();
	});

	it("refuses arbitrary host expected matter without an independently bound authorization", async () => {
		const { doc, returns, hooks } = fixture();
		const adapter = createRuntimeHostAdapter({
			agenticdocRoot: doc,
			...hooks,
			expectedFor: () => ({
				...returns.expected,
				matter_ref: "offer-matter-hash",
				matter_identity: "different-business-matter",
			}),
		});
		expect(await adapter.readTrustedContext(request(returns.run))).toBeUndefined();
	});

	it("refuses an empty expected matter instead of inventing one", async () => {
		const { doc, returns } = fixture();
		const adapter = createRuntimeHostAdapter({
			agenticdocRoot: doc,
			expectedFor: () => ({ ...returns.expected, matter_ref: "" }),
		});
		expect(await adapter.readTrustedContext(request(returns.run))).toBeUndefined();
	});

	it("refuses a signed or exponent-form card count instead of reading a different number", async () => {
		const negative = `owning_pm_claim: ${claim}\n\n${budgetBlock.map((line) => (line.startsWith("- `max_steps`") ? "- `max_steps`: -20" : line)).join("\n")}`;
		const negativeFixture = fixture({ card: negative });
		expect(
			await negativeFixture.returns.adapter.readTrustedContext(request(negativeFixture.returns.run)),
		).toBeUndefined();
		const exponent = `owning_pm_claim: ${claim}\n\n${budgetBlock.map((line) => (line.startsWith("- `remaining_cost`") ? line.replace(": 20，", ": 1e309，") : line)).join("\n")}`;
		const exponentFixture = fixture({ card: exponent });
		expect(
			await exponentFixture.returns.adapter.readTrustedContext(request(exponentFixture.returns.run)),
		).toBeUndefined();
	});

	it("surfaces a real stop status as a parent-cancel signal, not as silence", async () => {
		const { returns } = fixture({ status: "failed-by-stop" });
		const trusted = await returns.adapter.readTrustedContext(request(returns.run));
		expect(trusted?.stop_signals?.map((signal) => signal.kind)).toEqual(["parent-cancel"]);
	});

	it("refuses when no offer expectation exists for the ref", async () => {
		const { doc, returns } = fixture();
		const adapter = createRuntimeHostAdapter({ agenticdocRoot: doc, expectedFor: () => undefined });
		expect(await adapter.readTrustedContext(request(returns.run))).toBeUndefined();
	});
});

describe("T06 runtime host adapter — stop derivation", () => {
	it("returns no stop and no gaps for a live run", () => {
		const { doc, returns } = fixture();
		const facts = readRuntimeStopFacts({
			agenticdocRoot: doc,
			key: keyName,
			taskKey,
			runId: String(returns.run.run_id),
		});
		expect(facts).toEqual({ stop_signals: [], gaps: [] });
	});

	it("reports a passed card deadline as a worker-deadline stop (the only new stop fact)", async () => {
		const { doc, returns } = fixture({ runStartedAt: new Date(Date.now() - 3 * 60 * 60_000).toISOString() });
		// deadline = started_at + 30m, so a 3h-old run is already past it.
		const trusted = await returns.adapter.readTrustedContext(request(returns.run));
		expect(trusted?.stop_signals?.map((signal) => signal.kind)).toEqual(["worker-deadline"]);
		const facts = readRuntimeStopFacts({
			agenticdocRoot: doc,
			key: keyName,
			taskKey,
			runId: String(returns.run.run_id),
		});
		expect(facts.stop_signals.map((signal) => signal.kind)).toEqual(["worker-deadline"]);
	});

	it("reports unreadable facts as gaps (never as 'no stop')", () => {
		const { doc } = fixture();
		const facts = readRuntimeStopFacts({
			agenticdocRoot: doc,
			key: keyName,
			taskKey: "missing-task",
			runId: "missing-task@2026-01-01T00:00:00.000Z",
		});
		expect(facts.stop_signals).toEqual([]);
		expect(facts.gaps.length).toBeGreaterThan(0);
	});
});

describe("T06 runtime host adapter — budget preflight", () => {
	const base: MatterBudgetV1 = {
		schema_version: 1,
		budget_ref: "b",
		matter_ref: "m",
		deadline: new Date(Date.now() + 60_000).toISOString(),
		max_steps: 4,
		no_progress_limit: 2,
		remaining_cost: 2,
		steps_consumed: 0,
		cost_consumed: 0,
		no_progress_count: 0,
		source_refs: ["card"],
	};

	it("grants one step/cost unit while the finite budget allows it", () => {
		const result = preflightReservation(base);
		expect(result.ok).toBe(true);
		const value = result.ok ? result.value : {};
		expect(value.granted).toBe(true);
		expect(value.reserved_steps).toBe(1);
		expect(value.remaining_after_cost).toBe(1);
	});

	it("refuses once the no-progress limit is reached", () => {
		const result = preflightReservation({ ...base, no_progress_count: 2 });
		expect(result.ok && result.value.granted).toBe(false);
		expect(result.ok && result.value.reason).toBe("budget-exhausted");
	});

	it("refuses once the deadline has passed", () => {
		const result = preflightReservation({ ...base, deadline: new Date(Date.now() - 1000).toISOString() });
		expect(result.ok && result.value.granted).toBe(false);
	});
});

describe("T06 runtime host adapter — target-digest-v1 verifier", () => {
	it("proves the exact bytes of the result file and correlates the refs", () => {
		const { root } = fixture();
		fs.writeFileSync(path.join(root, "product.txt"), "real bytes\n");
		const digest = targetFileDigest(root, "product.txt");
		const expectedDigest = crypto.createHash("sha256").update("real bytes\n").digest("hex");
		expect(digest.ok && digest.value).toBe(expectedDigest);
		const proof = verifyTargetProof({
			projectRoot: root,
			resultRef: "product.txt",
			actionRef: "call_abc123",
			executor: "run-1#call_abc123",
			observedEffect: `sha256:${digest.ok ? digest.value : ""}`,
		});
		expect(proof.ok).toBe(true);
		if (!proof.ok) return;
		expect(proof.value.verifier_ref).toBe(TARGET_DIGEST_VERIFIER_ID);
		expect(proof.value.effect_state).toBe("known");
		expect(proof.value.target_digest).toBe(digest.ok ? digest.value : "");
	});

	it("refuses drift instead of reporting a third effect state", () => {
		const { root } = fixture();
		fs.writeFileSync(path.join(root, "product.txt"), "real bytes\n");
		const digest = targetFileDigest(root, "product.txt");
		const proof = verifyTargetProof({
			projectRoot: root,
			resultRef: "product.txt",
			actionRef: "call_abc123",
			executor: "run-1#call_abc123",
			observedEffect: `sha256:${digest.ok ? digest.value : ""}`,
			expectedTargetDigest: "0".repeat(64),
		});
		expect(proof.ok).toBe(false);
	});

	it("refuses an observed_effect that does not match the bytes", () => {
		const { root } = fixture();
		fs.writeFileSync(path.join(root, "product.txt"), "real bytes\n");
		const proof = verifyTargetProof({
			projectRoot: root,
			resultRef: "product.txt",
			actionRef: "call_abc123",
			executor: "run-1#call_abc123",
			observedEffect: "sha256:deadbeef",
		});
		expect(proof.ok).toBe(false);
	});

	it("refuses a target that escapes the project root", () => {
		const { root } = fixture();
		const outside = path.join(path.dirname(root), `${path.basename(root)}-outside.txt`);
		fs.writeFileSync(outside, "actual outside bytes");
		try {
			const escaped = targetFileDigest(root, path.relative(root, outside));
			expect(escaped.ok).toBe(false);
		} finally {
			fs.rmSync(outside);
		}
	});
});

function declaredBudget(card = budgetBlock.join("\n"), runStartedAt = "2026-11-15T10:00:00.000Z") {
	return buildMatterBudgetFromCard(card, {
		cardRef: "tasks/T-01.md",
		cardSha256: "a".repeat(64),
		runStartedAt,
		runRef: "workers/local-task/run.json",
		indexRef: "_index.parallel",
	});
}

const numericFields = [
	"max_steps",
	"no_progress_limit",
	"remaining_cost",
	"steps_consumed",
	"cost_consumed",
	"no_progress_count",
];
function explicitBudget(): string {
	return budgetBlock
		.join("\n")
		.replace(
			"- `steps_consumed` / `no_progress_count`：本运行初始 0",
			"- `steps_consumed`: 0\n- `cost_consumed`: 0\n- `no_progress_count`: 0",
		);
}

describe("T06-A strict card declaration parser", () => {
	it("preserves the real titled card's combined counters and explicit step-cost contract", () => {
		const result = declaredBudget();
		expect(result.ok).toBe(true);
		if (!result.ok) return;
		expect(result.value.budget.parent_matter_ref).toBe("key-a");
		expect(result.value.budget.cost_consumed).toBe(0);
		expect(result.value.budget.deadline).toBe("2026-11-15T10:30:00.000Z");
		expect(result.value.budget.source_refs[0]).toBe(`tasks/T-01.md#sha256:${"a".repeat(64)}`);
	});

	for (const field of numericFields) {
		for (const value of [
			"-1",
			"+1",
			"1e3",
			"1e309",
			"1/2",
			"NaN",
			"Infinity",
			"9007199254740992",
			"",
			"other `no_progress_count`: 4",
		]) {
			it(`rejects ${field}=${JSON.stringify(value)} without borrowing or truncation`, () => {
				const card = explicitBudget().replace(new RegExp(`^- \`${field}\`:.*$`, "m"), `- \`${field}\`: ${value}`);
				const result = declaredBudget(card);
				expect(result.ok).toBe(false);
			});
		}
		it(`rejects missing ${field} as that field, not another field's value`, () => {
			const without = explicitBudget().replace(new RegExp(`^- \`${field}\`:.*\\n?`, "m"), "");
			const result = declaredBudget(
				field === "cost_consumed"
					? without.replace("`cost_consumed` 与 `steps_consumed` 同单位", "显式成本计量")
					: without,
			);
			expect(result.ok).toBe(false);
			if (!result.ok) expect(result.gaps).toContain(field);
		});
		it(`rejects duplicate ${field}`, () => {
			expect(declaredBudget(`${explicitBudget()}\n- \`${field}\`: 1\n`).ok).toBe(false);
		});
	}

	it.each(["steps_consumed", "no_progress_count", "max_steps"])("rejects fractional integer %s", (field) => {
		const card = explicitBudget().replace(new RegExp(`^- \`${field}\`:.*$`, "m"), `- \`${field}\`: 1.5`);
		expect(declaredBudget(card).ok).toBe(false);
	});
	it.each(["source_refs", "matter_ref", "budget_ref"])("rejects empty %s", (field) => {
		const card = explicitBudget().replace(new RegExp(`^- \`${field}\`:.*$`, "m"), `- \`${field}\`: `);
		const result = declaredBudget(card);
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.gaps).toContain(field);
	});
	it("does not invent step-cost equivalence", () => {
		const card = explicitBudget().replace(/^- `remaining_cost`:.*$/m, "- `remaining_cost`: 20");
		const result = declaredBudget(card);
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.gaps).toContain("cost_unit");
	});
	it.each([
		"2026-02-30T10:00:00Z",
		"2026-13-01T10:00:00Z",
		"nonsense",
		"run.json.started_at + 9007199254740991m",
		"run.json.started_at + -1m",
		"run.json.started_at + 1e3m",
	])("refuses invalid/overflow deadline %s without throwing", (deadline) => {
		const result = declaredBudget(explicitBudget().replace(/^- `deadline`:.*$/m, `- \`deadline\`: \`${deadline}\``));
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.gaps).toContain("deadline");
	});
	it("refuses invalid run start even if Date.parse would normalize it", () => {
		expect(declaredBudget(undefined, "2026-02-30T10:00:00Z").ok).toBe(false);
	});
	it("rejects duplicate budget sections and standalone malformed parent", () => {
		expect(declaredBudget(`${explicitBudget()}\n${budgetBlock.join("\n")}`).ok).toBe(false);
		expect(declaredBudget(`${explicitBudget()}\n- \`parent_matter_ref\`: `).ok).toBe(false);
	});
	it("preflight validates malformed budgets and uses the supplied clock", () => {
		const parsed = declaredBudget();
		expect(parsed.ok).toBe(true);
		if (!parsed.ok) return;
		expect(preflightReservation({ ...parsed.value.budget, deadline: "bad" }).ok).toBe(false);
		expect(preflightReservation({ ...parsed.value.budget, remaining_cost: NaN }).ok).toBe(false);
		expect(preflightReservation(parsed.value.budget, Date.parse("2026-11-15T10:10:00Z")).ok).toBe(true);
	});
});

const registeredMaterial = {
	question: "Choose the bounded implementation action",
	background: {
		task_goal: "authorized task",
		current_state: "transport off",
		tried: "none",
		unknowns: "none",
		constraints: "one pinned authorization unit",
	},
	handling_options: [
		{
			id: "implement",
			label: "Implement",
			description: "Implement within card",
			consequence: "planned only",
			risk: "low",
			conditions: "finite host budget",
		},
		{
			id: "inspect",
			label: "Inspect",
			description: "Read scoped evidence",
			consequence: "planned only",
			risk: "low",
			conditions: "finite host budget",
		},
	],
};
const registeredPreparation = {
	prepared_at: "2026-11-15T10:00:00.000Z",
	basis_catalog: [
		{
			id: "basis",
			text: "Current task evidence",
			material_refs: ["background.current_state"],
			applies_to: ["implement"],
		},
	],
};

interface RegisteredRuntime {
	f: Fixture;
	h: Harness;
	handle: SubmitDecisionHostHandle;
	offer: SubmitOfferMetadata;
	posts: () => number;
	submit: (extra?: Record<string, unknown>) => Promise<Record<string, unknown>>;
}

async function registeredRuntime(
	options: {
		cardTransform?: (card: string) => string;
		grantTransform?: (grant: RuntimeHostAuthorization) => RuntimeHostAuthorization | undefined;
		noAccounting?: boolean;
	} = {},
): Promise<RegisteredRuntime> {
	const f = fixture();
	if (options.cardTransform !== undefined) {
		const card = options.cardTransform(fs.readFileSync(f.cardFile, "utf8"));
		fs.writeFileSync(f.cardFile, card);
		f.authorization.cardSha256 = sha256(card);
	}
	const allowedMatter = decisionMatterRef({
		version: decisionMatterVersion(),
		owner: claim,
		role: "pm",
		key: keyName,
		task_key: null,
		run_id: null,
		claim_id: claim,
		dp: "dp-auto",
		question: null,
		note: null,
		material: registeredMaterial,
		preparation: { basis_catalog: registeredPreparation.basis_catalog },
		context: null,
		task_before: null,
	});
	f.authorization.source = "pm";
	f.authorization.role = "pm";
	f.authorization.matterRef = allowedMatter;
	delete f.authorization.taskKey;
	delete f.authorization.runId;
	let handle: SubmitDecisionHostHandle | undefined;
	let posts = 0;
	const h = await createHarness({
		extensionFactories: [
			(pi) => {
				handle = registerSubmitDecisionHandoffTool(pi, {
					projectDir: f.root,
					// Real default adapter; no hostAdapter and no root override.
					runtimeHost: {
						authorizationFor: (localRef, expected) => {
							if (expected.matter_identity !== allowedMatter) return undefined;
							const grant = { ...f.authorization, localRef };
							return options.grantTransform === undefined ? grant : options.grantTransform(grant);
						},
						budgetSnapshotFor: options.noAccounting ? undefined : f.hooks.budgetSnapshotFor,
					},
				});
				registerAskDecisionTool(pi, {
					projectDir: f.root,
					initiatorRole: "pm",
					taskPath: "",
					submitHandle: handle,
					configReader: () => ({
						transport: "off",
						dpDisabled: false,
						signoffDisabled: false,
						mode: "auto",
						configRefs: [],
					}),
					runner: async () => {
						posts += 1;
						return { status: 0, stdout: "", stderr: "", timedOut: false };
					},
				});
			},
		],
	});
	harnesses.push(h);
	h.setResponses([
		fauxAssistantMessage(
			[
				fauxToolCall(ASK_DECISION_TOOL, {
					dp: "dp-auto",
					trigger: "local-task",
					material: registeredMaterial,
					preparation: registeredPreparation,
				}),
			],
			{ stopReason: "toolUse" },
		),
		fauxAssistantMessage("prepared"),
	]);
	await h.session.prompt("Prepare the scoped decision.");
	const askResult = h.session.messages.find(
		(message) => message.role === "toolResult" && message.toolName === ASK_DECISION_TOOL,
	);
	if (askResult === undefined || askResult.role !== "toolResult") throw new Error("registered ask did not return");
	const offer = (askResult.details as { submit_offer?: SubmitOfferMetadata }).submit_offer;
	expect(offer?.submittable, JSON.stringify(askResult.details)).toBe(true);
	if (offer === undefined || handle === undefined) throw new Error("missing actual host offer/handle");
	const submit = async (extra: Record<string, unknown> = {}) => {
		h.setResponses([
			fauxAssistantMessage(
				[
					fauxToolCall(SUBMIT_DECISION_HANDOFF_TOOL, {
						offer_id: offer.offer_id,
						choice: "implement",
						basis_id: "basis",
						...extra,
					}),
				],
				{ stopReason: "toolUse" },
			),
			fauxAssistantMessage("submitted"),
		]);
		await h.session.prompt("Submit the prepared selection.");
		const result = [...h.session.messages]
			.reverse()
			.find((message) => message.role === "toolResult" && message.toolName === SUBMIT_DECISION_HANDOFF_TOOL);
		if (result === undefined || result.role !== "toolResult") throw new Error("registered submit did not return");
		return result.details as Record<string, unknown>;
	};
	return { f, h, handle, offer, posts: () => posts, submit };
}

function diskSelections(env: RegisteredRuntime): string[] {
	const dir = path.join(env.f.doc, keyName, "evidence", "decision-handoffs");
	return fs.existsSync(dir) ? fs.readdirSync(dir).filter((file) => file.endsWith(".json")) : [];
}

describe("T06-A real registered ask → submit → default adapter → frozen store", () => {
	it("writes a real planned selection on disk with explicit pin despite another same-claim card", async () => {
		const env = await registeredRuntime();
		fs.copyFileSync(env.f.cardFile, path.join(path.dirname(env.f.cardFile), "other-same-claim.md"));
		const result = await env.submit();
		expect(result, JSON.stringify(result)).toMatchObject({
			status: "planned",
			selection_written: true,
			business_completed: false,
			code: "written",
		});
		expect(env.posts()).toBe(0);
		expect(diskSelections(env)).toHaveLength(1);
		const stored = new LocalSelectionStore({ agenticdoc_root: env.f.doc, key: keyName }).readSelection({
			source: "pm",
			ref: env.offer.local_ref!,
		});
		expect(stored.status).toBe("ok");
		expect(stored.record).toMatchObject({
			kind: "local-selection",
			action_state: "planned",
			business_completed: false,
			host_binding: { claim_id: claim, role: "pm" },
		});
		expect(JSON.stringify(stored.record)).not.toContain("decision_id");
		const duplicate = await env.submit();
		expect(duplicate.code).toBe("duplicate");
		expect(diskSelections(env)).toHaveLength(1);
	});

	it.each(["claim", "pin", "card-bytes"])("refuses only %s drift after real ask; zero records", async (drift) => {
		const env = await registeredRuntime();
		if (drift === "claim")
			fs.writeFileSync(
				path.join(env.f.doc, "_index.parallel"),
				`| ${keyName} | active | EXECUTE | foreign:987 | | f | now |\n`,
			);
		if (drift === "pin") env.f.authorization.cardSha256 = "0".repeat(64);
		if (drift === "card-bytes") fs.appendFileSync(env.f.cardFile, "\nbyte drift\n");
		expect(await env.submit()).toMatchObject({ status: "refused", selection_written: false });
		expect(diskSelections(env)).toHaveLength(0);
	});

	it.each([
		["missing pin", (grant: RuntimeHostAuthorization): RuntimeHostAuthorization => ({ ...grant, cardPath: "" })],
		["existing out-of-range card", (grant: RuntimeHostAuthorization) => ({ ...grant, cardPath: "../outside.md" })],
		["missing start", (grant: RuntimeHostAuthorization) => ({ ...grant, budgetStartedAt: "" })],
		["wrong unit", (grant: RuntimeHostAuthorization) => ({ ...grant, authorizationUnit: "other-unit" })],
		["wrong business matter", (grant: RuntimeHostAuthorization) => ({ ...grant, matterRef: "other-matter" })],
		["empty business matter", (grant: RuntimeHostAuthorization) => ({ ...grant, matterRef: "" })],
		["no host authorization", (_grant: RuntimeHostAuthorization): undefined => undefined],
	] as const)("rejects %s with real store refusal", async (_label, transform) => {
		const env = await registeredRuntime({ grantTransform: transform });
		fs.copyFileSync(env.f.cardFile, path.join(env.f.doc, "outside.md"));
		expect(await env.submit()).toMatchObject({ status: "refused", selection_written: false });
		expect(diskSelections(env)).toHaveLength(0);
	});

	it.each([
		["duplicate budget", (card: string) => `${card}\n- \`max_steps\`: 30\n`],
		["duplicate head", (card: string) => card.replace("title: fixture", `owning_pm_claim: ${claim}\ntitle: fixture`)],
		["empty cost source", (card: string) => card.replace(/^- `remaining_cost`:.*$/m, "- `remaining_cost`: 20")],
		["empty sources", (card: string) => card.replace(/^- `source_refs`:.*$/m, "- `source_refs`: ")],
		["empty card matter", (card: string) => card.replace(/^- `matter_ref`:.*$/m, "- `matter_ref`: ``")],
	] as const)("rejects %s in correctly repinned real card", async (_label, transform) => {
		const env = await registeredRuntime({ cardTransform: transform });
		expect(await env.submit()).toMatchObject({ status: "refused", selection_written: false });
		expect(diskSelections(env)).toHaveLength(0);
	});

	it("uses nonzero live history instead of resetting to initial card counters", async () => {
		const env = await registeredRuntime();
		fs.writeFileSync(
			path.join(env.f.root, "host-budget-history.json"),
			JSON.stringify({ steps: 2, cost: 2, noProgress: 1, remaining: 18 }),
		);
		expect(await env.submit()).toMatchObject({ status: "planned", selection_written: true, code: "written" });
		expect(diskSelections(env)).toHaveLength(1);
		const stored = new LocalSelectionStore({ agenticdoc_root: env.f.doc, key: keyName }).readSelection({
			source: "pm",
			ref: env.offer.local_ref!,
		});
		expect(stored.record).toMatchObject({ kind: "local-selection", budget_ref: "tasks/T-01.md#事项预算事实" });
		expect(env.f.observedBudgets.length).toBeGreaterThanOrEqual(2);
		for (const budget of env.f.observedBudgets)
			expect(budget).toMatchObject({
				steps_consumed: 2,
				cost_consumed: 2,
				no_progress_count: 1,
				remaining_cost: 18,
			});
	});

	it("refuses live exhaustion even though the pinned card still declares initial capacity", async () => {
		const env = await registeredRuntime();
		fs.writeFileSync(
			path.join(env.f.root, "host-budget-history.json"),
			JSON.stringify({ steps: 20, cost: 20, noProgress: 1, remaining: 0 }),
		);
		expect(await env.submit()).toMatchObject({ status: "refused", selection_written: false });
		expect(diskSelections(env)).toHaveLength(0);
	});

	it("refuses a registered submit through a same-byte directory redirect", async () => {
		const env = await registeredRuntime();
		const tasks = path.dirname(env.f.cardFile);
		const real = path.join(env.f.root, "redirected-tasks");
		fs.renameSync(tasks, real);
		fs.symlinkSync(real, tasks, process.platform === "win32" ? "junction" : "dir");
		expect(await env.submit()).toMatchObject({
			status: "refused",
			selection_written: false,
			code: "trusted-context-refused",
		});
		expect(diskSelections(env)).toHaveLength(0);
	});

	it("refuses static card-only counters without live accounting history", async () => {
		const env = await registeredRuntime({ noAccounting: true });
		expect(await env.submit()).toMatchObject({ status: "refused", selection_written: false });
		expect(diskSelections(env)).toHaveLength(0);
	});

	it("cannot supply a pin via model three-parameter submit", async () => {
		const env = await registeredRuntime({ grantTransform: () => undefined });
		const result = await env.submit({ card_path: "tasks/T-01.md", card_sha256: env.f.authorization.cardSha256 });
		expect(JSON.stringify(result)).not.toContain('"status":"planned"');
		expect(diskSelections(env)).toHaveLength(0);
	});
});

describe("T06-A worker host identity, pin bytes and redirect regressions", () => {
	it("does not adopt a new index PM claim while the pinned card still names its old owner", async () => {
		const f = fixture();
		fs.writeFileSync(
			path.join(f.doc, "_index.parallel"),
			`| ${keyName} | active | EXECUTE | next-owner:88 | | f | now |\n`,
		);
		expect(await f.returns.adapter.readTrustedContext(request(f.returns.run))).toBeUndefined();
		// Stop-only caller has no independent submit grant, but MUST still compare
		// the card PM owner, rather than accepting the new row as self.
		const facts = readRuntimeStopFacts({
			agenticdocRoot: f.doc,
			key: keyName,
			taskKey,
			runId: String(f.returns.run.run_id),
		});
		expect(facts.gaps).toContain("card.owning_pm_claim");
	});

	it("strict authority rejects a malformed foreign row and active+idle duplicate target", async () => {
		for (const extra of ["broken | legacy | row", `| ${keyName} | idle | EXECUTE | ${claim} | | f | now |`]) {
			const f = fixture();
			fs.appendFileSync(path.join(f.doc, "_index.parallel"), `${extra}\n`);
			expect(await f.returns.adapter.readTrustedContext(request(f.returns.run))).toBeUndefined();
		}
	});

	it.each(["task_key", "run_id", "owner_key", "kind"])("rejects independent host/run %s drift", async (field) => {
		const f = fixture();
		fs.writeFileSync(path.join(f.dir, "run.json"), JSON.stringify({ ...f.returns.run, [field]: "other" }));
		expect(await f.returns.adapter.readTrustedContext(request(f.returns.run))).toBeUndefined();
	});

	it("missing run owner produces a structured stop gap rather than throwing", () => {
		const f = fixture();
		const run = { ...f.returns.run };
		delete run.owner_key;
		fs.writeFileSync(path.join(f.dir, "run.json"), JSON.stringify(run));
		const facts = readRuntimeStopFacts({
			agenticdocRoot: f.doc,
			key: keyName,
			taskKey,
			runId: String(f.returns.run.run_id),
		});
		expect(facts.gaps).toContain("run.owner_key");
	});

	it.each(["card_path", "card_sha256"])("rejects duplicate %s in the dispatched envelope", async (field) => {
		const f = fixture();
		const value = field === "card_path" ? "tasks/T-01.md" : f.authorization.cardSha256;
		fs.appendFileSync(path.join(f.dir, "task.md"), `${field}: ${value}\n`);
		expect(await f.returns.adapter.readTrustedContext(request(f.returns.run))).toBeUndefined();
	});

	it("hashes the original Buffer, including invalid UTF-8 bytes, not decoded/re-encoded text", async () => {
		const f = fixture();
		const bytes = Buffer.concat([Buffer.from([35, 32, 255, 10]), fs.readFileSync(f.cardFile)]);
		fs.writeFileSync(f.cardFile, bytes);
		f.authorization.cardSha256 = crypto.createHash("sha256").update(bytes).digest("hex");
		fs.writeFileSync(
			path.join(f.dir, "task.md"),
			`type: coding\ncard_path: tasks/T-01.md\ncard_sha256: ${f.authorization.cardSha256}\n\nbody\n`,
		);
		expect(f.authorization.cardSha256).not.toBe(sha256(bytes.toString("utf8")));
		const trusted = await f.returns.adapter.readTrustedContext(request(f.returns.run));
		expect(trusted).toBeDefined();
	});

	it("rejects a card-directory junction even when the linked card has exact pinned bytes", async () => {
		const f = fixture();
		const tasks = path.dirname(f.cardFile);
		const real = path.join(f.root, "redirected-tasks");
		fs.renameSync(tasks, real);
		fs.symlinkSync(real, tasks, process.platform === "win32" ? "junction" : "dir");
		expect(fs.readFileSync(f.cardFile).equals(fs.readFileSync(path.join(real, "T-01.md")))).toBe(true);
		expect(await f.returns.adapter.readTrustedContext(request(f.returns.run))).toBeUndefined();
	});

	it("rejects a project-internal target junction, not just an escaping target", () => {
		const f = fixture();
		const real = path.join(f.root, "real-targets");
		fs.mkdirSync(real);
		fs.writeFileSync(path.join(real, "product.txt"), "real bytes\n");
		const linked = path.join(f.root, "linked-targets");
		fs.symlinkSync(real, linked, process.platform === "win32" ? "junction" : "dir");
		expect(targetFileDigest(f.root, "real-targets/product.txt").ok).toBe(true);
		expect(targetFileDigest(f.root, "linked-targets/product.txt").ok).toBe(false);
	});

	it("refuses a shape-only fake execution even with existing bytes and exact digest", async () => {
		const f = fixture();
		fs.writeFileSync(path.join(f.root, "product.txt"), "real bytes\n");
		const digest = crypto.createHash("sha256").update("real bytes\n").digest("hex");
		const proof = await f.returns.adapter.verifyExecution?.({
			key: keyName,
			source: "worker-local",
			local_ref: "local-ref-1",
			action_ref: "invented-call-999",
			result_ref: "product.txt",
			executor: "invented-run#invented-call-999",
			observed_effect: `sha256:${digest}`,
			expected_target_digest: digest,
			binding: {
				role: "coding",
				owner: claim,
				claim_id: claim,
				key: keyName,
				task_key: taskKey,
				run_id: String(f.returns.run.run_id),
				binding_version: "v1",
				observed_at: new Date().toISOString(),
			},
		});
		expect(proof).toBeUndefined();
	});

	it("refuses a host snapshot that exceeds the pinned card ceiling", async () => {
		const f = fixture();
		const config: RuntimeHostAdapterConfig = {
			agenticdocRoot: f.doc,
			...f.hooks,
			expectedFor: () => f.returns.expected,
			budgetSnapshotFor: (input) => {
				const snapshot = f.hooks.budgetSnapshotFor?.(input);
				if (snapshot === undefined || !snapshot.ok) throw new Error("fixture snapshot unavailable");
				snapshot.value.budget.max_steps += 1;
				return snapshot;
			},
		};
		expect(await createRuntimeHostAdapter(config).readTrustedContext(request(f.returns.run))).toBeUndefined();
	});
});

describe("T06-A pinned budget and host-snapshot consistency", () => {
	it.each(["21 cost unit ≡ 1 tool call", "-1 cost unit ≡ 1 tool call", "1 cost unit ≡ 10 tool call"])(
		"refuses non-equivalence unit %s",
		(contract) => {
			const result = declaredBudget(explicitBudget().replace("1 cost unit ≡ 1 tool call", contract));
			expect(result.ok).toBe(false);
			if (!result.ok) expect(result.gaps).toContain("cost_unit");
		},
	);

	it("refuses a budget_ref naming a different card even with valid own raw SHA", () => {
		const result = declaredBudget(
			explicitBudget().replace("tasks/T-01.md#事项预算事实", "tasks/other.md#事项预算事实"),
		);
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.gaps).toContain("budget_ref");
	});

	it("accepts a valid absolute ISO deadline and refuses invalid/unsafe clocks", () => {
		const result = declaredBudget(explicitBudget().replace("run.json.started_at + 30m", "2026-11-15T11:00:00Z"));
		expect(result.ok).toBe(true);
		if (!result.ok) return;
		expect(result.value.budget.deadline).toBe("2026-11-15T11:00:00Z");
		expect(preflightReservation(result.value.budget, NaN).ok).toBe(false);
		expect(preflightReservation(result.value.budget, Infinity).ok).toBe(false);
	});

	it("does not accept divergent explicit cost and step counters under unit equivalence", () => {
		const result = declaredBudget(explicitBudget().replace("- `cost_consumed`: 0", "- `cost_consumed`: 1"));
		expect(result.ok).toBe(false);
		if (!result.ok) expect(result.gaps).toContain("cost_consumed");
	});

	it.each(["replenished-cost", "zero-reservation", "wrong-remaining", "lost-card-provenance", "unreadable-history"])(
		"refuses live host %s instead of silently authorizing",
		async (failure) => {
			const f = fixture();
			const adapter = createRuntimeHostAdapter({
				agenticdocRoot: f.doc,
				...f.hooks,
				expectedFor: () => f.returns.expected,
				budgetSnapshotFor: (input) => {
					if (failure === "unreadable-history") throw new Error("host history unreadable");
					const snapshot = f.hooks.budgetSnapshotFor?.(input);
					if (snapshot === undefined || !snapshot.ok) throw new Error("fixture snapshot unavailable");
					if (failure === "replenished-cost") snapshot.value.budget.cost_consumed = 1;
					if (failure === "lost-card-provenance")
						snapshot.value.budget.source_refs = [snapshot.value.observationRef];
					if (failure === "zero-reservation")
						snapshot.value.preflight = {
							granted: true,
							reserved_steps: 0,
							reserved_cost: 0,
							remaining_after_steps: input.cardBudget.max_steps,
							remaining_after_cost: input.cardBudget.remaining_cost,
							reason: "granted",
						};
					if (failure === "wrong-remaining")
						snapshot.value.preflight = {
							granted: true,
							reserved_steps: 1,
							reserved_cost: 1,
							remaining_after_steps: input.cardBudget.max_steps,
							remaining_after_cost: input.cardBudget.remaining_cost,
							reason: "granted",
						};
					return snapshot;
				},
			});
			expect(await adapter.readTrustedContext(request(f.returns.run))).toBeUndefined();
		},
	);

	it("refuses a raw empty matter from a registered host prepare handle before making a new offer", async () => {
		const env = await registeredRuntime();
		const identity = { key: keyName, source: "pm" as const, role: "pm" as const, claimId: claim };
		const result = env.handle.prepareOffer({
			dp: "dp-auto",
			identity,
			material: registeredMaterial,
			preparation: registeredPreparation,
			matterRef: "  ",
			feedbackEffectUnknown: false,
			revalidate: () => ({ identity, trustedStop: false, configSignature: "config", hostSignature: "host" }),
		});
		expect(result).toMatchObject({ prepared: false, metadata: { submittable: false, gaps: ["matter_ref"] } });
		expect(diskSelections(env)).toHaveLength(0);
	});

	it("refuses policy-source exceptions without breaking independent decision preparation", async () => {
		const env = await registeredRuntime({
			grantTransform: () => {
				throw new Error("host authorization registry unreadable");
			},
		});
		expect(await env.submit()).toMatchObject({
			status: "refused",
			selection_written: false,
			code: "trusted-context-refused",
		});
		expect(diskSelections(env)).toHaveLength(0);
	});
});

// T06-I: the generated dispatch `card_sha256` is the frozen EOL-normalized SHA
// over RAW card bytes (shared/card-digest.ts). The A terminal defect hashed the
// raw Buffer directly, so every legal CRLF dispatch card (e.g. the real source
// card: 86 CRLF pairs, raw 9bd60d5d..., normalized 5ee8f669... = its task.md pin)
// was refused. These regressions pin the frozen recipe on real bytes.
describe("T06-I frozen CRLF-normalized dispatch card pin", () => {
	function rawSha(buf: Buffer): string {
		return crypto.createHash("sha256").update(buf).digest("hex");
	}

	function pinFixture(cardBytes: Buffer, pin: string) {
		const root = fs.mkdtempSync(path.join(os.tmpdir(), "t06-pin-"));
		roots.push(root);
		const doc = path.join(root, ".agenticdoc");
		const dir = path.join(doc, keyName, "workers", taskKey);
		fs.mkdirSync(path.join(doc, keyName, "tasks"), { recursive: true });
		fs.mkdirSync(dir, { recursive: true });
		fs.writeFileSync(
			path.join(doc, "_index.parallel"),
			`# Index Parallel\n| ${keyName} | active | EXECUTE | ${claim} | | fixture | now |\n`,
		);
		const startedAt = new Date(Date.now() - 60_000).toISOString();
		const runId = `${taskKey}@${startedAt}`;
		fs.writeFileSync(
			path.join(dir, "run.json"),
			JSON.stringify({
				schema: 1,
				task_key: taskKey,
				run_id: runId,
				owner_key: keyName,
				kind: "coding",
				status: "running",
				started_at: startedAt,
				artifacts: [],
			}),
		);
		fs.writeFileSync(path.join(doc, keyName, "tasks", "T-01.md"), cardBytes);
		fs.writeFileSync(
			path.join(dir, "task.md"),
			`type: coding\ncard_path: tasks/T-01.md\ncard_sha256: ${pin}\n\nbody\n`,
		);
		return {
			read: () => readRuntimeStopFacts({ agenticdocRoot: doc, key: keyName, taskKey, runId, clockMs: Date.now() }),
		};
	}

	/** Real titled card with a valid budget block, in LF and CRLF byte form. */
	function crlfCard(): { lf: Buffer; crlf: Buffer; pin: string } {
		const text = `owning_pm_claim: ${claim}\n\n${budgetBlock.join("\n")}`;
		const lf = Buffer.from(text, "utf8");
		const crlf = Buffer.from(text.replace(/\n/g, "\r\n"), "utf8");
		return { lf, crlf, pin: sha256EolNormalizedBytes(crlf) };
	}

	it("accepts a CRLF real dispatch card whose generated pin is the frozen normalized SHA", () => {
		const { crlf, pin } = crlfCard();
		// The raw-Buffer SHA is a DIFFERENT value; hashing it against the generated
		// normalized pin is exactly the A:481-482 defect the fix removes.
		expect(rawSha(crlf)).not.toBe(pin);
		expect(sha256EolNormalizedBytes(crlf)).toBe(pin);
		expect(pinFixture(crlf, pin).read().gaps).toEqual([]);
	});

	it("does not drift between CRLF and LF renderings of one card", () => {
		const { lf, crlf, pin } = crlfCard();
		expect(sha256EolNormalizedBytes(lf)).toBe(pin);
		expect(sha256EolNormalizedBytes(crlf)).toBe(pin);
		expect(pinFixture(crlf, pin).read().gaps).toEqual([]);
		expect(pinFixture(lf, pin).read().gaps).toEqual([]);
	});

	it("rejects an equal-length content substitution under the original pin", () => {
		const { crlf, pin } = crlfCard();
		const drifted = Buffer.from(crlf);
		const at = drifted.indexOf(Buffer.from("max_steps"));
		expect(at).toBeGreaterThan(0);
		drifted[at] = drifted[at] === 0x6d ? 0x6e : 0x6d; // m <-> n, same length
		expect(drifted.length).toBe(crlf.length);
		expect(rawSha(drifted)).not.toBe(rawSha(crlf));
		expect(pinFixture(drifted, pin).read().gaps).toContain("card_sha256");
	});

	it("preserves invalidUTF8 raw bytes instead of decode/re-encode hashing", () => {
		const { crlf } = crlfCard();
		// Invalid byte sits in a top comment line (ignored by parseHead/budgetBlockOf).
		const withBad = Buffer.concat([Buffer.from("# title "), Buffer.from([0xff]), Buffer.from("\r\n"), crlf]);
		const badPin = sha256EolNormalizedBytes(withBad);
		const decoded = Buffer.from(withBad.toString("utf8"), "utf8");
		// A lossy decode/re-encode would replace 0xFF with U+FFFD and change the SHA;
		// the frozen recipe keeps raw bytes, so the raw-byte pin is the only legal one.
		expect(sha256EolNormalizedBytes(decoded)).not.toBe(badPin);
		expect(pinFixture(withBad, badPin).read().gaps).toEqual([]);
		expect(pinFixture(withBad, sha256EolNormalizedBytes(decoded)).read().gaps).toContain("card_sha256");
	});

	it("records a distinct raw preservation SHA and never mixes it with the generated pin", () => {
		const { crlf, pin } = crlfCard();
		const preservationSha = rawSha(crlf);
		expect(preservationSha).not.toBe(pin);
		expect(pinFixture(crlf, preservationSha).read().gaps).toContain("card_sha256");
	});
});

// ── T06-J3 append-only: finite adversarial identity/ref JOIN matrix ──────
// LAYER (labelled honestly): the production createRuntimeHostAdapter(...)
// .readTrustedContext join guard (A:724-778), executed directly through its
// public config/request seams. Hooks wrap the REAL fixture registrations: the
// exact-ref expectedFor projection, an authorizationFor that keeps the genuine
// card pin / budget start / authorization unit / owning claim, and the REAL
// f.hooks.budgetSnapshotFor (host-budget-history.json). readRuntimeAuthority
// still reads real index/card/budget files. This is the ADAPTER JOIN layer,
// NOT the translated composition finishing path; readTrustedContext is a READ,
// so "no foreign write" here means no selection/execution/disposition bytes
// appeared at this layer (captured physically before/after). No private map,
// no method injection, no permissive trusted-hook override, no fake proof.

/** Physical .json bytes under the control doc, keyed by relative path. */
function j3JsonState(doc: string): Record<string, string> {
	const out: Record<string, string> = {};
	const walk = (dir: string): void => {
		if (!fs.existsSync(dir)) return;
		for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
			const full = path.join(dir, e.name);
			if (e.isDirectory()) walk(full);
			else if (e.name.endsWith(".json"))
				out[path.relative(doc, full)] = crypto.createHash("sha256").update(fs.readFileSync(full)).digest("hex");
		}
	};
	walk(doc);
	return out;
}

type J3Req = { key: string; source: "pm" | "worker-local"; ref: string; task_key?: string; run_id?: string };

function j3PmAdapter(f: Fixture, mutateExpected?: (e: RuntimeOfferExpected) => void) {
	const runId = String(f.returns.run.run_id);
	const expected: RuntimeOfferExpected = {
		...f.returns.expected,
		identity: { key: keyName, source: "pm", role: "pm", claimId: claim, owner: keyName, taskKey, runId },
	};
	if (mutateExpected !== undefined) mutateExpected(expected);
	const base: RuntimeHostAuthorization = { ...f.authorization, source: "pm", role: "pm", taskKey, runId };
	const adapter = createRuntimeHostAdapter({
		agenticdocRoot: f.doc,
		// exact-ref resolution like production; wraps the real projected offer
		expectedFor: (ref) => (ref === "local-ref-1" ? structuredClone(expected) : undefined),
		// genuine host registration hook: binds ONLY to the exact offer ref and
		// keeps the real pin/start/unit/claim; never a permissive grant.
		authorizationFor: (localRef) => ({ ...structuredClone(base), localRef }),
		// REAL callback preserved verbatim.
		budgetSnapshotFor: f.hooks.budgetSnapshotFor,
	});
	return { doc: f.doc, adapter };
}

async function j3Read(env: { doc: string; adapter: ReturnType<typeof createRuntimeHostAdapter> }, req: J3Req) {
	const before = j3JsonState(env.doc);
	const trusted = await env.adapter.readTrustedContext(req);
	const after = j3JsonState(env.doc);
	return { trusted, noWrite: JSON.stringify(after) === JSON.stringify(before) };
}

const j3PmBase: J3Req = { key: keyName, source: "pm", ref: "local-ref-1" };

describe("T06-J3 adversarial PM task/run identity join (isolated adapter layer)", () => {
	it("POSITIVE omitted PM task/run: trusted context resolves from the exact registered offer identity", async () => {
		const env = j3PmAdapter(fixture());
		const { trusted, noWrite } = await j3Read(env, { ...j3PmBase });
		expect(trusted).toBeDefined();
		expect(trusted?.self_claim_id).toBe(claim);
		expect(noWrite).toBe(true); // read layer wrote no selection/execution/disposition
	});

	it("POSITIVE exact PM task/run: supplied trusted values are accepted", async () => {
		const f = fixture();
		const env = j3PmAdapter(f);
		const { trusted, noWrite } = await j3Read(env, {
			...j3PmBase,
			task_key: taskKey,
			run_id: String(f.returns.run.run_id),
		});
		expect(trusted).toBeDefined();
		expect(trusted?.self_claim_id).toBe(claim);
		expect(noWrite).toBe(true);
	});

	it("NEGATIVE supplied foreign PM task_key: refused at pmTaskJoinOk; no write", async () => {
		const env = j3PmAdapter(fixture());
		const { trusted, noWrite } = await j3Read(env, { ...j3PmBase, task_key: "foreign-task", run_id: undefined });
		expect(trusted).toBeUndefined();
		expect(noWrite).toBe(true);
	});

	it("NEGATIVE supplied foreign PM run_id: refused at pmTaskJoinOk; no write", async () => {
		const env = j3PmAdapter(fixture());
		const { trusted, noWrite } = await j3Read(env, { ...j3PmBase, task_key: undefined, run_id: "foreign-run" });
		expect(trusted).toBeUndefined();
		expect(noWrite).toBe(true);
	});

	it("NEGATIVE wrong key: refused at identity.key join guard; no write", async () => {
		const env = j3PmAdapter(fixture());
		const { trusted, noWrite } = await j3Read(env, { ...j3PmBase, key: "foreign-key" });
		expect(trusted).toBeUndefined();
		expect(noWrite).toBe(true);
	});

	it("NEGATIVE wrong source: refused at identity.source join guard; no write", async () => {
		const env = j3PmAdapter(fixture());
		const { trusted, noWrite } = await j3Read(env, {
			...j3PmBase,
			source: "worker-local",
			task_key: taskKey,
			run_id: "x",
		});
		expect(trusted).toBeUndefined();
		expect(noWrite).toBe(true);
	});

	it("NEGATIVE wrong PM claim: refused at claimId vs owningPmClaim guard; no write", async () => {
		const env = j3PmAdapter(fixture(), (e) => {
			if (e.identity) e.identity.claimId = "foreign-claim";
		});
		const { trusted, noWrite } = await j3Read(env, { ...j3PmBase });
		expect(trusted).toBeUndefined();
		expect(noWrite).toBe(true);
	});

	it("NEGATIVE foreign ref: expectedFor resolves no offer; no write", async () => {
		const env = j3PmAdapter(fixture());
		const { trusted, noWrite } = await j3Read(env, { ...j3PmBase, ref: "foreign-ref" });
		expect(trusted).toBeUndefined();
		expect(noWrite).toBe(true);
	});

	it("NEGATIVE worker-local strict join: foreign run_id and omitted run_id both refused; no write", async () => {
		const f = fixture();
		const env = { doc: f.doc, adapter: f.returns.adapter };
		const runId = String(f.returns.run.run_id);
		const exact = await j3Read(env, {
			key: keyName,
			source: "worker-local",
			ref: "local-ref-1",
			task_key: taskKey,
			run_id: runId,
		});
		expect(exact.trusted).toBeDefined(); // worker-local positive control (strict equality)
		const foreignRun = await j3Read(env, {
			key: keyName,
			source: "worker-local",
			ref: "local-ref-1",
			task_key: taskKey,
			run_id: "other-run",
		});
		expect(foreignRun.trusted).toBeUndefined();
		expect(foreignRun.noWrite).toBe(true);
		const omittedRun = await j3Read(env, {
			key: keyName,
			source: "worker-local",
			ref: "local-ref-1",
			task_key: taskKey,
		});
		expect(omittedRun.trusted).toBeUndefined();
		expect(omittedRun.noWrite).toBe(true);
	});

	it("DEFAULT-STORE write-layer refusal: a foreign task in the registered grant writes zero selections", async () => {
		// Real registeredRuntime ask->submit->default adapter->frozen store. The
		// grantTransform injects a foreign taskKey into the host registration; the
		// frozen originalVerdict/join refuses before any selection is written.
		const env = await registeredRuntime({ grantTransform: (g) => ({ ...g, taskKey: "foreign-task" }) });
		const result = await env.submit();
		expect(result).toMatchObject({ status: "refused", selection_written: false });
		expect(diskSelections(env)).toHaveLength(0);
	});
});
