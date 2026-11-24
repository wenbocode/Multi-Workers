/** T-11 mw-window-claim-isolation / VC-005.
 *
 * Independent, fully offline regression at the REAL registered ask/receipt
 * execute boundary. Every case uses the suite's faux-provider harness, an
 * isolated temporary project (authority index, projection, per-key pm-state,
 * .mw config and local MW_PY sentinel) and injected fake decide/lifecycle/sign
 * runners. No real provider, service, model, production index, claim mutation,
 * decision write or sign-off is used.
 *
 * The ONLY mocked production surface is `node:child_process.spawn`, which
 * counts/forbids an external child. The identity predicate under test
 * (`boundKey` -> `inspectPmClaim` -> `currentClaimId` -> `_index.parallel`) is
 * never mocked, replaced or bypassed.
 */
import type * as childProcess from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { AgentMessage } from "@earendil-works/pi-agent-core";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	ASK_DECISION_BLOCKED_ACTION,
	ASK_DECISION_REASON_INPUT_INCOMPLETE,
	ASK_DECISION_TOOL,
	DECISION_RECEIPT_PARAMETERS,
	DECISION_RECEIPT_TOOL,
	type DecideRunner,
	type DecideRunRequest,
	type LifecycleRequest,
	type LifecycleRunner,
	type RawDecideResult,
	registerAskDecisionTool,
	type SignRequest,
	type SignRunner,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import { windowClaimId } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import { readIndexMdActiveKeys } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { agenticdocRoot } from "../../src/extensions/agent-team-loop/shared/paths.ts";
import { createHarness, getMessageText, type Harness } from "./harness.ts";

const { spawnCalls } = vi.hoisted(() => ({ spawnCalls: [] as string[][] }));

/** Count and forbid every external child at the module boundary. `spawnSync`
 * stays the real implementation; only `spawnWithTimeout`'s `spawn` import is
 * intercepted. This is a spawn assertion, not a mock of any identity check. */
vi.mock("node:child_process", async (importOriginal) => {
	const actual = (await importOriginal()) as typeof childProcess;
	const forbiddenSpawn = ((command: string, args: readonly string[] = []) => {
		spawnCalls.push([command, ...args]);
		throw new Error(`unexpected external spawn: ${command}`);
	}) as unknown as typeof actual.spawn;
	return { ...actual, spawn: forbiddenSpawn };
});

const SELF_KEY = "mw-window-own";
const FOREIGN_KEY = "mw-window-foreign";
const IDLE_KEY = "mw-window-idle";
const FORGED_KEY = "mw-window-forged";
const DUP_KEY = "mw-window-duplicate";
const SELF_CLAIM = windowClaimId();
const FOREIGN_CLAIM = `other-host:${process.pid + 4242}`;
const FORGED_CLAIM = `${os.hostname()}:${process.pid + 1}`;

type RowStatus = "active" | "idle" | "done";

interface Row {
	key: string;
	status: RowStatus;
	claimId: string;
	desc?: string;
}

interface Project {
	root: string;
	agenticdoc: string;
	indexFile: string;
	indexMd: string;
	spawnMarker: string;
}

interface Counts {
	decide: number;
	lifecycle: number;
	sign: number;
	spawn: number;
}

interface ClaimDiagnosis {
	reason: string;
	message: string;
	recovery: string;
}

interface AskPayload {
	available: boolean;
	unavailable?: string;
	action?: string;
	decision_id?: string;
	matter_suppressed?: true;
	claim_diagnosis?: ClaimDiagnosis;
	missing_fields?: string[];
}

interface ReceiptDetails {
	decision_id?: string;
	dp?: string | null;
	stage?: string;
	status?: string;
	unavailable?: string;
	claim_diagnosis?: ClaimDiagnosis;
}

interface AskDetails {
	decision_id?: string;
	matter_suppressed?: true;
	decision_feedback?: {
		matter_ref?: string;
		binding?: { key?: string };
	};
}

interface EnvelopeMeta {
	logical_id: string;
	key: string;
	task_key: string | null;
	initiator_role: string;
	record_version: number;
	retry_of: string | null;
}

interface FakeRunners {
	decide: DecideRunner;
	lifecycle: LifecycleRunner;
	sign: SignRunner;
	decideCalls: DecideRunRequest[];
	lifecycleCalls: LifecycleRequest[];
	signCalls: SignRequest[];
}

interface LegalDecision {
	decisionId: string;
	logicalId: string;
	key: string;
}

interface MatrixCase {
	name: string;
	askRows: readonly Row[];
	askKey: string;
	reason: string;
	receiptRows: readonly Row[];
	askProjection?: string;
	receiptProjection?: string;
	projectionCheck?: "scalar" | "array";
	prepare?: (project: Project) => void;
}

