/**
 * write-face-e2e.test.ts — W-07/B3: end-to-end parity of the two write-face
 * dispatch channels (PM `pm/task-dispatcher.ts::dispatchTask` and conductor
 * `autopilot/dispatch.py::_write_face_verdict`), plus the AC-005 reverse proof
 * and the AC-013 two-sided table.
 *
 * Card: `.agenticdoc/mw-write-face-guard/tasks/T-W-I12-e2e-parity.md`
 *
 * What is pinned here (the PM mirror of `packages/multi-workers/test/test_write_face_e2e.py`):
 *
 * - ① the frozen corpus (`test/fixtures/write-face-corpus.json`) is fed through
 *   ONE device: the same in-flight queue row + the same candidate task.md text
 *   go to the PM entry (in-process, read-only import) and to the conductor entry
 *   (spawned through the resolved Python interpreter, read-only import, no Python
 *   source is written). The verdicts are compared field by field:
 *   `ok` / `code` / `overlap-with:<task_key>` / `sample` / `serial-only`.
 * - ①b the alignment lesson: the previous PM differential produced 4 false
 *   inconsistencies because the two sides were given DIFFERENT bases
 *   (`evidence/PM-parity-differential-20261014.md` §0). The device makes the
 *   misalignment reproducible and counts it, then proves the aligned run is 0.
 * - ② AC-005 reverse proof (PM channel): same time, same key, same file -> 0
 *   multi-writer pairs; a gate-bypassing queue write makes the recomputed count
 *   > 0 (the detector is not self-proving).
 * - ③ AC-013 both directions: the true-write family is blocked on the runtime
 *   `write`/`edit` and `bash` call paths, the false-write family
 *   (`Write-Output a <term> --glob x`, PowerShell here-strings, read-only
 *   commands) passes; the gate side is covered by the same false-write bodies
 *   through the parity device.
 *
 * Pure filesystem + subprocess: no provider APIs, no credentials.
 */

