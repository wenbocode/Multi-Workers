/**
 * T14-A first isolated L2 entry. One vitest run builds one disposable key,
 * composes the real production host twice (PM and worker windows), drives the
 * production `agent_settled` dispatch handler, and stops at the first genuine
 * business gate refusal. Faux provider only; no paid API, no production write.
 */

import { execFileSync } from "node:child_process";
import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { type AgentTeamLoopComposition, activateWithRuntimeHost } from "../../src/extensions/agent-team-loop/index.ts";
import { ASK_DECISION_TOOL } from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import { SUBMIT_DECISION_HANDOFF_TOOL } from "../../src/extensions/agent-team-loop/pm/host-submit.ts";
import { parseHead, type RuntimeHostCounts } from "../../src/extensions/agent-team-loop/pm/runtime-host-adapter.ts";
import { readDecidePolicy } from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import {
	cardWriteFaceEntries,
	ENVELOPE_PRODUCER_KEY,
	envelopeProducerIdentity,
	extractCardSections,
	renderWriteFaceLine,
	WRITE_FACE_CARD_SECTION,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import {
	DISPOSITION_FILE_SUFFIX,
	EXECUTION_FILE_SUFFIX,
	SELECTION_FILE_SUFFIX,
	storedRecordPath,
} from "../../src/extensions/agent-team-loop/shared/local-selection-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import {
	type BashWriteScopeConfig,
	checkBashWriteScopeTarget,
	parseTaskMd,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { createHarness } from "./harness.ts";

type Harness = Awaited<ReturnType<typeof createHarness>>;
type JsonRecord = Record<string, unknown>;

interface Fixture {
	root: string;
	doc: string;
	keyDir: string;
	taskMdPath: string;
	cardPath: string;
	cardSha256: string;
	cardText: string;
	controlledPath: string;
	outsidePath: string;
	writeFaceLine: string;
	taskKey: string;
	keyName: string;
	claim: string;
}

interface ToolState {
	writes: number;
	results: JsonRecord[];
}

interface FailureRecord {
	stage: string;
	code: string;
	call: string;
	details: JsonRecord;
	text: string;
}

const ACTIVATION_FLAG = "__agentTeamLoopActivated";
const WATCH_ENTRY_TYPE = "agent-team-loop:watch";
const originalCwd = process.cwd();
const outerRunId = process.env.MW_L2_OUTER_RUN_ID ?? "unset";
const innerRunId = `l2:${crypto.randomUUID()}`;
const ownrun = process.env.MW_L2_OWNRUN ?? path.join(os.tmpdir(), `dp-l2-ownrun-${innerRunId.replaceAll(":", "-")}`);
const eventsPath = path.join(ownrun, "entry.events.jsonl");
const snapshotPath = path.join(ownrun, "entry.snapshot.json");
const negativeEventsPath = path.join(ownrun, "negative.events.jsonl");
const negativeSnapshotPath = path.join(ownrun, "negative.snapshot.json");
const negativeInnerRunId = `l2-negative:${crypto.randomUUID()}`;
const CONTROLLED_REL = "src/l2.txt";
const OUTSIDE_REL = "src/outside.txt";
const EXPECTED_CONTENT = "l2-real-action\n";
const OUTSIDE_CONTENT = "outside-initial\n";
const roots: string[] = [];
const harnesses: Harness[] = [];
const startedAt = new Date().toISOString();
const entryPath = "packages/coding-agent/test/suite/dp-continuity-runtime-l2.test.ts";
const taskGoal =
	"建立可收集可执行的最小隔离 L2 入口，在 DP 全程离线、signoff 要求启用和有限预算的同一 run 中，通过真实 dispatchNewTasks→registerPmDispatch 激活 worker，尽量取得真实 action/result；首个门禁拒绝立即停止该业务链并原样留证。";

fs.mkdirSync(ownrun, { recursive: true });
fs.writeFileSync(eventsPath, "", "utf8");
fs.writeFileSync(negativeEventsPath, "", "utf8");

function resetActivationFlag(): void {
	delete (globalThis as Record<string, unknown>)[ACTIVATION_FLAG];
}

function record(event: JsonRecord, targetPath: string = eventsPath): void {
	const row = {
		marker: "L2_EVENT",
		outer_run_id: outerRunId,
		inner_run_id: innerRunId,
		at: new Date().toISOString(),
		...event,
	};
	fs.appendFileSync(targetPath, `${JSON.stringify(row)}\n`, "utf8");
	process.stdout.write(`${JSON.stringify(row)}\n`);
}

function sha256(text: string): string {
	return sha256Bytes(Buffer.from(text, "utf8"));
}

function sha256Bytes(bytes: Buffer): string {
	return crypto.createHash("sha256").update(bytes).digest("hex");
}

function fileManifest(root: string): Record<string, string> {
	const out: Record<string, string> = {};
	const walk = (dir: string): void => {
		for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
			const full = path.join(dir, entry.name);
			if (entry.isDirectory()) walk(full);
			else if (entry.isFile())
				out[path.relative(root, full).replaceAll("\\", "/")] = sha256Bytes(fs.readFileSync(full));
		}
	};
	walk(root);
	return Object.fromEntries(Object.entries(out).sort(([a], [b]) => a.localeCompare(b)));
}

function readJsonRecord(file: string): JsonRecord | null {
	if (!fs.existsSync(file)) return null;
	return JSON.parse(fs.readFileSync(file, "utf8")) as JsonRecord;
}