const tempDirs: string[] = [];
const harnesses: Harness[] = [];
const projects: Project[] = [];
let callCounter = 0;
const savedEnv = new Map<string, string | undefined>();
const ENV_NAMES = [
	"HOME",
	"USERPROFILE",
	"PI_CODING_AGENT_DIR",
	"PI_WORKER_TASK",
	"MW_PY",
	"MW_STUB_SEEN",
	"MW_T11_SPAWN_SENTINEL",
] as const;

const ownActive: Row = { key: SELF_KEY, status: "active", claimId: SELF_CLAIM };
const foreignActive: Row = { key: FOREIGN_KEY, status: "active", claimId: FOREIGN_CLAIM };
const idleOwn: Row = { key: IDLE_KEY, status: "idle", claimId: SELF_CLAIM };
const dupSelfFirst: Row = { key: DUP_KEY, status: "active", claimId: SELF_CLAIM };
const dupForeignSecond: Row = { key: DUP_KEY.toUpperCase(), status: "active", claimId: FOREIGN_CLAIM };
const dupForeignFirst: Row = { key: DUP_KEY.toUpperCase(), status: "active", claimId: FOREIGN_CLAIM };
const dupSelfSecond: Row = { key: DUP_KEY, status: "active", claimId: SELF_CLAIM };

function mkTemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

function renderRow(row: Row): string {
	return `| ${row.key} | ${row.status} | EXECUTE | ${row.claimId} | — | ${row.desc ?? "fixture"} | 2026-11-12T00:00:00.000Z |`;
}

function activeKeyProjection(rows: readonly Row[]): string[] {
	const seen = new Set<string>();
	const keys: string[] = [];
	for (const row of rows) {
		if (row.status !== "active") continue;
		const normalized = row.key.trim().toLowerCase();
		if (seen.has(normalized)) continue;
		seen.add(normalized);
		keys.push(row.key);
	}
	return keys;
}

function renderProjection(keys: readonly string[]): string {
	return `# AgenticTask Index\n\nactive_keys: [${keys.map((key) => JSON.stringify(key)).join(", ")}]\n`;
}

function writePmState(project: Project, key: string, claimId: string): void {
	const keyDir = path.join(project.agenticdoc, key);
	fs.mkdirSync(keyDir, { recursive: true });
	fs.writeFileSync(
		path.join(keyDir, "pm-state.md"),
		`# PM State: ${key} (isolated fixture)\n- Phase: EXECUTE\n- Claim-Id: ${claimId}\n`,
		"utf8",
	);
}

function setAuthority(project: Project, rows: readonly Row[], projectionText?: string): void {
	const text = rows.length === 0 ? "" : `${rows.map(renderRow).join("\n")}\n`;
	fs.writeFileSync(project.indexFile, text, "utf8");
	fs.writeFileSync(project.indexMd, projectionText ?? renderProjection(activeKeyProjection(rows)), "utf8");
}

function newProject(): Project {
	const root = mkTemp("mw-t11-decision-");
	const agenticdoc = agenticdocRoot(root);
	const mwDir = path.join(root, ".mw");
	fs.mkdirSync(agenticdoc, { recursive: true });
	fs.mkdirSync(mwDir, { recursive: true });
	fs.writeFileSync(path.join(mwDir, "decide.json"), `${JSON.stringify({ enabled: true })}\n`, "utf8");
	const stubPath = path.join(mwDir, "spawn_sentinel.py");
	fs.writeFileSync(
		stubPath,
		[
			"import os, pathlib, sys",
			"marker = os.environ.get('MW_T11_SPAWN_SENTINEL')",
			"if marker:",
			"    pathlib.Path(marker).write_text(' '.join(sys.argv[1:]), encoding='utf-8')",
			"sys.exit(99)",
		].join("\n"),
		"utf8",
	);
	process.env.MW_PY = stubPath;
	const spawnMarker = path.join(mwDir, "SPAWNED");
	process.env.MW_T11_SPAWN_SENTINEL = spawnMarker;
	const project: Project = {
		root,
		agenticdoc,
		indexFile: path.join(agenticdoc, "_index.parallel"),
		indexMd: path.join(agenticdoc, "_index.md"),
		spawnMarker,
	};
	for (const key of [SELF_KEY, FOREIGN_KEY, IDLE_KEY, FORGED_KEY, DUP_KEY]) {
		writePmState(project, key, key === FOREIGN_KEY ? FOREIGN_CLAIM : SELF_CLAIM);
	}
	setAuthority(project, [ownActive, foreignActive]);
	projects.push(project);
	return project;
}

