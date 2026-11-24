import { execFileSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, describe, expect, it, vi } from "vitest";
import { answerPreparedGate } from "../../src/extensions/agent-team-loop/autopilot/gate-writer.ts";
import {
	deriveStatusModel,
	readWorkerReachability,
	renderStatusText,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import {
	type DecideRunner,
	type LifecycleRunner,
	registerAskDecisionTool,
} from "../../src/extensions/agent-team-loop/pm/decision-tool.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { createHarness, getMessageText, type Harness } from "./harness.ts";

const originals = new Map<string, string | undefined>();
const dirs: string[] = [];
const sessions: Harness[] = [];
const disposeBackstops: (() => void)[] = [];
const previousExit = process.exitCode;
const mwDir = path.resolve("../multi-workers");
const python = process.platform === "win32" ? "python" : "python3";
function runPython(args: string[], input?: string) {
	return execFileSync(python, ["-X", "utf8", "-B", ...args], {
		encoding: "utf8",
		input,
		env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
	});
}
function pythonFixture(root: string, body: string, ...args: string[]) {
	const script = path.join(root, "observe.py");
	fs.writeFileSync(
		script,
		`import sys, json
from pathlib import Path
sys.path.insert(0, sys.argv[1])
${body}
`,
	);
	return runPython([script, mwDir, ...args]);
}
afterEach(() => {
	vi.restoreAllMocks();
	for (const dispose of disposeBackstops.splice(0)) dispose();
	for (const h of sessions.splice(0)) h.cleanup();
	for (const [k, v] of originals) {
		if (v === undefined) delete process.env[k];
		else process.env[k] = v;
	}
	originals.clear();
	for (const d of dirs.splice(0)) fs.rmSync(d, { recursive: true, force: true });
	process.exitCode = previousExit;
});
function env(k: string, v: string) {
	if (!originals.has(k)) originals.set(k, process.env[k]);
	process.env[k] = v;
}
const openLedger = `import mw, decision, decision_lifecycle
root=Path(sys.argv[2])
cfg=mw._decide_config_snapshot(root)
store=mw._decide_lifecycle_store(root, cfg, decision.credential_snapshot(cfg))`;
async function fixture(choices: string[], realLedger = false, withFileEvidence = true) {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "dpc-t15-"));
	dirs.push(root);
	const dir = path.join(root, ".agenticdoc", "key-a", "workers", "read-card");
	fs.mkdirSync(dir, { recursive: true });
	const task = path.join(dir, "task.md");
	fs.writeFileSync(task, "---\ntype: coding\ntimeout: 5\n---\n\nReview the artifact.");
	if (realLedger) {
		const now = new Date().toISOString();
		fs.writeFileSync(
			path.join(root, ".agenticdoc", "_workers.parallel"),
			`# mw-queue:v2\nread-card | running | pi | faux | ${task} | ${now} | ${now} |  | manual\n`,
		);
	}
	const source = path.join(dir, "evidence.txt");
	fs.writeFileSync(source, "fixture decision evidence");
	env("PI_WORKER_TASK", task);
	const run = () => JSON.parse(fs.readFileSync(path.join(dir, "run.json"), "utf8"));
	const receipt: Record<string, unknown>[] = [];
	const observations: string[] = [];
	const lifecycle: LifecycleRunner = async (req) => {
		receipt.push(JSON.parse(req.input));
		if (realLedger) {
			const stdout = runPython(
				[path.join(mwDir, "mw.py"), "decide", "lifecycle", `--project=${root}`, "--stdin", "--json"],
				req.input,
			);
			return { status: 0, stdout, stderr: "", timedOut: false };
		}
		return { status: 0, stderr: "", stdout: JSON.stringify({ recorded: true, status: "written" }), timedOut: false };
	};
	const calls: string[] = [];
	const runner: DecideRunner = async (req) => {
		const { meta } = JSON.parse(req.input);
		calls.push(req.dp);
		const choice = choices.shift();
		if (realLedger) {
			pythonFixture(
				root,
				`${openLedger}
envelope = json.loads(sys.argv[3])
meta = decision_lifecycle.DecisionMeta.from_envelope(envelope)
dp, choice = "dp-w-check-task", sys.argv[4]
decision_id = dp + ":" + meta.logical_id
assert decision_lifecycle.record_start(store, meta, decision_id=decision_id).recorded
preparation = envelope["preparation"]
basis = preparation["basis_catalog"][0]
result = {"dp": dp, "available": True, "replayed": False, "choice": choice,
          "basis_id": basis["id"], "basis_text": basis["text"], "basis_source": "pm-prepared",
          "prepared_at": preparation["prepared_at"], "reason": None, "attempts": 1,
          "transport_attempts": 1, "business_decisions": 1}
assert decision_lifecycle.record_request(store, meta, decision_id=decision_id, result=result,
    material=envelope["material"], preparation=preparation).recorded`,
				root,
				req.input,
				choice ?? "",
			);
		}
		const reply: Record<string, unknown> = {
			available: true,
			mode: "auto",
			acted: false,
			decision_id: `${req.dp}:${meta.logical_id}`,
			answers: { reachability: { value: choice }, basis_id: { value: "basis" } },
		};
		if (withFileEvidence) reply.file_evidence = [];
		return {
			status: 0,
			stderr: "",
			timedOut: false,
			stdout: JSON.stringify(reply),
		};
	};
	const h = await createHarness({
		extensionFactories: [
			async (pi) => {
				pi.registerTool({
					name: "read",
					label: "Read evidence",
					description: "Read the named fixture",
					parameters: Type.Object({ path: Type.String() }),
					execute: async (_id, args) => {
						observations.push(run().status);
						return { content: [{ type: "text", text: fs.readFileSync(args.path, "utf8") }], details: {} };
					},
				});
				const existing = new Set(process.listeners("exit"));
				await workerModeActivate(pi, { reachabilityLifecycleRunner: lifecycle });
				// Each faux worker shares this Vitest process; dispose its own crash backstop.
				for (const listener of process.listeners("exit")) {
					if (!existing.has(listener)) disposeBackstops.push(() => process.off("exit", listener));
				}
				registerAskDecisionTool(pi, { projectDir: root, taskPath: task, runner, lifecycleRunner: lifecycle });
			},
		],
	});
	sessions.push(h);
	const ask = (
		choice: string,
		facts = "Only the in-scope artifacts are available",
		sourceOverride = source,
		stopCondition = "After reading evidence.txt",
	) => {
		const material = {
			task_goal: "Review the artifact",
			reachability_facts: facts,
			completed: "Read task.md",
			remaining: "Check artifact",
			blockers: "Missing upstream result",
			constraints: "Read the current task fixture only",
			investigation: {
				unknown: "Does evidence.txt contain the result?",
				evidence_source: sourceOverride,
				budget: "Within the existing 5 minute task",
				stop_condition: stopCondition,
			},
		};
		return fauxAssistantMessage(
			[
				fauxToolCall("ask_decision", {
					dp: "dp-w-check-task",
					trigger: "read-card",
					material,
					preparation: {
						prepared_at: "2026-10-25T10:00:00Z",
						basis_catalog: [
							{
								id: "basis",
								text: "Review current reachability evidence",
								material_refs: ["reachability_facts"],
								applies_to: [choice],
							},
						],
					},
				}),
			],
			{ stopReason: "toolUse" },
		);
	};
	const read = (file = source) =>
		fauxAssistantMessage([fauxToolCall("read", { path: file })], { stopReason: "toolUse" });
	return { h, ask, read, run, receipt, observations, calls, dir, root };
}
function toolResults(h: Harness) {
	return h.session.messages
		.filter((m) => m.role === "toolResult")
		.map((m) => ({
			text: getMessageText(m),
			details: (m as { details?: unknown }).details,
		}));
}
const observationNames = ["malformed-answer-result.json", "missing-metadata-result.json"] as const;
type ObservationName = (typeof observationNames)[number];
type OwnedObservationExport = {
	dir: string;
	ownerPath: string;
	ownerId: string;
};
type ObservationOwnerRecord = {
	owner: string;
	ownerId: string;
	pid: number;
	dir: string;
	names: string[];
};
type ObservationArchiveRequest = {
	envName: string;
	name: ObservationName;
	value: unknown;
	owned: OwnedObservationExport;
	source: string;
};
type ObservationArchiveResult = {
	marker: string;
	source: string;
	envName: string;
	configuredTarget: string | null;
	diagnosticOnly: true;
	name: ObservationName;
	path: string;
	status: "written" | "refused-existing" | "export-error";
	payload: unknown;
	bytes: number | null;
	sha256: string | null;
	payloadSha256: string;
	error?: string;
	ownership: {
		owner: string;
		ownerId: string;
		dir: string;
		ownerPath: string;
		ownerMarkerBytes: number;
		pid: number;
		cleanupRegistered: boolean;
		tmpRoot: string;
		insideOsTemp: boolean;
		outsideTaskDocTree: boolean;
		parent: string;
		relativeName: string;
	};
};
const observationOwner = "dp-consolidation-worker-owned-export";
function escapes(relativePath: string) {
	return relativePath === ".." || relativePath.startsWith(`..${path.sep}`) || path.isAbsolute(relativePath);
}
function createOwnedObservationExport(): OwnedObservationExport {
	const created = fs.mkdtempSync(path.join(os.tmpdir(), "dpc-t15-owned-observation-"));
	const dir = fs.realpathSync(created);
	dirs.push(dir);
	const ownerId = randomUUID();
	const ownerPath = path.join(dir, "owner.json");
	const record: ObservationOwnerRecord = {
		owner: observationOwner,
		ownerId,
		pid: process.pid,
		dir,
		names: [...observationNames],
	};
	fs.writeFileSync(ownerPath, JSON.stringify(record), { encoding: "utf8", flag: "wx" });
	return { dir, ownerPath, ownerId };
}
function assertOwnedTarget(owned: OwnedObservationExport, name: ObservationName) {
	const tmpRoot = fs.realpathSync(os.tmpdir());
	const dir = fs.realpathSync(owned.dir);
	const relTmp = path.relative(tmpRoot, dir);
	if (relTmp === "" || escapes(relTmp)) throw new Error("Owned observation export is outside OS temp");
	const relDocs = path.relative(path.resolve("..", "..", ".agenticdoc"), dir);
	if (!escapes(relDocs)) throw new Error("Owned observation export is inside the task doc tree");
	const record = JSON.parse(fs.readFileSync(owned.ownerPath, "utf8")) as ObservationOwnerRecord;
	if (
		record.owner !== observationOwner ||
		record.ownerId !== owned.ownerId ||
		record.pid !== process.pid ||
		record.dir !== dir ||
		!record.names.includes(name)
	) {
		throw new Error("Owned observation export owner marker mismatch");
	}
	const dirStats = fs.lstatSync(dir);
	if (!dirStats.isDirectory() || dirStats.isSymbolicLink())
		throw new Error("Owned observation export is not a concrete directory");
	const markerStats = fs.lstatSync(owned.ownerPath);
	if (!markerStats.isFile() || markerStats.isSymbolicLink())
		throw new Error("Owned observation export marker is not a concrete file");
	const target = path.join(dir, name);
	if (!path.isAbsolute(target) || path.dirname(target) !== dir || path.relative(dir, target) !== name) {
		throw new Error("Owned observation export target escaped its directory");
	}
	return { dir, target, tmpRoot, record };
}
function archiveObservation(request: ObservationArchiveRequest): ObservationArchiveResult {
	const { envName, name, value, owned, source } = request;
	const configuredTarget = process.env[envName] ?? null;
	const serialized = JSON.stringify(value, null, 2) ?? "{}";
	const payloadSha256 = createHash("sha256").update(serialized).digest("hex");
	const target = path.join(owned.dir, name);
	let status: ObservationArchiveResult["status"] = "written";
	let bytes: number | null = null;
	let sha256: string | null = null;
	let error: string | undefined;
	let ownership: ObservationArchiveResult["ownership"] = {
		owner: observationOwner,
		ownerId: owned.ownerId,
		dir: owned.dir,
		ownerPath: owned.ownerPath,
		ownerMarkerBytes: 0,
		pid: process.pid,
		cleanupRegistered: dirs.includes(owned.dir),
		tmpRoot: os.tmpdir(),
		insideOsTemp: false,
		outsideTaskDocTree: false,
		parent: owned.dir,
		relativeName: name,
	};
	try {
		const checked = assertOwnedTarget(owned, name);
		ownership = {
			owner: checked.record.owner,
			ownerId: checked.record.ownerId,
			dir: checked.dir,
			ownerPath: owned.ownerPath,
			ownerMarkerBytes: fs.statSync(owned.ownerPath).size,
			pid: checked.record.pid,
			cleanupRegistered: dirs.includes(owned.dir),
			tmpRoot: checked.tmpRoot,
			insideOsTemp: true,
			outsideTaskDocTree: true,
			parent: checked.dir,
			relativeName: name,
		};
		try {
			fs.writeFileSync(checked.target, serialized, { encoding: "utf8", flag: "wx" });
			bytes = Buffer.byteLength(serialized, "utf8");
			sha256 = payloadSha256;
		} catch (writeError) {
			if ((writeError as { code?: string }).code !== "EEXIST") throw writeError;
			const existing = fs.readFileSync(checked.target);
			status = "refused-existing";
			bytes = existing.length;
			sha256 = createHash("sha256").update(existing).digest("hex");
		}
	} catch (caught) {
		status = "export-error";
		error = caught instanceof Error ? caught.message : String(caught);
	}
	const result: ObservationArchiveResult = {
		marker: "MW_T06O_OBSERVATION_V1",
		source,
		envName,
		configuredTarget,
		diagnosticOnly: true,
		name,
		path: target,
		status,
		payload: value,
		bytes,
		sha256,
		payloadSha256,
		ownership,
	};
	if (error !== undefined) result.error = error;
	process.stdout.write(`MW_T06O_OBSERVATION_V1 ${JSON.stringify(result)}\n`);
	return result;
}
function firstLinePayload(results: ReturnType<typeof toolResults>) {
	return JSON.parse(results[0]?.text.split("\n")[0] ?? "{}") as Record<string, unknown>;
}
function firstDecisionFeedback(results: ReturnType<typeof toolResults>) {
	const line = results[0]?.text.split("\n")[1] ?? "{}";
	return (JSON.parse(line) as { decision_feedback?: Record<string, unknown> }).decision_feedback;
}
describe("real worker reachability", () => {
	it("continues with the same budget and records the first real action", async () => {
		const f = await fixture(["continue"]);
		f.h.setResponses([f.ask("continue"), f.read(), fauxAssistantMessage("Read evidence.txt.")]);
		await f.h.session.prompt("Run the task");
		expect(f.observations).toEqual(["running"]);
		expect(f.calls).toEqual(["dp-w-check-task"]);
		expect(f.receipt.map((r) => r.stage)).toEqual(["consumed", "executed", "settled"]);
		expect(f.receipt[1]).toMatchObject({
			action: "continue",
			task_after: { status: "running", source: "agent-report", completed: null, remaining: null, blockers: null },
			meta: { key: "key-a", task_key: "read-card", initiator_role: "coding" },
		});
	});
	it("ends an unreachable run with evidence and an existing incomplete terminal status", async () => {
		const f = await fixture(["terminate"], true);
		f.h.setResponses([f.ask("terminate"), fauxAssistantMessage("No further action")]);
		await f.h.session.prompt("Run the task");
		expect(f.run()).toMatchObject({
			status: "failed",
			exit: 1,
			reachability: {
				choice: "terminate",
				completed: "Read task.md",
				remaining: "Check artifact",
				blockers: "Missing upstream result",
			},
		});
		const output = fs.readFileSync(path.join(f.dir, "output.md"), "utf8");
		expect(output).toContain("Missing upstream result");
		expect(f.receipt[1]).toMatchObject({
			task_after: {
				status: "failed",
				source: "agent-report",
				completed: ["Read task.md"],
				remaining: ["Check artifact"],
				blockers: ["Missing upstream result"],
			},
		});
		const rows = JSON.parse(
			pythonFixture(
				f.root,
				`${openLedger}
print(json.dumps(list(decision_lifecycle.read_lifecycle(store).events)))`,
				f.root,
			),
		) as { kind: string; lifecycle?: string; logical_id: string; task_after?: { status: string } }[];
		expect(rows.map((r) => r.lifecycle ?? r.kind)).toEqual([
			"record-start",
			"request",
			"consumed",
			"executed",
			"settled",
		]);
		expect(rows[3].task_after?.status).toBe("failed");
		expect(rows.every((r) => r.logical_id === f.run().reachability.decision_id.split(":")[1])).toBe(true);
		const ts = readWorkerReachability(f.dir, "key-a", "read-card");
		expect(ts).toMatchObject({ choice: "terminate", decisionId: f.run().reachability.decision_id });
		const observed = JSON.parse(
			pythonFixture(
				f.root,
				"from mw_common import read_worker_reachability\nprint(json.dumps(read_worker_reachability(Path(sys.argv[2]), 'key-a', 'read-card')))",
				f.dir,
			),
		);
		expect(observed).toMatchObject({
			choice: "terminate",
			decision_id: ts?.decisionId,
			evidence: ts?.evidence,
			run_id: f.run().run_id,
		});
		expect(output).toContain("Only the in-scope artifacts are available");
		expect(f.receipt.map((r) => r.stage)).toEqual(["consumed", "executed", "settled"]);
	});
	it("requires the real bounded observation before a fresh decision, then terminates with that evidence", async () => {
		const f = await fixture(["investigate", "terminate"]);
		f.h.setResponses([
			f.ask("investigate"),
			f.read(path.join(f.dir, "task.md")),
			f.read(),
			f.ask("terminate", "Read evidence.txt; the required upstream result is absent."),
			fauxAssistantMessage("Stop"),
		]);
		await f.h.session.prompt("Run the task");
		expect(f.observations).toEqual(["running"]);
		expect(f.calls).toEqual(["dp-w-check-task", "dp-w-check-task"]);
		expect(f.run()).toMatchObject({ status: "failed", reachability: { choice: "terminate" } });
		expect(
			f.h.session.messages
				.filter((m) => m.role === "toolResult")
				.map(getMessageText)
				.join("\n"),
		).toContain("evidence_source");
		expect(f.receipt.filter((r) => r.stage === "executed")).toHaveLength(2);
	});
});
describe("reachability boundaries and persisted gate axes", () => {
	it("refuses a malformed child answer without a choice, id, or action", async () => {
		const f = await fixture([]);
		f.h.setResponses([f.ask("continue"), f.read(), fauxAssistantMessage("Cannot proceed")]);
		await f.h.session.prompt("Run the task");
		expect(f.observations).toEqual([]);
		expect(f.receipt).toEqual([]);
		expect(f.run()).toMatchObject({ status: "failed", exit: 1, reachability: { decision_id: null, choice: null } });
		expect(f.run().reachability.reason).toContain("bad-response");
		const malformedResults = toolResults(f.h);
		const malformedPayload = firstLinePayload(malformedResults);
		const malformedArchive = archiveObservation({
			envName: "MW_T06F_MALFORMED_OBSERVATION",
			name: "malformed-answer-result.json",
			value: { toolResults: malformedResults, firstLinePayload: malformedPayload },
			owned: createOwnedObservationExport(),
			source: "worker-case",
		});
		expect((malformedPayload.missing_fields as string[] | undefined) ?? []).not.toContain("file_evidence");
		expect(malformedArchive.status).toBe("written");
	});
	it("does not let an agent self-receipt an unexecuted reachability action", async () => {
		const f = await fixture(["continue"]);
		f.h.setResponses([
			f.ask("continue"),
			() =>
				fauxAssistantMessage(
					[
						fauxToolCall("decision_receipt", {
							decision_id: f.receipt[0].decision_id,
							stage: "executed",
							action: "continue",
							result: "Model claims it continued",
						}),
					],
					{ stopReason: "toolUse" },
				),
			f.read(),
			fauxAssistantMessage("Finished"),
		]);
		await f.h.session.prompt("Run the task");
		expect(f.receipt.map((r) => r.stage)).toEqual(["consumed", "executed", "settled"]);
		expect(f.receipt[1].result).toContain("authorized read");
	});
	it("ends the run without an execution receipt when the terminal product cannot be written", async () => {
		const f = await fixture(["terminate"]);
		fs.mkdirSync(path.join(f.dir, "output.md"));
		f.h.setResponses([f.ask("terminate"), fauxAssistantMessage("Stop")]);
		await f.h.session.prompt("Run the task");
		expect(f.run()).toMatchObject({ status: "failed", exit: 1 });
		expect(f.receipt.map((r) => r.stage)).toEqual(["consumed"]);
		expect(fs.readFileSync(path.join(f.dir, "trace.log"), "utf8")).toContain("terminal output unavailable");
	});
	it("refuses to project a terminal claim without its run identity", async () => {
		const f = await fixture(["terminate"]);
		f.h.setResponses([f.ask("terminate"), fauxAssistantMessage("Stop")]);
		await f.h.session.prompt("Run the task");
		const record = f.run();
		delete record.run_id;
		fs.writeFileSync(path.join(f.dir, "run.json"), JSON.stringify(record));
		expect(readWorkerReachability(f.dir, "key-a", "read-card")).toBeUndefined();
		expect(
			JSON.parse(
				pythonFixture(
					f.root,
					"from mw_common import read_worker_reachability\nprint(json.dumps(read_worker_reachability(Path(sys.argv[2]), 'key-a', 'read-card')))",
					f.dir,
				),
			),
		).toBeNull();
	});
	it("requires a prepared stop condition before dispatch and cannot read a substitute", async () => {
		const f = await fixture(["investigate"]);
		f.h.setResponses([
			f.ask("investigate", "unknown", path.join(f.dir, "evidence.txt"), ""),
			f.read(),
			fauxAssistantMessage("No supported probe"),
		]);
		await f.h.session.prompt("Run the task");
		expect(f.calls).toEqual([]);
		expect(f.observations).toEqual([]);
		expect(f.receipt).toEqual([]);
		expect(f.run()).toMatchObject({ status: "failed", reachability: { choice: null, decision_id: null } });
	});
	it("blocks the pending read when the original task deadline has passed", async () => {
		const f = await fixture(["investigate"]);
		f.h.setResponses([
			f.ask("investigate"),
			() => {
				vi.spyOn(Date, "now").mockReturnValue(Date.now() + 6 * 60_000);
				return f.read();
			},
			fauxAssistantMessage("Deadline reached"),
		]);
		await f.h.session.prompt("Run the task");
		expect(f.observations).toEqual([]);
		expect(f.receipt.map((r) => r.stage)).toEqual(["consumed"]);
		expect(f.run().reachability.reason).toContain("budget has expired");
	});
	it("refuses an existing file outside this worker's authority", async () => {
		const f = await fixture(["investigate"]);
		const other = fs.mkdtempSync(path.join(os.tmpdir(), "t15-outside-"));
		dirs.push(other);
		const foreignFile = path.join(other, "evidence.txt");
		fs.writeFileSync(foreignFile, "foreign evidence");
		f.h.setResponses([
			f.ask("investigate", "unknown", foreignFile),
			f.read(foreignFile),
			fauxAssistantMessage("Stop"),
		]);
		await f.h.session.prompt("Run the task");
		expect(f.observations).toEqual([]);
		expect(f.receipt.map((r) => r.stage)).toEqual(["consumed"]);
		expect(f.run().reachability.reason).toContain("outside");
	});
	it("does not grant a nonexistent evidence source or record an action", async () => {
		const f = await fixture(["investigate"]);
		f.h.setResponses([
			f.ask("investigate", "Missing result", path.join(f.dir, "absent.txt")),
			f.read(),
			fauxAssistantMessage("No in-scope evidence"),
		]);
		await f.h.session.prompt("Run the task");
		expect(f.observations).toEqual([]);
		expect(f.receipt.map((r) => r.stage)).toEqual(["consumed"]);
		expect(f.run()).toMatchObject({ status: "failed", reachability: { choice: "investigate" } });
		expect(f.run().reachability.reason).toContain("unavailable");
	});
	it("continues after real evidence and keeps the same run open for the next action", async () => {
		const f = await fixture(["investigate", "continue"]);
		f.h.setResponses([
			f.ask("investigate"),
			f.read(),
			f.ask("continue", "The required evidence is present in evidence.txt"),
			f.read(),
			fauxAssistantMessage("Finished"),
		]);
		await f.h.session.prompt("Run the task");
		expect(f.observations).toEqual(["running", "running"]);
		expect(f.receipt.filter((r) => r.stage === "executed").map((r) => r.action)).toEqual(["record", "continue"]);
	});
	it("reads a prepared gate across Python creation, TS answer, CLI and status without inferring an effect", async () => {
		const root = fs.mkdtempSync(path.join(os.tmpdir(), "t15-gate-"));
		dirs.push(root);
		const [legacy, prepared] = JSON.parse(
			pythonFixture(
				root,
				`from autopilot.gates import create
gates=Path(sys.argv[2])/".agenticdoc"/"_autopilot"/"gates"
gates.mkdir(parents=True)
a=create(gates, "stage-confirm", "Check stage?", key="key-a")
b=create(gates, "stage-confirm", "Resolve scope?", key="key-a", pm_note="Review existing scope", matter_ref="scope", substantive_version="v1")
print(json.dumps([str(a),str(b)]))`,
				root,
			),
		);
		const old = fs.readFileSync(legacy);
		const cli = () =>
			JSON.parse(runPython([path.join(mwDir, "mw.py"), "autopilot", "gates", `--project=${root}`, "--json"]));
		expect(cli()).toMatchObject({
			pending_count: 2,
			decisions: [{ transport: "pending", business: null, effect: "not-started" }],
		});
		const lockFile = path.join(root, ".mw", "gates.lock");
		fs.mkdirSync(path.dirname(lockFile), { recursive: true });
		const answered = await answerPreparedGate({
			gateFile: prepared,
			lockFile,
			answeredBy: "fixture:25",
			decision: "steer",
			modelBasis: "The scope is incomplete",
			decisionRef: "dp-gate-approve:073d4de2-486d-43aa-a8ab-c235cc69c9a7",
			matterRef: "scope",
			substantiveVersion: "v1",
		});
		expect(answered).toMatchObject({ ok: true, status: "pending" });
		expect(cli()).toMatchObject({
			pending_count: 1,
			decisions: [{ transport: "answered", business: "steer", effect: "not-started", closure_kind: null }],
		});
		const parsed = deriveStatusModel(root);
		if (!parsed.ok) throw Error(parsed.error);
		expect(parsed.model.status.gates[0].decision).toBeUndefined();
		expect(parsed.model.status.gates[1]).toMatchObject({
			status: "pending",
			decision: { transport: "answered", business: "steer", effect: "not-started" },
		});
		expect(renderStatusText(parsed.model)).toContain("transport=answered business=steer effect=not-started");
		expect(fs.readFileSync(legacy)).toEqual(old);
	});
	it("refuses an available reply without file_evidence metadata before any action or receipt", async () => {
		const f = await fixture(["continue"], false, false);
		f.h.setResponses([f.ask("continue"), f.read(), fauxAssistantMessage("Cannot proceed")]);
		await f.h.session.prompt("Run the task");
		const results = toolResults(f.h);
		const payload = firstLinePayload(results);
		const feedback = firstDecisionFeedback(results);
		const code = {
			unavailable: payload.unavailable,
			action: payload.action,
			missing_fields: payload.missing_fields,
			feedback_category: feedback?.category,
			feedback_raw_reason: feedback?.raw_reason,
			feedback_gaps: feedback?.gaps,
		};
		const missingArchive = archiveObservation({
			envName: "MW_T06F_OBSERVATION",
			name: "missing-metadata-result.json",
			value: { toolResults: results, firstLinePayload: payload, decisionFeedback: feedback, code },
			owned: createOwnedObservationExport(),
			source: "worker-case",
		});
		expect(payload).toMatchObject({
			available: false,
			unavailable: "bad-response",
			action: "blocked-ask-human",
			missing_fields: ["file_evidence"],
		});
		expect(code.unavailable).toBe("bad-response");
		expect(results[0]?.text).toContain("file_evidence");
		expect(f.observations).toEqual([]);
		expect(f.receipt).toEqual([]);
		expect(f.calls).toEqual(["dp-w-check-task"]);
		expect(String(f.run().reachability.reason ?? "")).toContain("bad-response");
		expect(missingArchive.status).toBe("written");
	});
});
describe("owned observation export isolation", () => {
	it("keeps an existing inherited observation destination diagnostic and preserves a fresh sentinel", () => {
		const sentinelRoot = fs.mkdtempSync(path.join(os.tmpdir(), "dpc-t15-sentinel-"));
		dirs.push(sentinelRoot);
		const sentinel = path.join(sentinelRoot, "stale-observation.json");
		const sentinelBytes = "W9O fresh sentinel: never overwrite\n";
		fs.writeFileSync(sentinel, sentinelBytes, { encoding: "utf8", flag: "wx" });
		env("MW_T06F_MALFORMED_OBSERVATION", sentinel);
		const value = {
			toolResults: [
				{ text: "sentinel observation\nfull tool text", details: { case: "sentinel", nested: { kept: true } } },
			],
			firstLinePayload: { unavailable: "bad-response" },
		};
		const archive = archiveObservation({
			envName: "MW_T06F_MALFORMED_OBSERVATION",
			name: "malformed-answer-result.json",
			value,
			owned: createOwnedObservationExport(),
			source: "regression",
		});
		expect(archive.status).toBe("written");
		expect(archive.configuredTarget).toBe(sentinel);
		expect(archive.path).not.toBe(sentinel);
		expect(archive.diagnosticOnly).toBe(true);
		expect(fs.readFileSync(sentinel, "utf8")).toBe(sentinelBytes);
		expect(JSON.parse(fs.readFileSync(archive.path, "utf8"))).toEqual(value);
		expect(archive.payload).toEqual(value);
		expect(archive.ownership.cleanupRegistered).toBe(true);
		expect(archive.ownership.insideOsTemp).toBe(true);
		expect(archive.ownership.outsideTaskDocTree).toBe(true);
		expect(fs.existsSync(archive.ownership.ownerPath)).toBe(true);
	});
	it("does not create or write an inherited destination whose parent is absent", () => {
		const root = fs.mkdtempSync(path.join(os.tmpdir(), "dpc-t15-absent-parent-"));
		dirs.push(root);
		const absentTarget = path.join(root, "absent-parent", "stale-observation.json");
		env("MW_T06F_OBSERVATION", absentTarget);
		const value = {
			toolResults: [
				{
					text: "missing file_evidence\nfull tool text",
					details: { case: "absent-parent", nested: { kept: true } },
				},
			],
			firstLinePayload: { unavailable: "bad-response", missing_fields: ["file_evidence"] },
			decisionFeedback: { category: "service-unavailable", raw_reason: "bad-response" },
			code: { missing_fields: ["file_evidence"] },
		};
		const archive = archiveObservation({
			envName: "MW_T06F_OBSERVATION",
			name: "missing-metadata-result.json",
			value,
			owned: createOwnedObservationExport(),
			source: "regression",
		});
		expect(archive.status).toBe("written");
		expect(archive.configuredTarget).toBe(absentTarget);
		expect(fs.existsSync(absentTarget)).toBe(false);
		expect(fs.existsSync(path.dirname(absentTarget))).toBe(false);
		expect(fs.readFileSync(archive.path, "utf8")).toContain("file_evidence");
		expect(JSON.parse(fs.readFileSync(archive.path, "utf8"))).toEqual(value);
		expect(archive.ownership.cleanupRegistered).toBe(true);
		expect(archive.ownership.outsideTaskDocTree).toBe(true);
	});
	it("keeps independent exports distinct and refuses a same-owned-file overwrite", () => {
		const sentinelRoot = fs.mkdtempSync(path.join(os.tmpdir(), "dpc-t15-shared-"));
		dirs.push(sentinelRoot);
		const shared = path.join(sentinelRoot, "shared-stale-observation.json");
		const sharedBytes = "W9O shared stale diagnostic: preserve\n";
		fs.writeFileSync(shared, sharedBytes, { encoding: "utf8", flag: "wx" });
		env("MW_T06F_MALFORMED_OBSERVATION", shared);
		env("MW_T06F_OBSERVATION", shared);
		const first = createOwnedObservationExport();
		const second = createOwnedObservationExport();
		const malformedValue = {
			toolResults: [{ text: "malformed answer\nfull text", details: { case: "malformed", nested: { kept: true } } }],
			firstLinePayload: { unavailable: "bad-response" },
		};
		const missingValue = {
			toolResults: [
				{ text: "missing file_evidence\nfull text", details: { case: "missing", nested: { kept: true } } },
			],
			firstLinePayload: { unavailable: "bad-response", missing_fields: ["file_evidence"] },
			decisionFeedback: { category: "service-unavailable", raw_reason: "bad-response" },
			code: { missing_fields: ["file_evidence"] },
		};
		const firstMalformed = archiveObservation({
			envName: "MW_T06F_MALFORMED_OBSERVATION",
			name: "malformed-answer-result.json",
			value: malformedValue,
			owned: first,
			source: "regression",
		});
		const firstMissing = archiveObservation({
			envName: "MW_T06F_OBSERVATION",
			name: "missing-metadata-result.json",
			value: missingValue,
			owned: first,
			source: "regression",
		});
		const secondMalformed = archiveObservation({
			envName: "MW_T06F_MALFORMED_OBSERVATION",
			name: "malformed-answer-result.json",
			value: malformedValue,
			owned: second,
			source: "regression",
		});
		const secondMissing = archiveObservation({
			envName: "MW_T06F_OBSERVATION",
			name: "missing-metadata-result.json",
			value: missingValue,
			owned: second,
			source: "regression",
		});
		const repeatValue = { toolResults: [{ text: "repeat attempt\nmust not truncate", details: { case: "repeat" } }] };
		const repeated = archiveObservation({
			envName: "MW_T06F_MALFORMED_OBSERVATION",
			name: "malformed-answer-result.json",
			value: repeatValue,
			owned: first,
			source: "regression",
		});
		expect([firstMalformed, firstMissing, secondMalformed, secondMissing].map((item) => item.status)).toEqual([
			"written",
			"written",
			"written",
			"written",
		]);
		expect(repeated.status).toBe("refused-existing");
		expect(first.dir).not.toBe(second.dir);
		expect(firstMalformed.path).not.toBe(secondMalformed.path);
		expect(firstMalformed.name).not.toBe(firstMissing.name);
		expect(fs.readFileSync(shared, "utf8")).toBe(sharedBytes);
		expect(fs.readFileSync(firstMalformed.path, "utf8")).toBe(JSON.stringify(malformedValue, null, 2));
		expect(fs.readFileSync(repeated.path, "utf8")).toBe(JSON.stringify(malformedValue, null, 2));
		expect(JSON.parse(fs.readFileSync(firstMissing.path, "utf8"))).toEqual(missingValue);
		expect(firstMalformed.payload).toEqual(malformedValue);
		expect(firstMissing.payload).toEqual(missingValue);
		expect(firstMalformed.payload).not.toEqual(firstMissing.payload);
		expect(repeated.payload).toEqual(repeatValue);
		expect(
			[firstMalformed, firstMissing, secondMalformed, secondMissing, repeated].every(
				(item) => item.ownership.cleanupRegistered,
			),
		).toBe(true);
	});
});