function budgetBlock(maxSteps: number, remaining: number): string {
	return [
		"## 事项预算事实",
		"- `budget_ref`: `tasks/AC015-L2.md#事项预算事实` + 其 SHA",
		"- `matter_ref`: `l2-isolated-key/AC015-L2`；`parent_matter_ref`: `l2-isolated-key`",
		"- `deadline`: `run.json.started_at + 30m`（由 harness 派生）",
		`- \`max_steps\`: ${maxSteps}`,
		"- `no_progress_limit`: 5",
		`- \`remaining_cost\`: ${remaining}，\`cost_consumed\` 与 \`steps_consumed\` 同单位（1 cost unit ≡ 1 tool call；卡明确约定）`,
		"- `steps_consumed` / `no_progress_count`：本运行初始 0",
		"- `source_refs`: 卡 SHA、`run.json`、`_index.parallel`、`task.md` 头",
		"",
	].join("\n");
}

function fixture(): Fixture {
	// Windows os.tmpdir() uses an 8.3 short path. resolveWorkspaceConfig uses
	// realpathSync.native (long path), while the shell guard uses realpathSync
	// (which preserves the short form); canonicalizing here keeps the card,
	// envelope, worker cwd and write-face parser on ONE path identity.
	const root = fs.realpathSync.native(fs.mkdtempSync(path.join(os.tmpdir(), "dp-continuity-l2-")));
	roots.push(root);
	const doc = path.join(root, ".agenticdoc");
	const keyName = "l2-isolated-key";
	const taskKey = "l2-first-entry";
	const claim = currentClaimId();
	const keyDir = path.join(doc, keyName);
	const workerDir = path.join(keyDir, "workers", taskKey);
	const cardPath = path.join(keyDir, "tasks", "AC015-L2.md");
	const taskMdPath = path.join(workerDir, "task.md");
	fs.mkdirSync(path.join(keyDir, "tasks"), { recursive: true });
	fs.mkdirSync(path.join(keyDir, "evidence", "research"), { recursive: true });
	fs.mkdirSync(workerDir, { recursive: true });
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.mkdirSync(path.join(root, "src"), { recursive: true });

	const decidePoints = {
		version: 1,
		updated_at: startedAt,
		updated_by: "human",
		points: Object.fromEntries(
			[
				"dp-w-type",
				"dp-pm-steer",
				"dp-w-check-task",
				"dp-QG",
				"dp-gate-approve",
				"dp-sign-key",
				"dp-auto",
				"dp-route",
			].map((dp) => [dp, { tier: "P2", enabled: false, mode: "auto", note: "" }]),
		),
	};
	const decideJson = {
		enabled: false,
		signoff: "auto",
		points: Object.fromEntries(Object.keys(decidePoints.points).map((dp) => [dp, { enabled: false }])),
	};
	fs.writeFileSync(
		path.join(doc, "_index.parallel"),
		`# Index Parallel\n| ${keyName} | active | EXECUTE | ${claim} | | isolated L2 fixture | now |\n`,
	);
	fs.writeFileSync(path.join(doc, "target.yml"), "active: single\n");
	fs.writeFileSync(path.join(root, ".mw", "mw.pid"), String(process.pid));
	fs.writeFileSync(path.join(root, ".mw", "decide.json"), `${JSON.stringify(decideJson, null, 2)}\n`);
	fs.writeFileSync(path.join(root, ".mw", "decide-points.json"), `${JSON.stringify(decidePoints, null, 2)}\n`);
	fs.writeFileSync(path.join(root, ".mw", "dispatch.yml"), "models:\n  coding: faux/faux\n");
	fs.writeFileSync(path.join(keyDir, "pm-state.md"), `- Phase: init\n- ClaimId: ${claim}\n`);
	fs.writeFileSync(
		path.join(keyDir, "spec.md"),
		`# Isolated L2 spec\n\nAC-001: one same-run PM dispatch and bounded worker activation slice.\n\n${"x".repeat(600)}\n`,
	);
	fs.writeFileSync(path.join(keyDir, "design.md"), `# Isolated L2 design\n\n${"x".repeat(600)}\n`);
	fs.writeFileSync(path.join(keyDir, "evidence", "research", "spec-note.md"), "spec research note\n");
	fs.writeFileSync(path.join(keyDir, "evidence", "research", "design-note.md"), "design research note\n");
	const cardText = [
		`# AC015 L2 first entry`,
		``,
		`type: coding`,
		`owning_pm_claim: ${claim}`,
		`title: isolated L2 first entry`,
		``,
		budgetBlock(8, 8),
		`## ${WRITE_FACE_CARD_SECTION}`,
		``,
		`- \`${CONTROLLED_REL}\``,
		``,
		`## 写入禁止面`,
		``,
		`- 除上述唯一具体文件外的所有路径`,
		``,
	].join("\n");
	fs.writeFileSync(cardPath, cardText);
	const cardSha256 = sha256(cardText);
	const cardEntries = cardWriteFaceEntries(extractCardSections(cardText)) ?? [];
	const writeFaceLine = renderWriteFaceLine(cardEntries);
	const taskText = [
		`type: coding`,
		`images: no`,
		`card_path: tasks/AC015-L2.md`,
		`card_sha256: ${cardSha256}`,
		`${ENVELOPE_PRODUCER_KEY}: ${envelopeProducerIdentity()}`,
		writeFaceLine,
		``,
		`# Isolated L2 worker slice`,
		``,
		`One same-run bounded action and its real result; an unexpected gate refusal stops the chain.`,
		``,
	].join("\n");
	fs.writeFileSync(taskMdPath, taskText);
	const controlledPath = path.join(root, CONTROLLED_REL);
	const outsidePath = path.join(root, OUTSIDE_REL);
	fs.writeFileSync(controlledPath, "initial\n");
	fs.writeFileSync(outsidePath, OUTSIDE_CONTENT);
	return {
		root,
		doc,
		keyDir,
		taskMdPath,
		cardPath,
		cardSha256,
		cardText,
		controlledPath,
		outsidePath,
		writeFaceLine,
		taskKey,
		keyName,
		claim,
	};
}