function dpAutoMaterial(): Record<string, unknown> {
	return {
		question: "Which offline action should the owning PM take?",
		background: {
			task_goal: "Prove the multi-active ask/receipt identity contract",
			current_state: "Temporary authoritative index and injected runner are ready",
			tried: "Read the frozen spec, design and real decision tool path",
			unknowns: "none for this offline fixture",
			constraints: "No real service, no model, no production index, no runtime change",
		},
		handling_options: [
			{
				id: "c1",
				label: "continue",
				description: "Continue the isolated fixture work",
				consequence: "keeps the fixture scope",
				risk: "documented",
				conditions: "inside the existing authorization",
			},
			{
				id: "c2",
				label: "report",
				description: "Report the observed identity verdict",
				consequence: "records the evidence",
				risk: "documented",
				conditions: "inside the existing authorization",
			},
		],
	};
}

function dpAutoPreparation(): Record<string, unknown> {
	return {
		prepared_at: "2026-11-12T06:00:00Z",
		basis_catalog: [
			{
				id: "reason",
				text: "The authoritative index and runner boundary are the prepared basis",
				material_refs: ["question"],
				applies_to: ["c1", "c2"],
			},
		],
	};
}

function askParams(key?: string): Record<string, unknown> {
	return {
		dp: "dp-auto",
		trigger: "t11-check",
		material: dpAutoMaterial(),
		preparation: dpAutoPreparation(),
		...(key === undefined ? {} : { key }),
	};
}

function fakeRunners(): FakeRunners {
	const decideCalls: DecideRunRequest[] = [];
	const lifecycleCalls: LifecycleRequest[] = [];
	const signCalls: SignRequest[] = [];
	const decide: DecideRunner = async (request) => {
		decideCalls.push(request);
		const envelope = JSON.parse(request.input) as {
			meta: EnvelopeMeta;
			preparation: { basis_catalog: Array<{ id: string }> };
		};
		const raw: RawDecideResult = {
			status: 0,
			stdout: JSON.stringify({
				available: true,
				file_evidence: [],
				mode: "auto",
				acted: false,
				confidence_source: "api",
				latency_ms: 5,
				decision_id: `dp-auto:${envelope.meta.logical_id}`,
				answers: {
					handling: { value: "c2", confidence: 0.9 },
					basis_id: { value: envelope.preparation.basis_catalog[0]?.id ?? "reason" },
				},
			}),
			stderr: "",
			timedOut: false,
		};
		return raw;
	};
	const lifecycle: LifecycleRunner = async (request) => {
		lifecycleCalls.push(request);
		const envelope = JSON.parse(request.input) as { stage?: string };
		const raw: RawDecideResult = {
			status: 0,
			stdout: JSON.stringify({
				stage: envelope.stage ?? "consumed",
				status: "written",
				recorded: true,
				duplicate: false,
			}),
			stderr: "",
			timedOut: false,
		};
		return raw;
	};
	const sign: SignRunner = async (request) => {
		signCalls.push(request);
		const raw: RawDecideResult = { status: 0, stdout: "{}", stderr: "", timedOut: false };
		return raw;
	};
	return { decide, lifecycle, sign, decideCalls, lifecycleCalls, signCalls };
}

async function harnessFor(project: Project, runners: FakeRunners): Promise<Harness> {
	const harness = await createHarness({
		extensionFactories: [
			(pi) => {
				registerAskDecisionTool(pi, {
					projectDir: project.root,
					// Empty string suppresses PI_WORKER_TASK; this is the PM branch,
					// with no registration-time key shortcut.
					taskPath: "",
					initiatorRole: "pm",
					runner: runners.decide,
					lifecycleRunner: runners.lifecycle,
					signRunner: runners.sign,
				});
			},
		],
	});
	harnesses.push(harness);
	return harness;
}

interface ToolCallResult {
	text: string;
	details: unknown;
}

async function callToolResult(
	harness: Harness,
	name: string,
	params: Record<string, unknown>,
): Promise<ToolCallResult> {
	const id = `t11-${callCounter++}`;
	harness.setResponses([
		fauxAssistantMessage([fauxToolCall(name, params, { id })], { stopReason: "toolUse" }),
		fauxAssistantMessage("done"),
	]);
	await harness.session.prompt("T-11 offline decision contract check");
	const result = harness.session.messages.find(
		(message): message is Extract<AgentMessage, { role: "toolResult" }> =>
			message.role === "toolResult" && message.toolCallId === id,
	);
	if (!result) throw new Error(`missing toolResult for ${id}`);
	return { text: getMessageText(result), details: result.details };
}

async function callTool(harness: Harness, name: string, params: Record<string, unknown>): Promise<string> {
	return (await callToolResult(harness, name, params)).text;
}

function firstLine(text: string): string {
	return text.split("\n")[0] ?? "";
}

function payloadOf(text: string): AskPayload {
	return JSON.parse(firstLine(text)) as AskPayload;
}