import { spawnSync } from "node:child_process";
import * as crypto from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { TERMINAL_WORKER_STATUSES } from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import {
	type DispatchRefusal,
	dispatchTask,
	writeFaceBase,
	writeFaceCaseInsensitive,
} from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import { resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";
import { type WorkerEntry, WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import {
	parseWriteFace,
	type WriteFace,
	writeFacesOverlap,
} from "../../src/extensions/agent-team-loop/shared/write-face.ts";
import {
	type BashWriteScopeConfig,
	checkBashWriteScopeTarget,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url)).replace(/[\\/]+$/, "");
const CORPUS_PATH = path.join(MULTI_WORKERS_DIR, "test", "fixtures", "write-face-corpus.json");
// LF-normalized fingerprint of the frozen corpus (the Windows file is CRLF, 20126 B).
const CORPUS_SHA256_LF = "b39f89250c39177f9638e8d3ecddfce176dcaf846648a2ea1e9afebb479d6a62";
const CORPUS_COUNTS = { parse: 23, overlap: 59 } as const;

const OWNER = "wfk-e2e";
const CAND = "w-new";
const INFLIGHT = "w-keep";
const CARD_PATH = "tasks/T-W-I12-e2e.md";

const PROCEED: Verdict = { ok: true, code: null, overlapWith: null, sample: null, serialOnly: false };

/**
 * AC-013 false-write family (mirrors `write-face-runtime.test.ts`): text that
 * looks like a write but is not, so the gate (body text) and the runtime guard
 * (bash text) must both let it through.
 */
const FALSE_WRITE_VECTORS = [
	"Write-Output a <term> --glob x",
	"Write-Output a <term>",
	`Write-Output "probe: <term> --glob '!x' done"`,
	"$code = @'\ndon't do x > y\n'@\nWrite-Output $code",
	'[[ "$ts" > "2026-01-01" ]]',
	'echo "a > b"',
	`bash -c "grep -n '>' f"`,
	"rg -n -F TERM --glob '!node_modules' .",
	"echo x 2>&1",
	"Get-Content a.txt > /dev/null",
	"echo x > $null",
];
const READ_ONLY_COMMANDS = ["rg -n foo packages", "cat package.json", "git status --porcelain"];

// ── types ───────────────────────────────────────────────────────────────────

interface Verdict {
	ok: boolean;
	code: string | null;
	overlapWith: string | null;
	sample: string | null;
	serialOnly: boolean;
}

interface QueueRow {
	task_key: string;
	status: string;
	cli: string;
	provider: string;
	task_path: string;
	dispatched_at: string;
	updated_at: string;
	model: string;
	origin: string;
}

interface CorpusParseRow {
	name: string;
	head: string[];
	expect: { kind: string; entries?: string[]; code?: string };
}
interface CorpusOverlapRow {
	name: string;
	a: string[] | null;
	b: string[] | null;
	a_deny?: string[];
	case_insensitive: boolean;
	expect: { kind: string; side?: string; code?: string; sample_globfree?: boolean };
}
interface Corpus {
	parse: CorpusParseRow[];
	overlap: CorpusOverlapRow[];
}

interface E2ECase {
	name: string;
	kind: "parse" | "overlap";
	a: string[] | null;
	b: string[] | null;
	candidate: string;
	inflight: string | null;
	taskKey: string;
	taskPath: string;
	inflightKey: string | null;
	inflightPath: string | null;
}

const tempDirs: string[] = [];

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function corpus(): Corpus {
	return JSON.parse(fs.readFileSync(CORPUS_PATH, "utf8")) as Corpus;
}

function readCorpusFingerprint(): string {
	const normalized = fs.readFileSync(CORPUS_PATH, "utf8").replace(/\r\n/g, "\n");
	return crypto.createHash("sha256").update(normalized, "utf8").digest("hex");
}

// ── device: one in-flight context + one candidate write face per case ────────

function subst(text: string, project: string, outside: string): string {
	return text.split("$REPO").join(project).split("$OUTSIDE").join(outside);
}

/** The D-113 carrier: comma-safe block list; `-` for declared-but-empty; nothing
 * when the face is undeclared. */
function faceHead(entries: string[] | null, name = "write_face"): string {
	if (entries === null) return "";
	if (entries.length === 0) return `${name}: -\n`;
	return `${name}:\n${entries.map((entry) => `  - ${entry}\n`).join("")}`;
}

function buildCases(input: Corpus, project: string, outside: string): E2ECase[] {
	const cases: E2ECase[] = [];
	for (const row of input.parse) {
		const head = row.head.map((line) => subst(line, project, outside)).join("\n");
		cases.push({
			name: row.name,
			kind: "parse",
			a: null,
			b: null,
			candidate: `card_path: ${CARD_PATH}\n${head}\n\nbody\n`,
			inflight: null,
			taskKey: "",
			taskPath: "",
			inflightKey: null,
			inflightPath: null,
		});
	}
	for (const row of input.overlap) {
		const a = row.a === null ? null : row.a.map((entry) => subst(entry, project, outside));
		const b = row.b === null ? null : row.b.map((entry) => subst(entry, project, outside));
		const deny = (row.a_deny ?? []).map((entry) => subst(entry, project, outside));
		const candidate =
			`card_path: ${CARD_PATH}\n` +
			faceHead(a) +
			faceHead(deny.length > 0 ? deny : null, "write_face_deny") +
			"\nbody\n";
		cases.push({
			name: row.name,
			kind: "overlap",
			a,
			b,
			candidate,
			inflight: b === null ? null : `${faceHead(b)}\nbody\n`,
			taskKey: "",
			taskPath: "",
			inflightKey: null,
			inflightPath: null,
		});
	}
	return cases;
}

function materialize(cases: E2ECase[], project: string): string {
	const agenticdoc = path.join(project, ".agenticdoc");
	cases.forEach((item, index) => {
		const taskKey = `${CAND}-${String(index).padStart(3, "0")}`;
		const taskPath = path.join(agenticdoc, OWNER, "workers", taskKey, "task.md");
		fs.mkdirSync(path.dirname(taskPath), { recursive: true });
		fs.writeFileSync(taskPath, item.candidate, "utf8");
		item.taskKey = taskKey;
		item.taskPath = taskPath;
		if (item.inflight !== null) {
			const inflightKey = `${INFLIGHT}-${String(index).padStart(3, "0")}`;
			const inflightPath = path.join(agenticdoc, OWNER, "workers", inflightKey, "task.md");
			fs.mkdirSync(path.dirname(inflightPath), { recursive: true });
			fs.writeFileSync(inflightPath, item.inflight, "utf8");
			item.inflightKey = inflightKey;
			item.inflightPath = inflightPath;
		}
	});
	return agenticdoc;
}

function queueRows(item: E2ECase): QueueRow[] {
	if (item.inflightKey === null || item.inflightPath === null) return [];
	return [
		{
			task_key: item.inflightKey,
			status: "running",
			cli: "pi",
			provider: "timi",
			task_path: item.inflightPath,
			dispatched_at: "2026-10-14T00:00:00.000Z",
			updated_at: "2026-10-14T00:00:00.000Z",
			model: "",
			origin: "manual",
		},
	];
}

function resetQueue(agenticdoc: string, rows: QueueRow[]): void {
	const queue = path.join(agenticdoc, "_workers.parallel");
	if (rows.length === 0) {
		fs.rmSync(queue, { force: true });
		return;
	}
	fs.mkdirSync(path.dirname(queue), { recursive: true });
	const text = rows
		.map((row) =>
			[
				row.task_key,
				row.status,
				row.cli,
				row.provider,
				row.task_path,
				row.dispatched_at,
				row.updated_at,
				row.model,
				row.origin,
			].join(" | "),
		)
		.join("\n");
	fs.writeFileSync(queue, `${text}\n`, "utf8");
}

function shapeRefusal(code: string, overlapWith: string | null, sample: string | null): Verdict {
	return { ok: false, code, overlapWith, sample, serialOnly: code === "write-face-undeclared" };
}

// ── PM channel (in-process) ─────────────────────────────────────────────────

async function pmVerdict(agenticdoc: string, item: E2ECase): Promise<Verdict> {
	resetQueue(agenticdoc, queueRows(item));
	const store = new WorkerStore(agenticdoc);
	const outcome = await dispatchTask(
		{ taskKey: item.taskKey, status: "pending", cli: "pi", provider: "timi", model: "", taskPath: item.taskPath },
		store,
	);
	if (outcome.ok === true) return { ...PROCEED };
	const refusal = outcome as DispatchRefusal;
	const overlap = /overlap-with:(\S+)/.exec(refusal.reason);
	const sample = /sample=(\S+)/.exec(refusal.reason);
	return shapeRefusal(
		refusal.code,
		refusal.overlapWith ?? (overlap === null ? null : overlap[1]),
		refusal.sample ?? (sample === null ? null : sample[1]),
	);
}

// ── operator gate projection (the documented channel algorithm) ─────────────

function gateProjection(item: E2ECase, base: string, caseInsensitive: boolean): Verdict {
	const own = parseWriteFace(item.candidate, { base, caseInsensitive });
	if (own.kind === "rejected") return shapeRefusal(own.code, null, null);
	const other =
		item.inflight === null
			? { kind: "undeclared" as const }
			: parseWriteFace(item.inflight, { base, caseInsensitive });
	if (own.kind === "undeclared") {
		return other.kind === "declared" ? shapeRefusal("write-face-undeclared", null, null) : { ...PROCEED };
	}
	if (other.kind !== "declared") return { ...PROCEED }; // D-003: undeclared cannot prove an overlap
	const result = writeFacesOverlap(own.face, other.face);
	if (result === null) return { ...PROCEED };
	if ("unsupported" in result) return shapeRefusal("write-face-overlap", item.inflightKey, null);
	return shapeRefusal("write-face-overlap", item.inflightKey, result.sample);
}

// ── conductor channel (spawned Python, read-only import) ────────────────────

const BRIDGE_SOURCE = String.raw`import json
import pathlib
import re
import sys

sys.path.insert(0, sys.argv[1])
import mw_common
from autopilot import dispatch as D


def shape(verdict):
    if verdict is None:
        return {"ok": True, "code": None, "overlapWith": None, "sample": None, "serialOnly": False}
    reason = verdict.reason
    code = reason.split(":", 1)[0]
    overlap = re.search(r"overlap-with:(\S+)", reason)
    sample = re.search(r"sample=(\S+)", reason)
    return {
        "ok": False,
        "code": code,
        "overlapWith": overlap.group(1) if overlap else None,
        "sample": sample.group(1) if sample else None,
        "serialOnly": code == "write-face-undeclared",
    }


request = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
project_root = pathlib.Path(request["projectRoot"])
out = []
for case in request["cases"]:
    queue = mw_common.workers_path(project_root)
    rows = case.get("queueRows") or []
    if rows:
        queue.parent.mkdir(parents=True, exist_ok=True)
        queue.write_text("\n".join(mw_common.serialize_entry(row) for row in rows) + "\n", encoding="utf-8", newline="\n")
    elif queue.exists():
        queue.unlink()
    verdict = D._write_face_verdict(
        project_root, request["owner"], case["taskKey"], case["content"],
        card_backed=True, timeline=None,
    )
    out.append(shape(verdict))
pathlib.Path(sys.argv[3]).write_text(json.dumps({
    "verdicts": out,
    "terminal": sorted(mw_common._TERMINAL_STATUSES),
    "caseInsensitive": D.write_face_case_insensitive(),
    "base": D.write_face_base(pathlib.Path(request["projectRoot"])),
}), encoding="utf-8");
`;

interface BridgeResult {
	verdicts: Verdict[];
	terminal: string[];
	caseInsensitive: boolean;
	base: string;
}

function conductorVerdicts(workdir: string, project: string, cases: E2ECase[]): BridgeResult {
	const bridge = path.join(workdir, "conductor-bridge.py");
	fs.writeFileSync(bridge, BRIDGE_SOURCE, "utf8");
	const request = path.join(workdir, "conductor-request.json");
	const response = path.join(workdir, "conductor-response.json");
	fs.writeFileSync(
		request,
		JSON.stringify({
			projectRoot: project,
			owner: OWNER,
			cases: cases.map((item) => ({
				name: item.name,
				taskKey: item.taskKey,
				content: item.candidate,
				queueRows: queueRows(item),
			})),
		}),
		"utf8",
	);
	const proc = spawnSync(resolveRagPython(), [bridge, MULTI_WORKERS_DIR, request, response], {
		encoding: "utf8",
		timeout: 180_000,
	});
	if (proc.status !== 0 || !fs.existsSync(response)) {
		throw new Error(`conductor bridge failed rc=${proc.status}\n${proc.stdout ?? ""}\n${proc.stderr ?? ""}`);
	}
	return JSON.parse(fs.readFileSync(response, "utf8")) as BridgeResult;
}

// ── 0. frozen corpus fingerprint ────────────────────────────────────────────

describe("frozen corpus (P-021)", () => {
	it("is the pinned LF-normalized input with the pinned counts", () => {
		expect(readCorpusFingerprint()).toBe(CORPUS_SHA256_LF);
		const input = corpus();
		expect({ parse: input.parse.length, overlap: input.overlap.length }).toEqual(CORPUS_COUNTS);
	});
});

// ── ① same corpus, both channels, field by field ────────────────────────────

describe("two-channel parity (AC-007 / D-001/D-111/D-112/D-115)", () => {
	it("the same in-flight context + candidate face yields identical verdict fields", async () => {
		// Device equivalence precondition (card requirement 4): base = the
		// `.agenticdoc` parent on both sides; case mode = the platform predicate.
		expect(process.platform).toBe("win32");
		expect(writeFaceCaseInsensitive()).toBe(process.platform === "win32");
		const workdir = mkdtemp("wf-e2e-ts-");
		const project = path.join(workdir, "project");
		const alt = path.join(workdir, "alt");
		fs.mkdirSync(project, { recursive: true });
		fs.mkdirSync(alt, { recursive: true });
		const outside = path.join(alt, "outside-dir");
		expect(writeFaceBase(path.join(project, ".agenticdoc"))).toBe(path.resolve(project));

		const cases = buildCases(corpus(), project, outside);
		expect(cases.length).toBe(CORPUS_COUNTS.parse + CORPUS_COUNTS.overlap);
		const agenticdoc = materialize(cases, project);
		const bridge = conductorVerdicts(workdir, project, cases);
		const conductor = bridge.verdicts;
		const pm: Verdict[] = [];
		for (const item of cases) pm.push(await pmVerdict(agenticdoc, item));

		// Cross-language preconditions, asserted instead of assumed.
		expect(bridge.terminal).toEqual([...TERMINAL_WORKER_STATUSES].sort());
		expect(bridge.caseInsensitive).toBe(writeFaceCaseInsensitive());
		expect(path.resolve(bridge.base)).toBe(path.resolve(project));

		const mismatches: Array<[string, Verdict, Verdict]> = [];
		const projectionMismatches: Array<[string, Verdict, Verdict]> = [];
		cases.forEach((item, index) => {
			const left = conductor[index];
			const right = pm[index];
			const expected = gateProjection(item, project, writeFaceCaseInsensitive());
			if (JSON.stringify(left) !== JSON.stringify(right)) mismatches.push([item.name, left, right]);
			if (JSON.stringify(left) !== JSON.stringify(expected)) projectionMismatches.push([item.name, left, expected]);
			if (JSON.stringify(right) !== JSON.stringify(expected))
				projectionMismatches.push([item.name, right, expected]);
		});
		process.stdout.write(
			`[EVIDENCE] TS aligned channel mismatches=${mismatches.length} projection=${projectionMismatches.length}\n`,
		);
		if (process.env.WF_E2E_TABLE === "1") {
			cases.forEach((item, index) => {
				process.stdout.write(
					`[TABLE] ${item.name} | conductor=${JSON.stringify(conductor[index])} | pm=${JSON.stringify(pm[index])}\n`,
				);
			});
		}
		expect(mismatches).toEqual([]);
		expect(projectionMismatches).toEqual([]);
		const codes = new Set(conductor.map((verdict) => verdict.code));
		expect(codes.has("write-face-overlap")).toBe(true);
		expect(codes.has(null)).toBe(true);

		// ①b base-alignment lesson (`evidence/PM-parity-differential-20261014.md` §0):
		// the SAME differential with a mis-derived PM base manufactures false
		// inconsistencies. Before = candidate-face signatures under the two bases;
		// after = the real aligned channel mismatch count asserted above (0).
		const signature = (item: E2ECase, base: string): string => {
			const parsed = parseWriteFace(item.candidate, { base, caseInsensitive: writeFaceCaseInsensitive() });
			if (parsed.kind === "rejected") return `reject:${parsed.code}`;
			if (parsed.kind === "undeclared") return "undeclared";
			return `declared:${parsed.face.entries.join(",")}`;
		};
		const unaligned = cases
			.filter((item) => signature(item, project) !== signature(item, alt))
			.map((item) => item.name);
		process.stdout.write(
			`[EVIDENCE] TS base alignment before=${unaligned.length} after=${mismatches.length} names=${JSON.stringify(unaligned)}\n`,
		);
		expect(unaligned.length).toBeGreaterThan(0);
	});
});

// ── ② AC-005 reverse proof (PM channel) ─────────────────────────────────────

function faceOf(row: WorkerEntry, project: string): WriteFace | null {
	const text = fs.existsSync(row.taskPath) ? fs.readFileSync(row.taskPath, "utf8") : null;
	if (text === null) return null;
	const parsed = parseWriteFace(text, { base: project, caseInsensitive: writeFaceCaseInsensitive() });
	return parsed.kind === "declared" ? parsed.face : null;
}

/** Recompute AC-005 from the live snapshot: queue rows + each row's task.md
 * `write_face:` field. Unsupported counts as an overlap (D-006). */
function multiWriterPairs(agenticdoc: string, project: string): string[] {
	const store = new WorkerStore(agenticdoc);
	const live = store.readQueue().rows.filter((row) => !TERMINAL_WORKER_STATUSES.has(row.status));
	const groups = new Map<string, WorkerEntry[]>();
	for (const row of live) {
		const owner = row.taskPath.replace(/\\/g, "/").match(/(?:^|\/)\.agenticdoc\/([^/]+)\/workers\//)?.[1] ?? "";
		const list = groups.get(owner) ?? [];
		list.push(row);
		groups.set(owner, list);
	}
	const pairs: string[] = [];
	for (const group of groups.values()) {
		for (let i = 0; i < group.length; i++) {
			for (let j = i + 1; j < group.length; j++) {
				const left = faceOf(group[i], project);
				const right = faceOf(group[j], project);
				if (left !== null && right !== null && writeFacesOverlap(left, right) !== null) {
					pairs.push(`${group[i].taskKey}|${group[j].taskKey}`);
				}
			}
		}
	}
	return pairs;
}

describe("AC-005 reverse proof (PM channel)", () => {
	it("same key, same file: 0 multi-writer pairs; bypassing the gate makes it > 0", async () => {
		const workdir = mkdtemp("wf-e2e-ac005-");
		const project = path.join(workdir, "project");
		const agenticdoc = path.join(project, ".agenticdoc");
		const store = new WorkerStore(agenticdoc);
		const keepDir = path.join(agenticdoc, OWNER, "workers", "w-keep");
		const newDir = path.join(agenticdoc, OWNER, "workers", "w-new");
		fs.mkdirSync(keepDir, { recursive: true });
		fs.mkdirSync(newDir, { recursive: true });
		const keepMd = path.join(keepDir, "task.md");
		const newMd = path.join(newDir, "task.md");
		fs.writeFileSync(keepMd, "write_face: packages/x/**\n", "utf8");
		fs.writeFileSync(newMd, "write_face: packages/x/file.ts\n", "utf8");

		const first = await dispatchTask(
			{ taskKey: "w-keep", status: "pending", cli: "pi", provider: "timi", model: "", taskPath: keepMd },
			store,
		);
		expect(first).toEqual({ ok: true });

		const second = await dispatchTask(
			{ taskKey: "w-new", status: "pending", cli: "pi", provider: "timi", model: "", taskPath: newMd },
			store,
		);
		expect(second.ok).toBe(false);
		const refusal = second as DispatchRefusal;
		expect(refusal.code).toBe("write-face-overlap");
		expect(refusal.overlapWith).toBe("w-keep");
		expect(refusal.sample).toBe("packages/x/file.ts");

		const refusedPairs = multiWriterPairs(agenticdoc, project);
		process.stdout.write(`[EVIDENCE] TS AC-005 pairs after PM dispatch=${refusedPairs.length}\n`);
		expect(refusedPairs).toEqual([]);

		// Counter-example: write the second row directly (gate bypassed).
		await store.upsert({
			taskKey: "w-bypass",
			status: "running",
			cli: "pi",
			provider: "timi",
			taskPath: newMd,
			dispatchedAt: "2026-10-14T00:00:00.000Z",
			updatedAt: "2026-10-14T00:00:00.000Z",
			model: "",
		});
		const bypassPairs = multiWriterPairs(agenticdoc, project);
		process.stdout.write(
			`[EVIDENCE] TS AC-005 pairs after gate bypass=${bypassPairs.length} ${JSON.stringify(bypassPairs)}\n`,
		);
		expect(bypassPairs.length).toBe(1);
	});
});

// ── ③ AC-013: runtime guard, true-write vs false-write ──────────────────────

const RUNTIME_KEY = "wfr-e2e";
const RUNTIME_TASK = "wfr-e2e-task";

interface RuntimeFixture {
	projectRoot: string;
	trueRoot: string;
	keyDir: string;
	taskDir: string;
}

function runtimeFixture(): RuntimeFixture {
	const projectRoot = mkdtemp("wf-e2e-runtime-");
	const trueRoot = path.join(projectRoot, ".agenticdoc");
	const keyDir = path.join(trueRoot, RUNTIME_KEY);
	const taskDir = path.join(keyDir, "workers", RUNTIME_TASK);
	for (const dir of [
		taskDir,
		path.join(keyDir, "evidence"),
		path.join(trueRoot, "other-key", "workers", "o1"),
		path.join(projectRoot, "packages", "coding-agent", "src"),
		path.join(projectRoot, "packages", "coding-agent", "other"),
		path.join(projectRoot, ".git"),
	]) {
		fs.mkdirSync(dir, { recursive: true });
	}
	fs.writeFileSync(path.join(trueRoot, "_index.parallel"), "x\n", "utf8");
	fs.writeFileSync(path.join(keyDir, "pm-state.md"), "x\n", "utf8");
	return { projectRoot, trueRoot, keyDir, taskDir };
}

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
	toolCall: (toolName: string, input: Record<string, unknown>) => { block?: boolean; reason?: string } | undefined;
}

function fakeWorkerPi(): FakeWorker {
	const handlers = new Map<string, Array<(event: unknown) => unknown>>();
	const pi = {
		on: (name: string, callback: (event: unknown) => unknown) => {
			const list = handlers.get(name) ?? [];
			list.push(callback);
			handlers.set(name, list);
		},
		sendUserMessage: () => {},
		setActiveTools: () => {},
		registerTool: () => {},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		emit: (name: string, payload?: unknown) => {
			for (const callback of handlers.get(name) ?? []) callback(payload);
		},
		toolCall: (toolName: string, input: Record<string, unknown>) => {
			for (const callback of handlers.get("tool_call") ?? []) {
				const result = callback({ type: "tool_call", toolCallId: "tc", toolName, input }) as
					| { block?: boolean; reason?: string }
					| undefined;
				if (result?.block) return result;
			}
			return undefined;
		},
	};
}

let savedCwd = process.cwd();

beforeEach(() => {
	savedCwd = process.cwd();
});

afterEach(() => {
	process.chdir(savedCwd);
	delete process.env.PI_WORKER_TASK;
});

async function startWorker(fixture: RuntimeFixture, frontmatter: string[]): Promise<FakeWorker> {
	const lines = ["---", "type: coding", ...frontmatter, "---", "", "Do the task.", ""];
	fs.writeFileSync(path.join(fixture.taskDir, "task.md"), lines.join("\n"), "utf8");
	process.env.PI_WORKER_TASK = path.join(fixture.taskDir, "task.md");
	process.chdir(fixture.projectRoot);
	const worker = fakeWorkerPi();
	await workerModeActivate(worker.pi);
	return worker;
}

function settle(worker: FakeWorker): void {
	worker.emit("agent_end", { messages: [] });
	worker.emit("agent_settled");
}

describe("AC-013 runtime guard two-sided table (D-115 write_face authority)", () => {
	it("true-write family is blocked on both the write/edit and the bash call path", async () => {
		const fixture = runtimeFixture();
		const worker = await startWorker(fixture, ["write_face: packages/coding-agent/src/**"]);
		const rows: Array<{ name: string; writeBlocked: boolean; bashBlocked: boolean }> = [];
		const targets: Array<[string, string]> = [
			["off-face-file", "packages/coding-agent/outside.ts"],
			["dotdot-escape", "packages/coding-agent/src/../../../evil.ts"],
			["outside-repo-absolute", path.join(fixture.projectRoot, "..", "wf-e2e-abs-evil.ts")],
			["cross-key-directory", ".agenticdoc/other-key/workers/o1/report.md"],
		];
		for (const [name, target] of targets) {
			const writeVerdict = worker.toolCall("write", { path: target, content: "x" });
			const bashVerdict = worker.toolCall("bash", { command: `echo x > ${target}` });
			rows.push({ name, writeBlocked: writeVerdict?.block === true, bashBlocked: bashVerdict?.block === true });
			expect(writeVerdict?.block, `${name} write`).toBe(true);
			expect(bashVerdict?.block, `${name} bash`).toBe(true);
		}
		process.stdout.write(`[EVIDENCE] TS AC-013 true-write runtime=${JSON.stringify(rows)}\n`);
		expect(rows).toHaveLength(4);
		settle(worker);
	});

	it("false-write family passes on the bash call path with no block", async () => {
		const fixture = runtimeFixture();
		const worker = await startWorker(fixture, ["write_face: packages/coding-agent/src/**"]);
		const rows: Array<{ name: string; blocked: boolean }> = [];
		for (const command of [...FALSE_WRITE_VECTORS, ...READ_ONLY_COMMANDS]) {
			const verdict = worker.toolCall("bash", { command });
			rows.push({ name: command, blocked: verdict?.block === true });
			expect(verdict, command).toBeUndefined();
		}
		process.stdout.write(
			`[EVIDENCE] TS AC-013 false-write runtime blocked=${rows.filter((row) => row.blocked).length}/${rows.length}\n`,
		);
		expect(rows.every((row) => !row.blocked)).toBe(true);
		const audit = fs.existsSync(path.join(fixture.taskDir, "trace.log"))
			? fs.readFileSync(path.join(fixture.taskDir, "trace.log"), "utf8")
			: "";
		expect(audit.split("\n").filter((line) => line.startsWith("[WRITE_SCOPE]"))).toHaveLength(0);
		settle(worker);
	});

	it("the same false-write text in a task.md body does not refuse either dispatch channel", async () => {
		const workdir = mkdtemp("wf-e2e-ts-body-");
		const project = path.join(workdir, "project");
		fs.mkdirSync(project, { recursive: true });
		const cases: E2ECase[] = [...FALSE_WRITE_VECTORS, ...READ_ONLY_COMMANDS].map((body, index) => ({
			name: `false-write-body-${index}`,
			kind: "parse" as const,
			a: null,
			b: null,
			candidate: `card_path: ${CARD_PATH}\nwrite_face: packages/x/**\n\n## body\n\n${body}\n`,
			inflight: null,
			taskKey: "",
			taskPath: "",
			inflightKey: null,
			inflightPath: null,
		}));
		const agenticdoc = materialize(cases, project);
		const conductor = conductorVerdicts(workdir, project, cases).verdicts;
		const pm: Verdict[] = [];
		for (const item of cases) pm.push(await pmVerdict(agenticdoc, item));
		process.stdout.write(
			`[EVIDENCE] TS AC-013 false-write gate conductor=${conductor.filter((v) => v.ok).length}/${cases.length} pm=${pm.filter((v) => v.ok).length}/${cases.length}\n`,
		);
		expect(conductor).toEqual(cases.map(() => ({ ...PROCEED })));
		expect(pm).toEqual(conductor);
	});
});

// ── device equivalence declaration (card requirement 4) ─────────────────────

describe("device equivalence preconditions (D-006/AC-007)", () => {
	it("base, case mode and the terminal-status single source are explicit", () => {
		expect(process.platform).toBe("win32");
		expect(writeFaceCaseInsensitive()).toBe(true);
		expect(path.resolve(writeFaceBase("/tmp/example/.agenticdoc"))).toBe(path.resolve("/tmp/example"));
		expect([...TERMINAL_WORKER_STATUSES].sort()).toEqual(["done", "failed", "lost", "needs-clarification"]);
	});

	it("the runtime guard is driven through the pure target checker for the same rules", () => {
		// Pure-function cross-check of the runtime table: the extracted candidate
		// for the false family is empty, so the guard has nothing to block.
		const projectRoot = mkdtemp("wf-e2e-pure-");
		const config: BashWriteScopeConfig = {
			projectRoot,
			trueRoot: path.join(projectRoot, ".agenticdoc"),
			keyDir: path.join(projectRoot, ".agenticdoc", RUNTIME_KEY),
			taskDir: path.join(projectRoot, ".agenticdoc", RUNTIME_KEY, "workers", RUNTIME_TASK),
			writeScope: undefined,
			roleClass: "writable",
		};
		expect(checkBashWriteScopeTarget(config, "packages/coding-agent/outside.ts", true).allowed).toBe(true);
		expect(checkBashWriteScopeTarget(config, path.join(projectRoot, "..", "evil.ts"), true).rule).toBe("scope");
	});
});