function nativeDecideConfig(root: string): JsonRecord {
	const repoPython = path.resolve(originalCwd, "..", "multi-workers");
	const code = [
		"import json, sys",
		"sys.path.insert(0, sys.argv[1])",
		"import decision",
		"cfg, err = decision.DecisionConfig.from_project(sys.argv[2])",
		"print(json.dumps({'enabled': cfg.enabled, 'signoff': cfg.signoff, 'signoff_error': cfg.signoff_error, 'unconfigured': cfg.unconfigured, 'config_error': cfg.config_error, 'parser_error': err}))",
	].join("; ");
	const stdout = execFileSync(
		process.env.PYTHON_EXE ?? "python",
		["-I", "-B", "-X", "utf8", "-c", code, repoPython, root],
		{
			cwd: originalCwd,
			encoding: "utf8",
			timeout: 10_000,
			windowsHide: true,
			maxBuffer: 65_536,
		},
	);
	return JSON.parse(stdout.trim()) as JsonRecord;
}

function findToolResult(h: Harness, name: string) {
	const message = [...h.session.messages]
		.reverse()
		.find((item) => item.role === "toolResult" && item.toolName === name);
	return message !== undefined && message.role === "toolResult" ? message : undefined;
}

function toolCallId(h: Harness, name: string): string | undefined {
	return findToolResult(h, name)?.toolCallId;
}

function toolDetails(h: Harness, name: string): JsonRecord {
	const message = findToolResult(h, name);
	if (message === undefined) return {};
	const direct = message.details;
	if (direct !== null && typeof direct === "object" && !Array.isArray(direct) && Object.keys(direct).length > 0)
		return direct as JsonRecord;
	const content = message.content;
	if (typeof content === "string") return { text: content };
	if (Array.isArray(content)) {
		for (const part of content) {
			if (
				part !== null &&
				typeof part === "object" &&
				"type" in part &&
				part.type === "text" &&
				"text" in part &&
				typeof part.text === "string"
			) {
				try {
					const parsed: unknown = JSON.parse(part.text);
					if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)) return parsed as JsonRecord;
				} catch {
					return { text: part.text };
				}
			}
		}
	}
	return {};
}

function toolResultText(h: Harness, name: string): string {
	const message = findToolResult(h, name);
	if (message === undefined) return "";
	const content = message.content;
	if (typeof content === "string") return content;
	if (!Array.isArray(content)) return "";
	const texts: string[] = [];
	for (const part of content) {
		if (
			part !== null &&
			typeof part === "object" &&
			"type" in part &&
			part.type === "text" &&
			"text" in part &&
			typeof part.text === "string"
		)
			texts.push(part.text);
	}
	return texts.join("\n");
}

function guardConfigFor(f: Fixture): BashWriteScopeConfig {
	const meta = parseTaskMd(f.taskMdPath);
	return {
		projectRoot: f.root,
		taskDir: path.dirname(f.taskMdPath),
		keyDir: f.keyDir,
		trueRoot: meta.trueAgenticdocRoot,
		writeScope: meta.writeScope,
		writeScopeBase: path.dirname(meta.trueAgenticdocRoot),
		roleClass: "writable",
		writeFace: meta.writeFace,
		writeFaceRejected:
			meta.writeFace === undefined && (meta.writeFaceRejected !== undefined || meta.writeFaceEntries !== undefined),
		writeRoots: meta.writeRoots,
	};
}

function declarationFacts(f: Fixture): JsonRecord {
	const cardEntries = cardWriteFaceEntries(extractCardSections(f.cardText)) ?? [];
	const rendered = renderWriteFaceLine(cardEntries);
	const taskText = fs.readFileSync(f.taskMdPath, "utf8");
	const head = parseHead(taskText);
	const meta = parseTaskMd(f.taskMdPath);
	const config = guardConfigFor(f);
	const controlledVerdict = checkBashWriteScopeTarget(config, CONTROLLED_REL, true, "write");
	const outsideVerdict = checkBashWriteScopeTarget(config, OUTSIDE_REL, true, "write");
	return {
		card_path: path.relative(f.keyDir, f.cardPath).replaceAll("\\", "/"),
		card_sha256: f.cardSha256,
		card_write_face_entries: cardEntries,
		rendered_write_face_line: rendered,
		envelope_write_face_line: f.writeFaceLine,
		envelope_head_ok: head.ok,
		envelope_head: head.ok ? head.value : { error: head.reason, gaps: head.gaps },
		worker_cwd: process.cwd(),
		fixture_root: f.root,
		project_root: config.projectRoot,
		write_face_base: meta.writeFace?.base,
		write_face_entries: meta.writeFaceEntries ?? [],
		write_roots: meta.writeRoots ?? [],
		write_face_rejected: meta.writeFaceRejected ?? null,
		controlled_verdict: controlledVerdict,
		outside_verdict: outsideVerdict,
	};
}