function askDetailsOf(rawDetails: unknown): AskDetails {
	return rawDetails as AskDetails;
}

function countsOf(runners: FakeRunners): Counts {
	return {
		decide: runners.decideCalls.length,
		lifecycle: runners.lifecycleCalls.length,
		sign: runners.signCalls.length,
		spawn: spawnCalls.length,
	};
}

function expectNoNewActivity(label: string, project: Project, runners: FakeRunners, before: Counts): void {
	expect(runners.decideCalls, `${label}: decide runner`).toHaveLength(before.decide);
	expect(runners.lifecycleCalls, `${label}: lifecycle runner`).toHaveLength(before.lifecycle);
	expect(runners.signCalls, `${label}: sign runner`).toHaveLength(before.sign);
	expect(spawnCalls, `${label}: external spawn`).toHaveLength(before.spawn);
	expect(fs.existsSync(project.spawnMarker), `${label}: MW_PY sentinel`).toBe(false);
}

function expectNoAuthorityWrites(label: string, project: Project, indexBefore: Buffer, mdBefore: Buffer): void {
	expect(fs.readFileSync(project.indexFile).equals(indexBefore), `${label}: _index.parallel bytes`).toBe(true);
	expect(fs.readFileSync(project.indexMd).equals(mdBefore), `${label}: _index.md bytes`).toBe(true);
	expect(fs.existsSync(path.join(project.root, ".mw", "index.lock")), `${label}: index.lock`).toBe(false);
}

function assertProjectionCheck(project: Project, kind: "scalar" | "array" | undefined): void {
	if (kind === "scalar") {
		expect(() => readIndexMdActiveKeys(project.agenticdoc)).toThrow();
		return;
	}
	if (kind === "array") {
		expect(readIndexMdActiveKeys(project.agenticdoc)).toEqual([SELF_KEY, FOREIGN_KEY]);
	}
}

async function establishDecision(
	label: string,
	project: Project,
	runners: FakeRunners,
	harness: Harness,
): Promise<LegalDecision> {
	setAuthority(project, [ownActive, foreignActive]);
	const text = await callTool(harness, ASK_DECISION_TOOL, askParams(undefined));
	const payload = payloadOf(text);
	expect(payload.available, `${label}: legal ask must reach the fake runner`).toBe(true);
	if (!payload.available || typeof payload.decision_id !== "string") {
		throw new Error(`${label}: legal ask did not return a decision_id`);
	}
	const last = runners.decideCalls.at(-1);
	if (last === undefined) throw new Error(`${label}: legal ask did not call the fake runner`);
	const envelope = JSON.parse(last.input) as { meta: EnvelopeMeta };
	expect(payload.decision_id, `${label}: child decision_id`).toBe(`dp-auto:${envelope.meta.logical_id}`);
	expect(envelope.meta.key, `${label}: bound meta.key`).toBe(SELF_KEY);
	expect(envelope.meta.initiator_role, `${label}: structural role`).toBe("pm");
	expect(envelope.meta.task_key, `${label}: no inferred task`).toBeNull();
	return { decisionId: payload.decision_id, logicalId: envelope.meta.logical_id, key: envelope.meta.key };
}

async function assertAskRefusal(
	label: string,
	matrixCase: MatrixCase,
	project: Project,
	runners: FakeRunners,
	harness: Harness,
): Promise<void> {
	setAuthority(project, matrixCase.askRows, matrixCase.askProjection);
	matrixCase.prepare?.(project);
	assertProjectionCheck(project, matrixCase.projectionCheck);
	const before = countsOf(runners);
	const indexBefore = fs.readFileSync(project.indexFile);
	const mdBefore = fs.readFileSync(project.indexMd);
	const text = await callTool(harness, ASK_DECISION_TOOL, askParams(matrixCase.askKey));
	const payload = payloadOf(text);
	expect(payload.available, `${label}: ask available`).toBe(false);
	expect(payload.unavailable, `${label}: ask reason`).toBe(ASK_DECISION_REASON_INPUT_INCOMPLETE);
	expect(payload.action, `${label}: ask action`).toBe(ASK_DECISION_BLOCKED_ACTION);
	expect(payload.missing_fields, `${label}: no missing material field`).toBeUndefined();
	expect(payload.claim_diagnosis?.reason, `${label}: ask diagnosis`).toBe(matrixCase.reason);
	expect(payload.claim_diagnosis?.message, `${label}: diagnosis names meta.key`).toContain("meta.key");
	expect(text, `${label}: no-guessing directive`).toContain("不要自行猜测");
	expectNoNewActivity(label, project, runners, before);
	expectNoAuthorityWrites(label, project, indexBefore, mdBefore);
	const after = countsOf(runners);
	process.stdout.write(
		`[EVIDENCE] T-11 case=${label} entry=ask result=refused reason=${matrixCase.reason} ` +
			`decide_delta=${after.decide - before.decide} lifecycle_delta=${after.lifecycle - before.lifecycle} ` +
			`sign_delta=${after.sign - before.sign} spawn_delta=${after.spawn - before.spawn} ` +
			`decide=${after.decide} lifecycle=${after.lifecycle} sign=${after.sign} spawn=${after.spawn} receipts=0 ` +
			`spawn_marker=${String(fs.existsSync(project.spawnMarker))}\n`,
	);
}