function registerTestTools(pi: ExtensionAPI, state: ToolState): void {
	pi.registerTool({
		name: "write",
		label: "write",
		description: "isolated fixture write with real byte I/O and a read-back result",
		parameters: Type.Object({ path: Type.String(), content: Type.String() }),
		execute: async (toolCallId, params) => {
			const target = path.join(process.cwd(), params.path);
			await fs.promises.writeFile(target, Buffer.from(params.content, "utf8"));
			const observed = await fs.promises.readFile(target);
			const details: JsonRecord = {
				status: "written",
				path: params.path,
				bytes: observed.length,
				sha256: sha256Bytes(observed),
				content: observed.toString("utf8"),
				tool_call_id: toolCallId,
			};
			state.writes += 1;
			state.results.push(details);
			return { content: [{ type: "text" as const, text: `wrote ${params.path}:${observed.length}` }], details };
		},
	});
}

async function waitForQueue(store: WorkerStore, taskKey: string): Promise<JsonRecord | undefined> {
	const until = Date.now() + 3_000;
	while (Date.now() < until) {
		const row = store.readQueue().rows.find((item) => item.taskKey === taskKey);
		if (row !== undefined) return JSON.parse(JSON.stringify(row)) as JsonRecord;
		await new Promise((resolve) => setTimeout(resolve, 25));
	}
	return undefined;
}

async function waitForRegistered(composition: AgentTeamLoopComposition): Promise<number> {
	const until = Date.now() + 3_000;
	while (Date.now() < until) {
		const count = composition.host.countsSnapshot().registered;
		if (count >= 1) return count;
		await new Promise((resolve) => setTimeout(resolve, 25));
	}
	return composition.host.countsSnapshot().registered;
}

function jsonFiles(doc: string): string[] {
	const out: string[] = [];
	const walk = (dir: string): void => {
		if (!fs.existsSync(dir)) return;
		for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
			const full = path.join(dir, entry.name);
			if (entry.isDirectory()) walk(full);
			else if (entry.name.endsWith(".json")) out.push(path.relative(doc, full));
		}
	};
	walk(doc);
	return out.sort();
}

function cleanup(): void {
	delete process.env.PI_WORKER_TASK;
	process.chdir(originalCwd);
	resetActivationFlag();
	for (const h of harnesses.splice(0)) h.cleanup();
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
}

function asRecord(value: unknown): JsonRecord | undefined {
	return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as JsonRecord) : undefined;
}

function stableStringify(value: unknown): string {
	if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
	if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
	const record = value as Record<string, unknown>;
	return `{${Object.keys(record)
		.sort()
		.map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`)
		.join(",")}}`;
}

function targetDigest(sha: string): string {
	const manifest = [{ path: CONTROLLED_REL, state: "file", sha256: sha }];
	return `sha256:${crypto.createHash("sha256").update(JSON.stringify(manifest)).digest("hex")}`;
}

function persistedJoinFacts(
	f: Fixture,
	localRef: string | undefined,
	actionRef: string | undefined,
	workerRunId: string,
): JsonRecord {
	const resultRef = actionRef === undefined ? undefined : `tool_result:${actionRef}`;
	const dispositionRef = actionRef === undefined ? undefined : `disposition:${actionRef}`;
	const paths =
		localRef === undefined || dispositionRef === undefined
			? {}
			: {
					selection: storedRecordPath(
						f.doc,
						f.keyName,
						"worker-local",
						f.taskKey,
						localRef,
						SELECTION_FILE_SUFFIX,
					),
					execution: storedRecordPath(
						f.doc,
						f.keyName,
						"worker-local",
						f.taskKey,
						localRef,
						EXECUTION_FILE_SUFFIX,
					),
					disposition: storedRecordPath(
						f.doc,
						f.keyName,
						"worker-local",
						f.taskKey,
						dispositionRef,
						DISPOSITION_FILE_SUFFIX,
					),
				};
	const selection = typeof paths.selection === "string" ? readJsonRecord(paths.selection) : null;
	const execution = typeof paths.execution === "string" ? readJsonRecord(paths.execution) : null;
	const disposition = typeof paths.disposition === "string" ? readJsonRecord(paths.disposition) : null;
	const issues: string[] = [];
	if (localRef === undefined) issues.push("local_ref missing");
	if (actionRef === undefined) issues.push("action_ref missing");
	if (selection === null || selection.kind !== "local-selection" || selection.local_ref !== localRef)
		issues.push("persisted selection missing or not joined to local_ref");
	if (execution === null || execution.kind !== "local-execution" || execution.local_ref !== localRef)
		issues.push("persisted execution missing or not joined to local_ref");
	if (disposition === null || disposition.disposition_ref !== dispositionRef)
		issues.push("persisted disposition missing or not joined to disposition_ref");
	const selectionBinding = asRecord(selection?.host_binding);
	for (const [label, record] of [
		["execution", execution],
		["disposition", disposition],
	] as const) {
		const binding = asRecord(record?.[label === "disposition" ? "binding" : "host_binding"]);
		if (
			selectionBinding === undefined ||
			binding === undefined ||
			stableStringify(binding) !== stableStringify(selectionBinding)
		)
			issues.push(`${label} binding differs from selection`);
	}
	if (
		selectionBinding?.task_key !== f.taskKey ||
		selectionBinding?.key !== f.keyName ||
		selectionBinding?.run_id !== workerRunId
	)
		issues.push("selection host binding task/key/run mismatch");
	if (execution?.action_ref !== actionRef || execution?.result_ref !== resultRef)
		issues.push("execution action_ref/result_ref mismatch");
	if (execution?.executor !== JSON.stringify([workerRunId, actionRef])) issues.push("execution executor mismatch");
	if (execution?.effect_state !== "known") issues.push("execution effect_state is not known");
	const basisRefs = disposition?.basis_refs;
	if (!Array.isArray(basisRefs) || !basisRefs.includes(actionRef) || !basisRefs.includes(resultRef))
		issues.push("disposition does not cite the same action/result refs");
	return {
		outer_run_id: outerRunId,
		inner_run_id: innerRunId,
		key: f.keyName,
		task_key: f.taskKey,
		worker_run_id: workerRunId,
		local_ref: localRef ?? null,
		action_ref: actionRef ?? null,
		result_ref: resultRef ?? null,
		disposition_ref: dispositionRef ?? null,
		paths,
		selection,
		execution,
		disposition,
		issues,
		joined: issues.length === 0,
	};
}

it("one isolated L2 run writes one authorized file and joins action/result to execution/disposition", async () => {
	let status = "running";
	let firstFailure: FailureRecord | null = null;
	let workerActivated = false;
	let realActionResult = false;
	let errorText: string | null = null;
	const events: string[] = [];
	let snapshot: JsonRecord = { outer_run_id: outerRunId, inner_run_id: innerRunId, full_ac015: "NONE" };

	try {
		const f = fixture();
		process.chdir(f.root);
		resetActivationFlag();
		delete process.env.PI_WORKER_TASK;

		const beforeControlled = fs.readFileSync(f.controlledPath);
		const beforeOutside = fs.readFileSync(f.outsidePath);
		const beforeManifest = fileManifest(f.root);
		const declarations = declarationFacts(f);
		expect(declarations.card_write_face_entries).toEqual([CONTROLLED_REL]);
		expect(declarations.rendered_write_face_line).toBe(`write_face: ${CONTROLLED_REL}`);
		expect(declarations.envelope_write_face_line).toBe(`write_face: ${CONTROLLED_REL}`);
		expect(declarations.envelope_head_ok).toBe(true);
		expect(declarations.worker_cwd).toBe(f.root);
		expect(declarations.write_face_base).toBe(f.root);
		expect((declarations.controlled_verdict as JsonRecord).allowed).toBe(true);
		expect((declarations.outside_verdict as JsonRecord).allowed).toBe(false);

		const nativeConfig = nativeDecideConfig(f.root);
		const decideJson = JSON.parse(fs.readFileSync(path.join(f.root, ".mw", "decide.json"), "utf8")) as JsonRecord;
		const decidePoints = JSON.parse(
			fs.readFileSync(path.join(f.root, ".mw", "decide-points.json"), "utf8"),
		) as JsonRecord;
		const policy = readDecidePolicy(f.root);
		const configFacts = {
			decide_json: decideJson,
			decide_points: decidePoints,
			readDecidePolicy: policy,
			native_DecisionConfig: nativeConfig,
			all_points_disabled:
				typeof decidePoints.points === "object" &&
				decidePoints.points !== null &&
				Object.values(decidePoints.points as JsonRecord).every(
					(row) => row !== null && typeof row === "object" && (row as JsonRecord).enabled === false,
				),
		};
		expect(nativeConfig.enabled).toBe(false);
		expect(nativeConfig.signoff).toBe("auto");
		expect(policy.enabled).toBe(false);
		expect(configFacts.all_points_disabled).toBe(true);
		record({
			event: "L2_FIXTURE",
			fixture_root: f.root,
			card_sha256: f.cardSha256,
			config: configFacts,
			budget: { max_steps: 8, remaining_cost: 8, deadline: "run.json.started_at + 30m" },
			declarations,
			controlled_file: {
				path: CONTROLLED_REL,
				before_sha256: sha256Bytes(beforeControlled),
				before_bytes: beforeControlled.length,
			},
			outside_file: {
				path: OUTSIDE_REL,
				before_sha256: sha256Bytes(beforeOutside),
				before_bytes: beforeOutside.length,
			},
		});
		events.push("fixture-and-native-config");

		let pmComposition: AgentTeamLoopComposition | undefined;
		const pm = await createHarness({
			initialActiveToolNames: ["write", ASK_DECISION_TOOL, SUBMIT_DECISION_HANDOFF_TOOL],
			extensionFactories: [
				async (pi) => {
					pmComposition = await activateWithRuntimeHost(pi);
				},
			],
		});
		harnesses.push(pm);
		if (pmComposition === undefined) throw new Error("PM production host composition missing");
		const pmHost = pmComposition.host;
		expect(pmComposition.submitHandle.runtimeHost).toBe(pmHost);
		pm.sessionManager.appendCustomEntry(WATCH_ENTRY_TYPE, { key: f.keyName, claimed: false });
		await pm.session.bindExtensions({});
		await pm.session.extensionRunner.emit({ type: "agent_settled" });
		const registered = await waitForRegistered(pmComposition);
		const queueRow = await waitForQueue(new WorkerStore(f.doc), f.taskKey);
		if (registered !== 1 || queueRow === undefined)
			throw new Error(`PM dispatch not registered: registered=${registered} queue=${JSON.stringify(queueRow)}`);
		record({
			event: "L2_PM_DISPATCH",
			production_entry: "pm-orchestrator.ts:1601 via agent_settled handler at 2885-2895",
			registered_host_counts: pmHost.countsSnapshot(),
			queue_row: queueRow,
			submit_handle_is_same_host: true,
		});
		events.push("real-dispatchNewTasks-to-real-registerPmDispatch");
		pm.cleanup();
		harnesses.splice(harnesses.indexOf(pm), 1);
		resetActivationFlag();

		process.env.PI_WORKER_TASK = f.taskMdPath;
		let workerComposition: AgentTeamLoopComposition | undefined;
		const state: ToolState = { writes: 0, results: [] };
		const worker = await createHarness({
			initialActiveToolNames: ["write", ASK_DECISION_TOOL, SUBMIT_DECISION_HANDOFF_TOOL],
			extensionFactories: [
				async (pi) => {
					workerComposition = await activateWithRuntimeHost(pi);
					registerTestTools(pi, state);
				},
			],
		});
		harnesses.push(worker);
		if (workerComposition === undefined) throw new Error("worker production host composition missing");
		const workerHost = workerComposition.host;
		expect(workerComposition.submitHandle.runtimeHost).toBe(workerHost);
		await worker.session.bindExtensions({});
		const runStatePath = path.join(f.keyDir, "workers", f.taskKey, "run.json");
		const runState = JSON.parse(fs.readFileSync(runStatePath, "utf8")) as JsonRecord;
		const workerRegistered = workerHost.countsSnapshot().registered;
		workerActivated = workerRegistered === 1 && runState.status === "running";
		if (!workerActivated)
			throw new Error(
				`worker activation not registered: counts=${workerRegistered} run=${JSON.stringify(runState)}`,
			);
		record({
			event: "L2_WORKER_ACTIVATION",
			production_entry: "workerModeActivate registerWorkerActivation",
			run_state: runState,
			registered_host_counts: workerHost.countsSnapshot(),
		});
		events.push("real-worker-activation");

		const askArgs = {
			dp: "dp-w-check-task",
			trigger: f.taskKey,
			key: f.keyName,
			task_key: f.taskKey,
			note: "Isolated L2 first-entry slice: DP offline, signoff auto, finite budget, real PM dispatch host registration; no QG/sign/phase claims.",
			material: {
				task_goal: taskGoal,
				reachability_facts:
					"PM dispatch and worker activation are registered from real production host sources in one isolated run",
				completed: "isolated fixture, real PM dispatch registration and real worker activation",
				remaining: "one bounded controlled action and its result, then stop this minimal slice",
				blockers: "none known before the first business call",
				constraints: "existing active claim, finite card budget, DP offline and signoff=auto only",
			},
			preparation: {
				prepared_at: new Date().toISOString(),
				basis_catalog: [
					{
						id: "basis",
						text: "registered PM dispatch and worker activation bounds one controlled action",
						material_refs: ["reachability_facts"],
						applies_to: ["continue"],
					},
				],
			},
		};
		const submitArgs = { choice: "continue", basis_id: "basis" };
		const writeArgs = { path: CONTROLLED_REL, content: EXPECTED_CONTENT };
		worker.setResponses([
			fauxAssistantMessage([fauxToolCall(ASK_DECISION_TOOL, askArgs)], { stopReason: "toolUse" }),
			(context) => {
				const blob = JSON.stringify([context.messages, worker.session.messages]);
				const match = /offer:([0-9a-f]{40,})/.exec(blob);
				if (match === null) return fauxAssistantMessage("L2 slice stopped: no submittable offer");
				return fauxAssistantMessage(
					[fauxToolCall(SUBMIT_DECISION_HANDOFF_TOOL, { offer_id: `offer:${match[1]}`, ...submitArgs })],
					{ stopReason: "toolUse" },
				);
			},
			(context) => {
				const blob = JSON.stringify([context.messages, worker.session.messages]);
				const planned = blob.includes('"status":"planned"') && blob.includes('"business_completed":false');
				if (!planned) return fauxAssistantMessage("L2 slice stopped: local selection was not planned");
				return fauxAssistantMessage([fauxToolCall("write", writeArgs)], { stopReason: "toolUse" });
			},
			fauxAssistantMessage("L2 slice ended before QG, sign or phase."),
		]);
		await worker.session.prompt("one bounded isolated L2 slice");
		const askDetails = toolDetails(worker, ASK_DECISION_TOOL);
		const askText = toolResultText(worker, ASK_DECISION_TOOL);
		const offer = askDetails.submit_offer as JsonRecord | undefined;
		const submitDetails = toolDetails(worker, SUBMIT_DECISION_HANDOFF_TOOL);
		const submitText = toolResultText(worker, SUBMIT_DECISION_HANDOFF_TOOL);
		const writeDetails = toolDetails(worker, "write");
		const writeText = toolResultText(worker, "write");
		const writeCallId = toolCallId(worker, "write");
		const afterControlled = fs.readFileSync(f.controlledPath);
		const afterOutside = fs.readFileSync(f.outsidePath);
		const expectedHash = sha256Bytes(Buffer.from(EXPECTED_CONTENT, "utf8"));
		const controlledFacts = {
			path: CONTROLLED_REL,
			before_sha256: sha256Bytes(beforeControlled),
			after_sha256: sha256Bytes(afterControlled),
			expected_sha256: expectedHash,
			before_bytes: beforeControlled.length,
			after_bytes: afterControlled.length,
			content: afterControlled.toString("utf8"),
			content_ok: afterControlled.toString("utf8") === EXPECTED_CONTENT,
		};
		const outsideFacts = {
			path: OUTSIDE_REL,
			before_sha256: sha256Bytes(beforeOutside),
			after_sha256: sha256Bytes(afterOutside),
			unchanged: afterOutside.equals(beforeOutside),
		};
		const beforeManifestAfterPrompt = fileManifest(f.root);
		const localRef = typeof submitDetails.local_ref === "string" ? submitDetails.local_ref : undefined;
		const workerRunId = typeof runState.run_id === "string" ? runState.run_id : "";
		const joins = persistedJoinFacts(f, localRef, writeCallId, workerRunId);
		const expectedObservedEffect = `byte-manifest:${targetDigest(sha256Bytes(beforeControlled))}->${targetDigest(expectedHash)};business-correctness=unverified`;
		const counts: RuntimeHostCounts = workerHost.countsSnapshot();
		const producedJson = jsonFiles(f.doc);
		const executionRecord = asRecord(joins.execution);
		const dispositionRecord = asRecord(joins.disposition);
		const chainIssues: string[] = [...(joins.issues as string[])];
		if (!controlledFacts.content_ok)
			chainIssues.push("controlled file bytes do not equal the requested exact content");
		if (!outsideFacts.unchanged) chainIssues.push("outside file changed");
		if (state.writes !== 1 || state.results.length !== 1)
			chainIssues.push("write tool did not produce exactly one real result");
		if (
			writeDetails.status !== "written" ||
			writeDetails.sha256 !== expectedHash ||
			writeDetails.content !== EXPECTED_CONTENT
		)
			chainIssues.push("tool result details do not prove the exact read-back bytes");
		if (writeDetails.tool_call_id !== writeCallId) chainIssues.push("tool result tool_call_id mismatch");
		if (
			counts.reserves !== 1 ||
			counts.observes !== 1 ||
			counts.appends !== 1 ||
			counts.dispositions !== 1 ||
			counts.selectionCommits !== 1 ||
			counts.recordedWithDisposition !== 1 ||
			counts.unknowns !== 0 ||
			counts.blocks !== 0
		)
			chainIssues.push("production host/budget/execution/disposition counters are incomplete");
		if (
			executionRecord?.observed_effect !== expectedObservedEffect ||
			executionRecord?.target_digest !== targetDigest(expectedHash)
		)
			chainIssues.push("execution proof does not match the independent byte manifest");
		if (typeof executionRecord?.verified_by !== "string" || executionRecord.verified_by === "")
			chainIssues.push("execution verifier identity missing");
		if (dispositionRecord?.owner !== f.claim || dispositionRecord?.status !== "observed")
			chainIssues.push("disposition owner/status mismatch");
		record({
			event: "L2_BUSINESS_CALLS",
			ask_args: askArgs,
			ask_details: askDetails,
			ask_text: askText,
			submit_args: submitArgs,
			submit_details: submitDetails,
			submit_text: submitText,
			write_args: writeArgs,
			write_details: writeDetails,
			write_text: writeText,
			write_call_id: writeCallId,
			state,
			counts,
			controlled_file: controlledFacts,
			outside_file: outsideFacts,
			before_manifest: beforeManifest,
			prompt_manifest: beforeManifestAfterPrompt,
			joins,
			chain_issues: chainIssues,
			produced_json: producedJson,
		});
		events.push("business-calls-and-products");

		const rawWriteFailure = {
			write_args: writeArgs,
			write_details: writeDetails,
			write_text: writeText,
			write_call_id: writeCallId,
			guard_verdict: declarations.controlled_verdict,
			function: "worker-mode.ts::checkBashWriteScopeTarget via pi.on(tool_call)",
			source: "packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:2745-2780",
			narrow_fix:
				"keep one canonical project-root identity and one concrete write_face entry; do not widen production or the workspace face",
			counts,
		};
		if (askDetails.available !== false || offer?.submittable !== true || typeof offer.offer_id !== "string") {
			firstFailure = {
				stage: "ask_decision",
				code: String(askDetails.unavailable ?? askDetails.code ?? "no-submittable-offer"),
				call: "ask_decision",
				details: askDetails,
				text: askText,
			};
		} else if (submitDetails.status !== "planned" || submitDetails.business_completed !== false) {
			firstFailure = {
				stage: "submit_decision_handoff",
				code: String(submitDetails.code ?? submitDetails.status ?? "not-planned"),
				call: "submit_decision_handoff",
				details: submitDetails,
				text: submitText,
			};
		} else if (state.writes !== 1 || writeDetails.status !== "written") {
			firstFailure = {
				stage: "controlled_write",
				code: writeText.includes("write-scope") ? "write-scope" : "no-real-action-result",
				call: "write",
				details: rawWriteFailure,
				text: writeText,
			};
		} else if (counts.observes !== 1) {
			firstFailure = {
				stage: "execution_observation",
				code: "no-real-tool-result-observation",
				call: "write",
				details: rawWriteFailure,
				text: writeText,
			};
		} else if (counts.appends !== 1 || executionRecord === undefined) {
			firstFailure = {
				stage: "execution_archive",
				code: "execution-record-refused-or-missing",
				call: "write",
				details: { ...rawWriteFailure, joins },
				text: writeText,
			};
		} else if (counts.dispositions !== 1 || counts.recordedWithDisposition !== 1 || dispositionRecord === undefined) {
			firstFailure = {
				stage: "disposition_archive",
				code: "disposition-record-refused-or-missing",
				call: "write",
				details: { ...rawWriteFailure, joins },
				text: writeText,
			};
		} else if (chainIssues.length > 0) {
			firstFailure = {
				stage: "persisted_join",
				code: "action-result-execution-disposition-join-mismatch",
				call: "write",
				details: { ...rawWriteFailure, joins, chain_issues: chainIssues },
				text: writeText,
			};
		} else {
			realActionResult = true;
		}

		expect(workerActivated).toBe(true);
		expect(askDetails.available).toBe(false);
		if (firstFailure !== null) {
			status = "blocked";
			record({ event: "L2_FIRST_REFUSAL", first_failure: firstFailure });
			events.push("first-business-refusal-stop");
		} else {
			status = "advanced-to-action-result";
			events.push("real-action-and-result-without-QG-sign-phase");
		}
		expect(firstFailure).toBeNull();
		expect(status).toBe("advanced-to-action-result");
		expect(realActionResult).toBe(true);
		expect(chainIssues).toEqual([]);

		const finalRunState = JSON.parse(fs.readFileSync(runStatePath, "utf8")) as JsonRecord;
		const outputPath = path.join(f.keyDir, "workers", f.taskKey, "output.md");
		snapshot = {
			outer_run_id: outerRunId,
			inner_run_id: innerRunId,
			started_at: startedAt,
			ended_at: new Date().toISOString(),
			status,
			entry_path: entryPath,
			ownrun,
			events,
			fixture: {
				root: f.root,
				key: f.keyName,
				task_key: f.taskKey,
				card_path: "tasks/AC015-L2.md",
				card_sha256: f.cardSha256,
				budget: { max_steps: 8, remaining_cost: 8, deadline: "run.json.started_at + 30m" },
			},
			config: configFacts,
			declarations,
			controlled_file: controlledFacts,
			outside_file: outsideFacts,
			before_manifest: beforeManifest,
			prompt_manifest: beforeManifestAfterPrompt,
			pm: { registered_host_counts: pmHost.countsSnapshot(), queue_row: queueRow, submit_handle_is_same_host: true },
			worker: {
				activated: workerActivated,
				initial_run_state: runState,
				final_run_state: finalRunState,
				registered_host_counts: workerHost.countsSnapshot(),
				output_md_exists: fs.existsSync(outputPath),
			},
			produced: {
				ask_details: askDetails,
				submit_details: submitDetails,
				write_details: writeDetails,
				write_text: writeText,
				write_call_id: writeCallId,
				state,
				host_counts: counts,
				json_files: producedJson,
				joins,
				chain_issues: chainIssues,
			},
			first_failure: firstFailure,
			worker_activated: workerActivated,
			real_action_result: realActionResult,
			qg_sign_phase: "not-invoked",
			remaining_to_native_sign:
				"Native mw decide sign, QG, followup and phase Done were deliberately not invoked in this first slice; evidence-based ETA unknown.",
			full_ac015: "NONE",
			full_ac015_reason:
				"No complete same-run dispatch→worker→review→QG→followup→sign→Done chain was attempted or proved.",
		};
	} catch (err) {
		status = "error";
		errorText = err instanceof Error ? (err.stack ?? err.message) : String(err);
		record({ event: "L2_ERROR", error: errorText, first_failure: firstFailure });
		throw err;
	} finally {
		snapshot = { ...snapshot, status, error: errorText, ended_at: new Date().toISOString(), full_ac015: "NONE" };
		fs.writeFileSync(snapshotPath, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
		record({
			event: "L2_FINAL",
			status,
			worker_activated: workerActivated,
			real_action_result: realActionResult,
			first_failure: firstFailure,
			full_ac015: "NONE",
		});
		cleanup();
	}
});

it("isolated negative control refuses an out-of-face write with zero fixture effects", () => {
	const f = fixture();
	try {
		process.chdir(f.root);
		resetActivationFlag();
		delete process.env.PI_WORKER_TASK;
		const before = fileManifest(f.root);
		const config = guardConfigFor(f);
		const verdict = checkBashWriteScopeTarget(config, OUTSIDE_REL, true, "write");
		const expectedReason =
			`write-scope: blocked write to ${OUTSIDE_REL}: outside the task's declared write_face ` +
			`[rule=write-scope]; allowed: ${f.root}`;
		const after = fileManifest(f.root);
		const unchanged = JSON.stringify(before) === JSON.stringify(after);
		const facts: JsonRecord = {
			outer_run_id: outerRunId,
			inner_run_id: negativeInnerRunId,
			event: "L2_NEGATIVE_CONTROL",
			fixture_root: f.root,
			worker_cwd: process.cwd(),
			write_face_base: declarationFacts(f).write_face_base,
			card_write_face: [CONTROLLED_REL],
			requested_path: OUTSIDE_REL,
			verdict,
			expected_reason: expectedReason,
			before_manifest: before,
			after_manifest: after,
			fixture_unchanged: unchanged,
			positive_chain_invoked: false,
			writes: 0,
			real_action_result: false,
			full_ac015: "NONE",
		};
		fs.writeFileSync(negativeSnapshotPath, `${JSON.stringify(facts, null, 2)}\n`, "utf8");
		record({ ...facts, inner_run_id: negativeInnerRunId }, negativeEventsPath);
		expect(verdict.allowed).toBe(false);
		expect(verdict.rule).toBe("write-scope");
		expect(verdict.detail).toBe("outside-declared-write-face");
		expect(verdict.reason).toBe(expectedReason);
		expect(unchanged).toBe(true);
		expect(facts.positive_chain_invoked).toBe(false);
	} finally {
		cleanup();
	}
});