async function assertReceiptRefusal(
	label: string,
	matrixCase: MatrixCase,
	project: Project,
	runners: FakeRunners,
	harness: Harness,
): Promise<void> {
	const legal = await establishDecision(label, project, runners, harness);
	expect(legal.key, `${label}: legal decision key`).toBe(SELF_KEY);
	setAuthority(project, matrixCase.receiptRows, matrixCase.receiptProjection);
	matrixCase.prepare?.(project);
	assertProjectionCheck(project, matrixCase.projectionCheck);
	const before = countsOf(runners);
	const indexBefore = fs.readFileSync(project.indexFile);
	const mdBefore = fs.readFileSync(project.indexMd);
	const { text, details: rawDetails } = await callToolResult(harness, DECISION_RECEIPT_TOOL, {
		decision_id: legal.decisionId,
		stage: "executed",
		action: "record",
	});
	const details = rawDetails as ReceiptDetails;
	const refusal = payloadOf(text);
	expect(refusal.available, `${label}: receipt text available`).toBe(false);
	expect(refusal.unavailable, `${label}: receipt text reason`).toBe(ASK_DECISION_REASON_INPUT_INCOMPLETE);
	expect(refusal.action, `${label}: receipt text action`).toBe(ASK_DECISION_BLOCKED_ACTION);
	expect(refusal.missing_fields, `${label}: receipt text has no missing material field`).toBeUndefined();
	expect(refusal.claim_diagnosis?.reason, `${label}: receipt text diagnosis`).toBe(matrixCase.reason);
	expect(details.status, `${label}: receipt details status`).toBe("refused");
	expect(details.unavailable, `${label}: receipt reason`).toBe(ASK_DECISION_REASON_INPUT_INCOMPLETE);
	expect(details.decision_id, `${label}: receipt decision_id`).toBe(legal.decisionId);
	expect(details.claim_diagnosis?.reason, `${label}: receipt diagnosis`).toBe(matrixCase.reason);
	expect(text, `${label}: receipt diagnosis text`).toContain("claim_diagnosis");
	expect(text, `${label}: receipt has no missing_fields`).not.toContain('"missing_fields"');
	expectNoNewActivity(label, project, runners, before);
	expectNoAuthorityWrites(label, project, indexBefore, mdBefore);
	const after = countsOf(runners);
	process.stdout.write(
		`[EVIDENCE] T-11 case=${label} entry=receipt result=refused reason=${matrixCase.reason} ` +
			`decide_delta=${after.decide - before.decide} lifecycle_delta=${after.lifecycle - before.lifecycle} ` +
			`sign_delta=${after.sign - before.sign} spawn_delta=${after.spawn - before.spawn} ` +
			`decide=${after.decide} lifecycle=${after.lifecycle} sign=${after.sign} spawn=${after.spawn} ` +
			`receipt_attempts=1 receipts_written=0 spawn_marker=${String(fs.existsSync(project.spawnMarker))}\n`,
	);
}

beforeEach(() => {
	for (const name of ENV_NAMES) savedEnv.set(name, process.env[name]);
	const home = mkTemp("mw-t11-home-");
	process.env.HOME = home;
	process.env.USERPROFILE = home;
	process.env.PI_CODING_AGENT_DIR = path.join(home, ".pi", "agent");
	fs.mkdirSync(process.env.PI_CODING_AGENT_DIR, { recursive: true });
	delete process.env.PI_WORKER_TASK;
	delete process.env.MW_PY;
	delete process.env.MW_STUB_SEEN;
	delete process.env.MW_T11_SPAWN_SENTINEL;
	spawnCalls.length = 0;
	projects.length = 0;
	callCounter = 0;
});

afterEach(() => {
	for (const [name, value] of savedEnv) {
		if (value === undefined) delete process.env[name];
		else process.env[name] = value;
	}
	savedEnv.clear();
	while (harnesses.length > 0) harnesses.pop()?.cleanup();
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	projects.length = 0;
	spawnCalls.length = 0;
	vi.restoreAllMocks();
});

describe("T-11 multi-active ask/receipt window-claim contract (VC-005)", () => {
	it("binds only the current window's unique authoritative active key at both real tool entries", async () => {
		expect(SELF_CLAIM, "ui-bridge and implementation-gate identities agree").toBe(currentClaimId());
		expect(FORGED_CLAIM, "forged claim differs from the real windowClaimId").not.toBe(SELF_CLAIM);
		expect(FOREIGN_CLAIM).not.toBe(SELF_CLAIM);
		const receiptProperties =
			(DECISION_RECEIPT_PARAMETERS as { properties?: Record<string, unknown> }).properties ?? {};
		expect(receiptProperties.key, "receipt has no model-supplied key bypass").toBeUndefined();

		// ── Positive: multiple active rows, own active passes to fake runners ──
		const positive = newProject();
		const positiveRunners = fakeRunners();
		const positiveHarness = await harnessFor(positive, positiveRunners);
		const positiveIndexBefore = fs.readFileSync(positive.indexFile);
		const positiveMdBefore = fs.readFileSync(positive.indexMd);
		const positiveSpawnBefore = spawnCalls.length;
		expect(readIndexMdActiveKeys(positive.agenticdoc), "canonical projection is a collection only").toEqual([
			SELF_KEY,
			FOREIGN_KEY,
		]);

		const askOmittedResult = await callToolResult(positiveHarness, ASK_DECISION_TOOL, askParams(undefined));
		const askOmittedText = askOmittedResult.text;
		const askOmittedDetails = askDetailsOf(askOmittedResult.details);
		const askOmitted = payloadOf(askOmittedText);
		expect(askOmitted.available, `multi-active omitted key: ${JSON.stringify(askOmitted)}`).toBe(true);
		expect(askOmitted.claim_diagnosis, "success has no diagnosis leak").toBeUndefined();
		const omittedEnvelope = JSON.parse((positiveRunners.decideCalls[0] as DecideRunRequest).input) as {
			meta: EnvelopeMeta;
		};
		expect(omittedEnvelope.meta.key).toBe(SELF_KEY);
		const firstDecision = askOmitted.decision_id;
		if (typeof firstDecision !== "string") throw new Error("first legal ask returned no decision_id");
		expect(firstDecision).toBe(`dp-auto:${omittedEnvelope.meta.logical_id}`);
		expect(askOmittedDetails.matter_suppressed, "first ask is not a replay").toBeUndefined();
		expect(askOmittedDetails.decision_id, "first ask details decision_id").toBe(firstDecision);
		expect(askOmittedDetails.decision_feedback?.binding?.key, "first ask binding").toBe(SELF_KEY);
		const firstMatterRef = askOmittedDetails.decision_feedback?.matter_ref;
		if (typeof firstMatterRef !== "string") throw new Error("first legal ask returned no matter_ref");

		const caseVariantKey = `  ${SELF_KEY.toUpperCase()}  `;
		const replayBefore = countsOf(positiveRunners);
		const askStringResult = await callToolResult(positiveHarness, ASK_DECISION_TOOL, askParams(caseVariantKey));
		const askStringText = askStringResult.text;
		const askStringDetails = askDetailsOf(askStringResult.details);
		process.stdout.write(
			`[DIAGNOSTIC] T-21 second-ask first_decision_id=${firstDecision} first_matter_ref=${firstMatterRef} ` +
				`replay_response=${firstLine(askStringText)} replay_details=${JSON.stringify(askStringDetails)} ` +
				`counts_before=${JSON.stringify(replayBefore)} counts_after=${JSON.stringify(countsOf(positiveRunners))}\n`,
		);
		const askString = payloadOf(askStringText);
		expect(askString.available, "same-matter replay is available").toBe(true);
		expect(askString.matter_suppressed, "same-matter replay is suppressed").toBe(true);
		expect(askString.decision_id, "same-matter replay reuses the decision id").toBe(firstDecision);
		expect(askStringDetails.matter_suppressed, "same-matter replay details are suppressed").toBe(true);
		expect(askStringDetails.decision_id, "same-matter replay details reuse the decision id").toBe(firstDecision);
		expect(askStringDetails.decision_feedback?.matter_ref, "same-matter replay reuses the matter ref").toBe(
			firstMatterRef,
		);
		expect(askStringDetails.decision_feedback?.binding?.key, "same-matter replay reuses the own-key binding").toBe(
			SELF_KEY,
		);
		expectNoNewActivity("same-matter replay", positive, positiveRunners, replayBefore);
		expectNoAuthorityWrites("same-matter replay", positive, positiveIndexBefore, positiveMdBefore);
		expect(positiveRunners.decideCalls, "one real ask reached the fake decide runner").toHaveLength(1);
		expect(positiveRunners.lifecycleCalls, "one consumed row for the real ask").toHaveLength(1);
		expect(positiveRunners.signCalls, "no sign runner on dp-auto").toHaveLength(0);

		const receiptText = await callTool(positiveHarness, DECISION_RECEIPT_TOOL, {
			decision_id: firstDecision,
			stage: "executed",
			action: "record",
		});
		const receiptDetails = JSON.parse(firstLine(receiptText)) as ReceiptDetails;
		expect(receiptDetails.status, "legal receipt reaches the fake lifecycle runner").toBe("written");
		expect(receiptDetails.decision_id).toBe(firstDecision);
		expect(receiptText).not.toContain("refused");
		expect(positiveRunners.decideCalls, "one real ask reached the fake decide runner").toHaveLength(1);
		expect(positiveRunners.lifecycleCalls, "consumed, executed").toHaveLength(2);
		const executedEnvelope = JSON.parse((positiveRunners.lifecycleCalls[1] as LifecycleRequest).input) as {
			stage: string;
			action: string;
			decision_id: string;
			meta: EnvelopeMeta;
		};
		expect(executedEnvelope).toMatchObject({ stage: "executed", action: "record", decision_id: firstDecision });
		expect(executedEnvelope.meta.key).toBe(SELF_KEY);
		expect(spawnCalls, "positive path spawned zero children").toHaveLength(positiveSpawnBefore);
		expect(fs.existsSync(positive.spawnMarker), "positive MW_PY sentinel never ran").toBe(false);
		expectNoAuthorityWrites("positive", positive, positiveIndexBefore, positiveMdBefore);
		process.stdout.write(
			`[EVIDENCE] T-11 case=own-active entry=ask+receipt result=pass decide=${positiveRunners.decideCalls.length} ` +
				`lifecycle=${positiveRunners.lifecycleCalls.length} sign=${positiveRunners.signCalls.length} ` +
				`spawn_delta=${spawnCalls.length - positiveSpawnBefore} spawn_calls=${spawnCalls.length} receipts=1 ` +
				`spawn_marker=${String(fs.existsSync(positive.spawnMarker))}\n`,
		);

		// Separate harness: the explicit case/whitespace own-key ask is a fresh
		// matter cache, so its real envelope binding remains directly observable.
		const explicitProject = newProject();
		const explicitRunners = fakeRunners();
		const explicitHarness = await harnessFor(explicitProject, explicitRunners);
		const explicitIndexBefore = fs.readFileSync(explicitProject.indexFile);
		const explicitMdBefore = fs.readFileSync(explicitProject.indexMd);
		const explicitSpawnBefore = spawnCalls.length;
		const explicitAskResult = await callToolResult(explicitHarness, ASK_DECISION_TOOL, askParams(caseVariantKey));
		const explicitPayload = payloadOf(explicitAskResult.text);
		expect(explicitPayload.available, "explicit case/whitespace own key").toBe(true);
		expect(explicitPayload.matter_suppressed, "independent harness has no replay").toBeUndefined();
		const explicitDecision = explicitPayload.decision_id;
		if (typeof explicitDecision !== "string") throw new Error("explicit legal ask returned no decision_id");
		const explicitEnvelope = JSON.parse((explicitRunners.decideCalls[0] as DecideRunRequest).input) as {
			meta: EnvelopeMeta;
		};
		expect(explicitEnvelope.meta.key, "string key binds to stored authoritative spelling").toBe(SELF_KEY);
		expect(explicitRunners.decideCalls).toHaveLength(1);
		expect(explicitRunners.lifecycleCalls).toHaveLength(1);
		expect(explicitRunners.signCalls).toHaveLength(0);
		expect(spawnCalls, "explicit positive path spawned zero children").toHaveLength(explicitSpawnBefore);
		expect(fs.existsSync(explicitProject.spawnMarker), "explicit MW_PY sentinel never ran").toBe(false);
		expectNoAuthorityWrites(
			"explicit case/whitespace own key",
			explicitProject,
			explicitIndexBefore,
			explicitMdBefore,
		);

		const explicitReceiptResult = await callToolResult(explicitHarness, DECISION_RECEIPT_TOOL, {
			decision_id: explicitDecision,
			stage: "executed",
			action: "record",
		});
		const explicitReceiptDetails = explicitReceiptResult.details as ReceiptDetails;
		expect(explicitReceiptDetails.status, "explicit legal receipt reaches the fake lifecycle runner").toBe("written");
		expect(explicitReceiptDetails.decision_id).toBe(explicitDecision);
		expect(explicitReceiptResult.text).not.toContain("refused");
		expect(explicitRunners.lifecycleCalls).toHaveLength(2);
		const explicitExecutedEnvelope = JSON.parse((explicitRunners.lifecycleCalls[1] as LifecycleRequest).input) as {
			stage: string;
			action: string;
			decision_id: string;
			meta: EnvelopeMeta;
		};
		expect(explicitExecutedEnvelope).toMatchObject({
			stage: "executed",
			action: "record",
			decision_id: explicitDecision,
		});
		expect(explicitExecutedEnvelope.meta.key).toBe(SELF_KEY);
		expect(spawnCalls, "explicit positive receipt spawned zero children").toHaveLength(explicitSpawnBefore);
		expectNoAuthorityWrites("explicit receipt", explicitProject, explicitIndexBefore, explicitMdBefore);
		process.stdout.write(
			`[DIAGNOSTIC] T-21 explicit-positive case_variant=${JSON.stringify(caseVariantKey)} ` +
				`decide=${explicitRunners.decideCalls.length} lifecycle=${explicitRunners.lifecycleCalls.length} ` +
				`sign=${explicitRunners.signCalls.length} spawn_delta=${spawnCalls.length - explicitSpawnBefore} ` +
				`receipts=1 matter_suppressed=false\n`,
		);

		// ── Negative matrix: every row is refused at BOTH real entries ───────
		const staleScalar = `active: ${SELF_KEY}\n`;
		const staleArray = renderProjection([SELF_KEY, FOREIGN_KEY]);
		const cases: readonly MatrixCase[] = [
			{
				name: "foreign-live",
				askRows: [ownActive, foreignActive],
				askKey: FOREIGN_KEY,
				reason: "foreign-owner",
				receiptRows: [{ key: SELF_KEY, status: "active", claimId: FOREIGN_CLAIM }, foreignActive],
			},
			{
				name: "idle",
				askRows: [ownActive, idleOwn, foreignActive],
				askKey: IDLE_KEY,
				reason: "key-inactive",
				receiptRows: [{ key: SELF_KEY, status: "idle", claimId: SELF_CLAIM }, foreignActive],
			},
			{
				name: "forged-self-claim",
				askRows: [ownActive, foreignActive, { key: FORGED_KEY, status: "active", claimId: FORGED_CLAIM }],
				askKey: FORGED_KEY,
				reason: "foreign-owner",
				receiptRows: [{ key: SELF_KEY, status: "active", claimId: FORGED_CLAIM }, foreignActive],
				prepare: (project) => {
					writePmState(project, FORGED_KEY, SELF_CLAIM);
					writePmState(project, SELF_KEY, SELF_CLAIM);
				},
			},
			{
				name: "duplicate-self-first",
				askRows: [dupSelfFirst, dupForeignSecond, foreignActive],
				askKey: DUP_KEY,
				reason: "ambiguous-claim",
				receiptRows: [
					{ key: SELF_KEY, status: "active", claimId: SELF_CLAIM },
					{ key: SELF_KEY.toUpperCase(), status: "active", claimId: FOREIGN_CLAIM },
					foreignActive,
				],
			},
			{
				name: "duplicate-foreign-first",
				askRows: [dupForeignFirst, dupSelfSecond, foreignActive],
				askKey: DUP_KEY.toUpperCase(),
				reason: "ambiguous-claim",
				receiptRows: [
					{ key: SELF_KEY.toUpperCase(), status: "active", claimId: FOREIGN_CLAIM },
					{ key: SELF_KEY, status: "active", claimId: SELF_CLAIM },
					foreignActive,
				],
			},
			{
				name: "stale-scalar-projection",
				askRows: [foreignActive, idleOwn],
				askKey: SELF_KEY,
				reason: "key-not-found",
				receiptRows: [foreignActive, idleOwn],
				askProjection: staleScalar,
				receiptProjection: staleScalar,
				projectionCheck: "scalar",
			},
			{
				name: "stale-array-projection",
				askRows: [{ key: SELF_KEY, status: "idle", claimId: SELF_CLAIM }, foreignActive],
				askKey: SELF_KEY,
				reason: "key-inactive",
				receiptRows: [{ key: SELF_KEY, status: "idle", claimId: SELF_CLAIM }, foreignActive],
				askProjection: staleArray,
				receiptProjection: staleArray,
				projectionCheck: "array",
			},
		];

		for (const matrixCase of cases) {
			const label = matrixCase.name;
			const project = newProject();
			const runners = fakeRunners();
			const harness = await harnessFor(project, runners);
			await assertAskRefusal(`ask/${label}`, matrixCase, project, runners, harness);
			await assertReceiptRefusal(`receipt/${label}`, matrixCase, project, runners, harness);
		}

		expect(spawnCalls, "whole matrix: zero external spawn calls").toHaveLength(0);
		expect(
			projects.every((project) => !fs.existsSync(project.spawnMarker)),
			"whole matrix: zero MW_PY sentinels",
		).toBe(true);
		// Print the frozen marker ONLY after every real matrix assertion above passed.
		process.stdout.write(`[VERIFY] VC-005: identity_strict=true\n`);
	});
});
