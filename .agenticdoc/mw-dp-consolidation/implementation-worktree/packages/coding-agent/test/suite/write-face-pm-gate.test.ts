/**
 * write-face-pm-gate.test.ts — PM-side dispatch gate + card rendering
 * (mw-write-face-guard W-08, card T-W-I08; design D-001/D-003/D-005/D-006/D-008/
 * D-111/D-113, AC-001/002/003/007/008/011/014).
 *
 * What is pinned here:
 *
 * 1. **rendering** — the card's `## 写入允许面` entries render into the task.md
 *    `write_face:` head exactly like the conductor's
 *    `dispatch.py::render_write_face_line`: one line `write_face: a, b`, the
 *    D-113 block-list carrier when any entry contains `,`, `write_face: -` for
 *    a declared-but-empty face, and NO line when the section is absent;
 * 2. **round trip** — `parse(render(entries)) == entries` for comma-bearing and
 *    multi-entry faces (D-113);
 * 3. **cross-language extraction** — the entries this side extracts from a card
 *    equal the ones the real `dispatch.py::_card_write_face_entries` extracts
 *    from the same card file (AC-007; the Python file is only imported, never
 *    modified);
 * 4. **judgement** — an overlapping same-owner in-flight worker refuses with
 *    the conductor's field shape (`write-face-overlap` + `overlap-with:<key>` +
 *    `sample=`) and zero side effects (queue + `.agenticdoc` byte snapshot);
 *    an undeclared face is serial-only (D-003), never an overlap refusal;
 * 5. **site helpers** — `writeFaceBase` is the `.agenticdoc` parent and the
 *    case mode is explicit, both given at the call site (D-006).
 *
 * Pure filesystem + subprocess test: no provider APIs, no credentials.
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import {
	type DispatchAlarm,
	dispatchNewTasks,
	formatDispatchAlarm,
	repairDispatchOrphanedKey,
} from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import {
	type DispatchRefusal,
	dispatchTask,
	writeFaceBase,
	writeFaceCaseInsensitive,
} from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import {
	cardWriteFaceEntries,
	extractCardSections,
	renderWriteFaceLine,
	WRITE_FACE_CARD_SECTION,
	writeDispatchTaskMd,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";
import { type WorkerEntry, WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { parseWriteFace } from "../../src/extensions/agent-team-loop/shared/write-face.ts";

const MULTI_WORKERS_DIR = fileURLToPath(new URL("../../../multi-workers/", import.meta.url)).replace(/[\\/]+$/, "");

/** The module under test, read as text so the test can prove it carries no
 * second queue-row writer (D-114: the row format lives in `worker-store.ts`). */
const DISPATCHER_SOURCE = fileURLToPath(
	new URL("../../src/extensions/agent-team-loop/pm/task-dispatcher.ts", import.meta.url),
);

const tempDirs: string[] = [];

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** `<project>/.agenticdoc` — the WorkerStore root. */
function mkProject(): { project: string; agenticdoc: string } {
	const project = mkdtemp("mw-writeface-pm-");
	const agenticdoc = path.join(project, ".agenticdoc");
	fs.mkdirSync(agenticdoc, { recursive: true });
	return { project, agenticdoc };
}

/** Write `.agenticdoc/<key>/workers/<taskKey>/task.md` and return its path. */
function writeTask(agenticdoc: string, key: string, taskKey: string, header: string): string {
	const dir = path.join(agenticdoc, key, "workers", taskKey);
	fs.mkdirSync(dir, { recursive: true });
	const md = path.join(dir, "task.md");
	fs.writeFileSync(md, header, "utf8");
	return md;
}

/** One same-owner in-flight queue row (the gate's `in_flight` input). */
async function queueInflight(
	store: WorkerStore,
	taskKey: string,
	md: string,
	status: WorkerEntry["status"] = "running",
): Promise<void> {
	await store.upsert({
		taskKey,
		status,
		cli: "pi",
		provider: "timi",
		taskPath: md,
		dispatchedAt: "2026-10-14T00:00:00.000Z",
		updatedAt: "2026-10-14T00:00:00.000Z",
		model: "",
	});
}

function entry(taskKey: string, md: string): Omit<WorkerEntry, "dispatchedAt" | "updatedAt"> {
	return { taskKey, status: "pending", cli: "pi", provider: "timi", model: "", taskPath: md };
}

/** Recursive `rel -> DIR | <size>B` snapshot, so a refusal that touched the
 * tree is a diff (VC-003 / D-008 zero side effects). */
function snapshotDir(dir: string): Record<string, string> {
	const out: Record<string, string> = {};
	const walk = (current: string, prefix: string): void => {
		for (const dirent of fs.readdirSync(current, { withFileTypes: true })) {
			const full = path.join(current, dirent.name);
			const rel = prefix === "" ? dirent.name : `${prefix}/${dirent.name}`;
			if (dirent.isDirectory()) {
				out[rel] = "DIR";
				walk(full, rel);
			} else {
				out[rel] = `${fs.statSync(full).size}B`;
			}
		}
	};
	if (fs.existsSync(dir)) walk(dir, "");
	return out;
}

function assertRefusal(outcome: { ok: boolean }): DispatchRefusal {
	if (outcome.ok) throw new Error("expected a refusal, got ok=true");
	return outcome as DispatchRefusal;
}

// ── card fixtures ───────────────────────────────────────────────────────────

/** A coding card whose `## 写入允许面` mixes a backtick span, a bare entry and
 * a prose-suffixed entry (the three extraction branches). */
const CARD_WITH_FACE = [
	"type: coding",
	"",
	"# fixture",
	"",
	"## 上下文",
	"",
	"任务投递链需要卡。锚点 .agenticdoc/goal.md；判据 pm/ui-bridge.ts:2030。",
	"",
	"## 要求",
	"",
	"AC-001 成立。",
	"",
	"## 交付格式",
	"",
	"report.md。",
	"",
	`## ${WRITE_FACE_CARD_SECTION}`,
	"",
	"- `packages/x/**`",
	"- a/{b,c}/**",
	"- packages/y/** 备注",
	"",
	"## 写入禁止面",
	"",
	"其余一切路径。",
	"",
].join("\n");

/** Same card but the face section only carries the `-` marker. */
const CARD_WITH_EMPTY_FACE = CARD_WITH_FACE.replace("- `packages/x/**`\n- a/{b,c}/**\n- packages/y/** 备注", "-");

/** Same card without the face section at all (undeclared). */
const CARD_WITHOUT_FACE = CARD_WITH_FACE.replace(
	`## ${WRITE_FACE_CARD_SECTION}\n\n- \`packages/x/**\`\n- a/{b,c}/**\n- packages/y/** 备注\n\n`,
	"",
);

function renderCard(agenticdoc: string, cardText: string, taskKey: string): string {
	const sections = extractCardSections(cardText);
	const written = writeDispatchTaskMd(
		{ agenticdocRoot: agenticdoc, ownerKey: "k" },
		{
			taskKey,
			type: "coding",
			body: "body",
			frontmatter: "type: coding",
			card: { headerPath: "tasks/T-fixture.md", sha256: "0".repeat(64), sections },
		},
	);
	return fs.readFileSync(written.path, "utf8");
}

// ── 1. render <-> parse round trip (D-113) ──────────────────────────────────

describe("write_face rendering round trip (D-113)", () => {
	const opts = { base: path.parse(process.cwd()).root, caseInsensitive: false };

	it("single-line form is byte-identical to the historical renderer", () => {
		expect(renderWriteFaceLine(["packages/x/**"])).toBe("write_face: packages/x/**");
		expect(renderWriteFaceLine(["a", "b.ts"])).toBe("write_face: a, b.ts");
	});

	it("comma-bearing entries use the D-113 block-list carrier", () => {
		expect(renderWriteFaceLine(["a/{b,c}/**"])).toBe("write_face:\n  - a/{b,c}/**");
		expect(renderWriteFaceLine(["packages/x/**", "a/{b,c}/**"])).toBe(
			"write_face:\n  - packages/x/**\n  - a/{b,c}/**",
		);
	});

	it("parse(render(entries)) == entries for the pinned faces", () => {
		const faces: string[][] = [
			["packages/x/**"],
			["src/x.ts"],
			["a/{b,c}/**"],
			["packages/x/**", "a/{b,c}/**"],
			["src/[a-", "src/ok.ts"],
		];
		for (const face of faces) {
			const parsed = parseWriteFace(renderWriteFaceLine(face), opts);
			expect(parsed.kind, JSON.stringify(face)).toBe("declared");
			if (parsed.kind === "declared") expect(parsed.face.entries).toEqual(face);
		}
	});

	it("the one-line carrier would NOT round-trip a comma entry (the D-113 defect)", () => {
		// The block form is the fix: the naive one-liner silently rewrites the
		// declared face into two entries (fail-closed but not identical).
		const naive = parseWriteFace("write_face: a/{b,c}/**", opts);
		const block = parseWriteFace("write_face:\n  - a/{b,c}/**", opts);
		expect(naive.kind).toBe("declared");
		if (naive.kind === "declared") expect(naive.face.entries).toEqual(["a/{b", "c}/**"]);
		expect(block.kind).toBe("declared");
		if (block.kind === "declared") expect(block.face.entries).toEqual(["a/{b,c}/**"]);
	});
});

// ── 2. card head rendering ─────────────────────────────────────────────────

describe("card head rendering (D-001)", () => {
	it("renders the card's 写入允许面 entries as one write_face: head line", () => {
		const { agenticdoc } = mkProject();
		const md = renderCard(agenticdoc, CARD_WITH_FACE, "t-face");
		const prologue = md.split("\n\n")[0] ?? "";
		expect(prologue.split("\n")).toEqual([
			"type: coding",
			"card_path: tasks/T-fixture.md",
			`card_sha256: ${"0".repeat(64)}`,
			expect.stringMatching(/^envelope_producer: /),
			"write_face:",
			"  - packages/x/**",
			"  - a/{b,c}/**",
			"  - packages/y/**",
		]);
	});

	it("a declared-but-entry-less section renders the `-` undeclared marker", () => {
		const { agenticdoc } = mkProject();
		const md = renderCard(agenticdoc, CARD_WITH_EMPTY_FACE, "t-empty");
		const prologue = md.split("\n\n")[0] ?? "";
		expect(prologue.split("\n").at(-1)).toBe("write_face: -");
		// `write_face: -` parses back as undeclared (§3.3), not as an empty face.
		expect(parseWriteFace("write_face: -", { base: agenticdoc, caseInsensitive: false })).toEqual({
			kind: "undeclared",
		});
	});

	it("an absent section writes no write_face: line (undeclared, D-003)", () => {
		const { agenticdoc } = mkProject();
		const md = renderCard(agenticdoc, CARD_WITHOUT_FACE, "t-absent");
		expect(md).not.toContain("write_face");
		expect(cardWriteFaceEntries(extractCardSections(CARD_WITHOUT_FACE))).toBeNull();
		expect(cardWriteFaceEntries(extractCardSections(CARD_WITH_EMPTY_FACE))).toEqual([]);
	});
});

// ── 3. cross-language extraction parity (AC-007) ───────────────────────────

const pythonAvailable = (() => {
	try {
		return spawnSync(resolveRagPython(), ["-c", "print(1)"], { encoding: "utf8", timeout: 10_000 }).status === 0;
	} catch {
		return false;
	}
})();

/** Read-only call of the real `dispatch.py::_card_write_face_entries`. */
function pythonWriteFaceEntries(cardPath: string): string[] | null {
	const script = [
		"import json, sys",
		`sys.path.insert(0, ${JSON.stringify(MULTI_WORKERS_DIR)})`,
		"from autopilot.dispatch import _card_write_face_entries, _extract_card_parts",
		"text = open(sys.argv[1], encoding='utf-8').read()",
		"_sections, extras = _extract_card_parts(text)",
		"print(json.dumps(_card_write_face_entries({'extras': extras}), ensure_ascii=False))",
	].join("\n");
	const result = spawnSync(resolveRagPython(), ["-c", script, cardPath], { encoding: "utf8", timeout: 30_000 });
	if (result.status !== 0) {
		throw new Error(`python _card_write_face_entries failed: ${result.stdout ?? ""}${result.stderr ?? ""}`);
	}
	return JSON.parse((result.stdout ?? "").trim()) as string[] | null;
}

describe("PM / conductor extraction parity (AC-007)", () => {
	it.skipIf(!pythonAvailable)("the same card yields identical entries on both sides", () => {
		const { project } = mkProject();
		const cardPath = path.join(project, "card.md");
		fs.writeFileSync(cardPath, CARD_WITH_FACE, "utf8");
		fs.writeFileSync(`${cardPath}.empty`, CARD_WITH_EMPTY_FACE, "utf8");
		fs.writeFileSync(`${cardPath}.absent`, CARD_WITHOUT_FACE, "utf8");
		for (const file of [cardPath, `${cardPath}.empty`, `${cardPath}.absent`]) {
			const text = fs.readFileSync(file, "utf8");
			const pm = cardWriteFaceEntries(extractCardSections(text));
			const py = pythonWriteFaceEntries(file);
			expect(pm, file).toEqual(py);
		}
		expect(pythonWriteFaceEntries(cardPath)).toEqual(["packages/x/**", "a/{b,c}/**", "packages/y/**"]);
	});
});

/** Read-only call of the real `dispatch.py::_write_face_verdict` for one head
 * text: returns the conductor's `DispatchResult.reason` plus the audit rows a
 * real `_write_face_audit` would append (captured with a recorder so the
 * timeline destination is untouched). The Python file is imported, never
 * modified. */
function pythonWriteFaceVerdict(
	projectRoot: string,
	owner: string,
	taskKey: string,
	content: string,
): { reason: string | null; audit: Array<{ ev: string; key: string; detail: string }> } {
	const script = [
		"import json, pathlib, sys",
		`sys.path.insert(0, ${JSON.stringify(MULTI_WORKERS_DIR)})`,
		"from autopilot import dispatch as D",
		"class _Recorder:",
		"    def __init__(self):",
		"        self.rows = []",
		"    def append(self, ev, key=None, detail=None):",
		"        self.rows.append({'ev': ev, 'key': key, 'detail': detail})",
		"request = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))",
		"recorder = _Recorder()",
		"verdict = D._write_face_verdict(",
		"    pathlib.Path(request['projectRoot']), request['owner'], request['taskKey'],",
		"    request['content'], card_backed=True, timeline=recorder,",
		")",
		"print(json.dumps({",
		"    'reason': None if verdict is None else verdict.reason,",
		"    'audit': recorder.rows,",
		"}, ensure_ascii=False))",
	].join("\n");
	const requestPath = path.join(
		os.tmpdir(),
		`wfg-i14-reason-${process.pid}-${Date.now()}-${Math.random().toString(36).slice(2)}.json`,
	);
	fs.writeFileSync(requestPath, JSON.stringify({ projectRoot, owner, taskKey, content }), "utf8");
	try {
		const result = spawnSync(resolveRagPython(), ["-c", script, requestPath], {
			encoding: "utf8",
			timeout: 30_000,
		});
		if (result.status !== 0) {
			throw new Error(`python _write_face_verdict failed: ${result.stdout ?? ""}${result.stderr ?? ""}`);
		}
		return JSON.parse((result.stdout ?? "").trim()) as {
			reason: string | null;
			audit: Array<{ ev: string; key: string; detail: string }>;
		};
	} finally {
		fs.rmSync(requestPath, { force: true });
	}
}

// ── 4. site helpers (D-006) ────────────────────────────────────────────────

describe("call-site helpers (D-006/AC-007)", () => {
	it("writeFaceBase is the .agenticdoc parent (the WorkerStore queue anchor)", () => {
		const { project, agenticdoc } = mkProject();
		expect(path.resolve(writeFaceBase(agenticdoc))).toBe(path.resolve(project));
		expect(path.resolve(writeFaceBase(agenticdoc))).toBe(path.resolve(agenticdoc, ".."));
	});

	it("the case mode is explicit and platform-derived, never operator-internal", () => {
		expect(writeFaceCaseInsensitive()).toBe(process.platform === "win32");
	});
});

// ── 5. judgement: overlap refuse + zero side effects (AC-001/002/008/014) ───

describe("PM dispatch gate (D-005/D-008)", () => {
	it("refuses an overlapping same-owner in-flight worker with the conductor shape", async () => {
		const { agenticdoc } = mkProject();
		const store = new WorkerStore(agenticdoc);
		const keepMd = writeTask(agenticdoc, "k", "w-keep", "type: coding\nwrite_face: packages/x/**\n");
		await queueInflight(store, "w-keep", keepMd);

		const newMd = writeTask(agenticdoc, "k", "w-new", "type: coding\nwrite_face: packages/x/file.ts\n");
		const before = snapshotDir(agenticdoc);
		const outcome = await dispatchTask(entry("w-new", newMd), store);
		const refusal = assertRefusal(outcome);

		expect(refusal.code).toBe("write-face-overlap");
		expect(refusal.overlapWith).toBe("w-keep");
		expect(refusal.sample).toBe("packages/x/file.ts");
		expect(refusal.reason).toBe("write-face-overlap: overlap-with:w-keep sample=packages/x/file.ts");
		expect(refusal.detail).toBe(
			"w-new: overlap with w-keep at packages/x/file.ts (packages/x/file.ts vs packages/x/**)",
		);

		// Zero side effects: no queue row, no task-dir/task.md write (snapshot diff).
		expect(store.readAll().map((row) => row.taskKey)).toEqual(["w-keep"]);
		expect(snapshotDir(agenticdoc)).toEqual(before);
		expect(fs.readFileSync(newMd, "utf8")).toBe("type: coding\nwrite_face: packages/x/file.ts\n");
	});

	it("an undeclared face is serial-only, not an overlap refusal (D-003)", async () => {
		const { agenticdoc } = mkProject();
		const store = new WorkerStore(agenticdoc);
		const keepMd = writeTask(agenticdoc, "k", "w-keep", "type: coding\nwrite_face: packages/x/**\n");
		await queueInflight(store, "w-keep", keepMd);

		const newMd = writeTask(agenticdoc, "k", "w-new", "type: coding\ncard_path: tasks/T.md\n\nbody.\n");
		const outcome = await dispatchTask(entry("w-new", newMd), store);
		const refusal = assertRefusal(outcome);

		expect(refusal.code).toBe("write-face-undeclared");
		expect(refusal.serialOnly).toBe(true);
		expect(refusal.inFlight).toBe(1);
		expect(refusal.reason).toBe("write-face-undeclared: serial-only (1 same-owner worker(s) in flight)");
		expect(refusal.detail).toBe("w-new: write_face undeclared; 1 same-owner worker(s) in flight");
		// Deferred, never rejected as overlapping, and never queued in parallel.
		expect(refusal.code).not.toBe("write-face-overlap");
		expect(store.readAll().map((row) => row.taskKey)).toEqual(["w-keep"]);
	});

	it("a card-less undeclared task dispatches normally even with an in-flight peer (Python exemption)", async () => {
		const { agenticdoc } = mkProject();
		const store = new WorkerStore(agenticdoc);
		const keepMd = writeTask(agenticdoc, "k", "w-keep", "type: coding\nwrite_face: packages/x/**\n");
		await queueInflight(store, "w-keep", keepMd);

		// No `card_path:` -> no author surface to declare a face on, so refusing
		// would manufacture a permanent stall (dispatch.py card-less exemption).
		const newMd = writeTask(agenticdoc, "k", "w-new", "type: coding\n\nbody.\n");
		const outcome = await dispatchTask(entry("w-new", newMd), store);
		expect(outcome).toEqual({ ok: true });
		expect(store.readAll().map((row) => row.taskKey)).toEqual(["w-keep", "w-new"]);
	});

	it("an undeclared face with no in-flight worker dispatches normally", async () => {
		const { agenticdoc } = mkProject();
		const store = new WorkerStore(agenticdoc);
		const md = writeTask(agenticdoc, "k", "w-solo", "type: coding\n\nbody.\n");
		const outcome = await dispatchTask(entry("w-solo", md), store);
		expect(outcome).toEqual({ ok: true });
		expect(store.readAll().map((row) => row.taskKey)).toEqual(["w-solo"]);
	});

	it("terminal same-owner rows never count as in flight", async () => {
		const { agenticdoc } = mkProject();
		const store = new WorkerStore(agenticdoc);
		const keepMd = writeTask(agenticdoc, "k", "w-done", "type: coding\nwrite_face: packages/x/**\n");
		await queueInflight(store, "w-done", keepMd, "done");

		const newMd = writeTask(agenticdoc, "k", "w-new", "type: coding\nwrite_face: packages/x/file.ts\n");
		const outcome = await dispatchTask(entry("w-new", newMd), store);
		expect(outcome).toEqual({ ok: true });
		expect(store.readAll().map((row) => row.taskKey)).toEqual(["w-done", "w-new"]);
	});

	it("a different owner key is not the same 在飞 集", async () => {
		const { agenticdoc } = mkProject();
		const store = new WorkerStore(agenticdoc);
		const otherMd = writeTask(agenticdoc, "other", "w-other", "type: coding\nwrite_face: packages/x/**\n");
		await queueInflight(store, "w-other", otherMd);

		const newMd = writeTask(agenticdoc, "k", "w-new", "type: coding\nwrite_face: packages/x/file.ts\n");
		const outcome = await dispatchTask(entry("w-new", newMd), store);
		expect(outcome).toEqual({ ok: true });
	});

	it("a provable overlap wins over an unsupported-syntax side (D-111)", async () => {
		const { agenticdoc } = mkProject();
		const store = new WorkerStore(agenticdoc);
		// `[a-` is unsupported syntax; `packages/x/file.ts` is a provable conflict.
		const keepMd = writeTask(agenticdoc, "k", "w-keep", "type: coding\nwrite_face: [a-, packages/x/file.ts\n");
		await queueInflight(store, "w-keep", keepMd);

		const newMd = writeTask(agenticdoc, "k", "w-new", "type: coding\nwrite_face: packages/x/**\n");
		const outcome = await dispatchTask(entry("w-new", newMd), store);
		const refusal = assertRefusal(outcome);
		expect(refusal.code).toBe("write-face-overlap");
		expect(refusal.sample).toBe("packages/x/file.ts");
	});

	it("a parse refusal (write-face-empty) is zero side effects too", async () => {
		const { agenticdoc } = mkProject();
		const store = new WorkerStore(agenticdoc);
		const md = writeTask(agenticdoc, "k", "w-bad", "type: coding\nwrite_face:\n");
		const outcome = await dispatchTask(entry("w-bad", md), store);
		const refusal = assertRefusal(outcome);
		expect(refusal.code).toBe("write-face-empty");
		// The operator detail (T-W-I14) reaches both the `reason` the audit line
		// is derived from and the conductor-shaped `detail` line.
		expect(refusal.reason).toBe("write-face-empty: present-but-empty write_face head");
		expect(refusal.detail).toBe("w-bad: write-face-empty present-but-empty write_face head");
		expect(store.readAll()).toEqual([]);
	});

	it("the locked row write goes through WorkerStore's own entry point, not a mirror", async () => {
		// End-to-end: a real dispatchTask (lock held, gate passed) and a direct
		// WorkerStore.upsert of the same row land byte-identical files — because
		// both go through the ONE writer implementation (D-114).
		const { agenticdoc } = mkProject();
		const store = new WorkerStore(agenticdoc);
		const md = writeTask(agenticdoc, "k", "w-a", "type: coding\n\nbody.\n");
		const outcome = await dispatchTask(entry("w-a", md), store);
		expect(outcome).toEqual({ ok: true });
		const dispatchedRaw = fs.readFileSync(path.join(agenticdoc, "_workers.parallel"), "utf8");
		expect(dispatchedRaw.startsWith("# mw-queue:v2\n")).toBe(true);
		const dispatchedRow = store.readAll()[0];
		expect(dispatchedRow?.taskKey).toBe("w-a");
		expect(dispatchedRow?.origin).toBe("manual");

		// Replay the exact same row through the ordinary lock-taking upsert on a
		// fresh queue and compare the resulting bytes.
		const { agenticdoc: replayRoot } = mkProject();
		const replay = new WorkerStore(replayRoot);
		await replay.upsert(dispatchedRow as WorkerEntry);
		expect(fs.readFileSync(path.join(replayRoot, "_workers.parallel"), "utf8")).toBe(dispatchedRaw);

		// The dispatcher no longer carries a second row-joining implementation:
		// the ` | ` layout, the replace matcher and the locked-upsert helper are
		// all gone (each name/pattern asserted absent so a partial revert fails).
		const dispatcherSource = fs.readFileSync(DISPATCHER_SOURCE, "utf8");
		expect(dispatcherSource).not.toContain('join(" | ")');
		expect(dispatcherSource).not.toContain("upsertQueueRowLocked");
		expect(dispatcherSource).not.toContain("serializeWorkerEntry");
		expect(dispatcherSource).not.toContain("queueLineMatchesTaskKey");
	});
});

// ── 6. caller consumes DispatchOutcome (AC-003/D-008, card T-W-I13) ─────────

/** Rows of the single autopilot ledger the PM audit channel appends to
 * (`.agenticdoc/_autopilot/auto-decisions.jsonl`). */
function readLedger(agenticdocRoot: string): Array<Record<string, unknown>> {
	const file = path.join(agenticdocRoot, "_autopilot", "auto-decisions.jsonl");
	if (!fs.existsSync(file)) return [];
	return fs
		.readFileSync(file, "utf8")
		.split("\n")
		.filter((line) => line.trim() !== "")
		.map((line) => JSON.parse(line) as Record<string, unknown>);
}

function refusalRows(agenticdocRoot: string): Array<Record<string, unknown>> {
	return readLedger(agenticdocRoot).filter((row) => row.kind === "write-face-refusal");
}

/** `[VERIFY]` evidence line, written to real stdout (the vite config is
 * `silent: "passed-only"`, so `console.log` from a passing test is swallowed). */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

describe("PM dispatch outcome consumption (AC-003/D-008)", () => {
	it("the normal scan path refuses without a queue row, records one ledger row, and does not spend the quota", async () => {
		const { agenticdoc: agenticdocRoot } = mkProject();
		const store = new WorkerStore(agenticdocRoot);
		const keepMd = writeTask(agenticdocRoot, "_scratch", "wa-keep", "type: coding\nwrite_face: packages/x/**\n");
		await queueInflight(store, "wa-keep", keepMd);
		const refusedMd = writeTask(
			agenticdocRoot,
			"_scratch",
			"wb-overlap",
			"type: coding\nwrite_face: packages/x/file.ts\n",
		);
		const queueBefore = fs.readFileSync(path.join(agenticdocRoot, "_workers.parallel"), "utf8");
		const alarms: DispatchAlarm[] = [];
		const notices: string[] = [];

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "cli",
			maxPerScan: 1,
			onAlarm: (alarm) => alarms.push(alarm),
			onRefusal: (text) => notices.push(text),
		});

		// Zero queue side effects (byte snapshot + rows): the refused task never
		// reaches `_workers.parallel`, and its directory is left where it was.
		expect(fs.readFileSync(path.join(agenticdocRoot, "_workers.parallel"), "utf8")).toBe(queueBefore);
		expect(store.readAll().map((row) => row.taskKey)).toEqual(["wa-keep"]);
		expect(fs.existsSync(refusedMd)).toBe(true);

		// Exactly one durable audit row, field-assertable.
		const detail = "wb-overlap: write-face-overlap: overlap-with:wa-keep sample=packages/x/file.ts";
		expect(refusalRows(agenticdocRoot)).toEqual([
			{ seq: 1, phase: "dispatch-alarm", kind: "write-face-refusal", count: 1, detail },
		]);
		// `maxPerScan` is 1 and nothing was queued: the refusal did not count, so
		// no scan-level quota alarm fires (the buggy `queued += 1` would fire it).
		expect(alarms.filter((alarm) => alarm.kind === "dispatch-quota")).toEqual([]);
		// The human notice is the alarm text, never the audit itself.
		expect(notices).toEqual([formatDispatchAlarm({ kind: "write-face-refusal", count: 1, detail })]);
		verify(
			`[VERIFY] T-W-I13 normal_path refused=wb-overlap queue_rows=[${store
				.readAll()
				.map((row) => row.taskKey)
				.join(",")}] quota_alarms=0`,
		);
		verify(
			`[VERIFY] T-W-I13 normal_ledger_line=${fs
				.readFileSync(path.join(agenticdocRoot, "_autopilot", "auto-decisions.jsonl"), "utf8")
				.trimEnd()}`,
		);
	});

	it("the normal scan path counts a successful dispatch and records no refusal row", async () => {
		const { agenticdoc: agenticdocRoot } = mkProject();
		const store = new WorkerStore(agenticdocRoot);
		writeTask(agenticdocRoot, "_scratch", "w-a", "type: coding\nwrite_face: packages/a/**\n");
		writeTask(agenticdocRoot, "_scratch", "w-b", "type: coding\nwrite_face: packages/b/**\n");
		const alarms: DispatchAlarm[] = [];
		const notices: string[] = [];

		await dispatchNewTasks(store, agenticdocRoot, {
			scope: "cli",
			maxPerScan: 1,
			onAlarm: (alarm) => alarms.push(alarm),
			onRefusal: (text) => notices.push(text),
		});

		// One task queued (the other hit the quota) — proof the success counted,
		// plus the quota count itself and no refusal noise.
		expect(store.readAll().filter((row) => row.status === "pending")).toHaveLength(1);
		expect(alarms.filter((alarm) => alarm.kind === "dispatch-quota")).toEqual([{ kind: "dispatch-quota", count: 1 }]);
		expect(notices).toEqual([]);
		expect(refusalRows(agenticdocRoot)).toEqual([]);
		verify(
			`[VERIFY] T-W-I13 normal_path success queued=${
				store.readAll().filter((row) => row.status === "pending").length
			} quota_alarm_count=${alarms.filter((alarm) => alarm.kind === "dispatch-quota")[0]?.count ?? 0} refusal_rows=${
				refusalRows(agenticdocRoot).length
			}`,
		);
	});

	it("the claim-free repair path refuses without counting it in result.queued and records the ledger row", async () => {
		const { agenticdoc: agenticdocRoot } = mkProject();
		const store = new WorkerStore(agenticdocRoot);
		writeTask(agenticdocRoot, "orphan", "w-par", "type: coding\nwrite_face:\n\nbody\n");
		const notices: string[] = [];

		const result = await repairDispatchOrphanedKey(store, agenticdocRoot, "orphan", {
			onRefusal: (text) => notices.push(text),
		});

		expect(result.queued).toEqual([]);
		expect(store.readAll()).toEqual([]);
		const detail = "w-par: write-face-empty: present-but-empty write_face head";
		expect(refusalRows(agenticdocRoot)).toEqual([
			{ seq: 1, phase: "dispatch-alarm", kind: "write-face-refusal", count: 1, detail },
		]);
		expect(notices).toEqual([formatDispatchAlarm({ kind: "write-face-refusal", count: 1, detail })]);
		verify(
			`[VERIFY] T-W-I13 repair_path refused=w-par result_queued=[${result.queued.join(
				",",
			)}] queue_rows=${store.readAll().length} refusal_rows=${refusalRows(agenticdocRoot).length}`,
		);
		verify(
			`[VERIFY] T-W-I13 repair_ledger_line=${fs
				.readFileSync(path.join(agenticdocRoot, "_autopilot", "auto-decisions.jsonl"), "utf8")
				.trimEnd()}`,
		);
	});
});

// ── 7. rejected reason parity (AC-007, card T-W-I14) ───────────────────────

describe("PM / conductor rejected reason parity (AC-007)", () => {
	it.skipIf(!pythonAvailable)("the same refused head yields a byte-identical reason on both channels", async () => {
		const { project, agenticdoc } = mkProject();
		const store = new WorkerStore(agenticdoc);
		// Two refusal classes are mandatory (empty head + rejected entry); the
		// escape entry is the third, so a future regression in any of the
		// `write_face.py:654/668/674/685` construction points shows up here.
		const cases: Array<{ name: string; head: string; taskKey: string; code: string }> = [
			{ name: "empty head", head: "type: coding\nwrite_face:\n", taskKey: "w-empty", code: "write-face-empty" },
			{
				name: "invalid entry",
				head: "type: coding\nwrite_face:\n  - !packages/x/**\n",
				taskKey: "w-bang",
				code: "write-face-invalid-entry",
			},
			{
				name: "escape entry",
				head: "type: coding\nwrite_face:\n  - a/../b/**\n",
				taskKey: "w-escape",
				code: "write-face-escape",
			},
		];
		for (const item of cases) {
			const md = writeTask(agenticdoc, "k", item.taskKey, item.head);
			const outcome = await dispatchTask(entry(item.taskKey, md), store);
			const refusal = assertRefusal(outcome);
			const py = pythonWriteFaceVerdict(project, "k", item.taskKey, item.head);
			expect(refusal.code, item.name).toBe(item.code);
			expect(py.reason, item.name).not.toBeNull();
			expect(refusal.reason, item.name).toBe(py.reason);
			// `DispatchRefusal.detail` stays the conductor's `_write_face_audit`
			// timeline line (`"<task_key>: <code> <detail>"`), captured from the
			// real Python refusal, not restated from the TS code.
			expect(refusal.detail, item.name).toBe(py.audit[0]?.detail);
		}
	});

	it.skipIf(!pythonAvailable)("a raw single quote is a bounded quote-style difference only", async () => {
		// Python `repr` switches to double quotes when the raw contains a single
		// quote and no double quote; the operator keeps the plain single-quote
		// wrapper. This boundary is pinned explicitly rather than silently
		// emulated (`write-face.ts` never does `repr`).
		const { project, agenticdoc } = mkProject();
		const store = new WorkerStore(agenticdoc);
		const raw = "x'y/**";
		const head = `type: coding\nwrite_face:\n  - ${raw}\n`;
		const md = writeTask(agenticdoc, "k", "w-quote", head);
		const refusal = assertRefusal(await dispatchTask(entry("w-quote", md), store));
		const py = pythonWriteFaceVerdict(project, "k", "w-quote", head);

		expect(py.reason).toBe(`write-face-invalid-entry: entry "${raw}"`);
		expect(refusal.reason).toBe(`write-face-invalid-entry: entry '${raw}'`);
		const rawOf = (line: string): string => {
			const at = line.indexOf("entry ");
			return line.slice(at + "entry ".length + 1, -1);
		};
		expect(rawOf(py.reason ?? "")).toBe(raw);
		expect(rawOf(refusal.reason)).toBe(raw);
		// The audit line inherits the same bounded difference (and nothing else).
		expect(py.audit[0]?.detail).toBe(`w-quote: write-face-invalid-entry entry "${raw}"`);
		expect(refusal.detail).toBe(`w-quote: write-face-invalid-entry entry '${raw}'`);
	});

	it.skipIf(!pythonAvailable)(
		"a one-line quoted comma is a second known bounded difference (D-112 split)",
		async () => {
			// Pre-existing, not caused by this card: TS `splitSingleLine` strips the
			// matching wrapper quotes before splitting (`shared/write-face.ts`), while
			// Python's D-112 split is syntax-blind and takes the first field `'a`.
			// Both still agree on the judgement `code`; only the raw entry text in
			// the `reason` differs. Pinned so a future split alignment is deliberate.
			const { project, agenticdoc } = mkProject();
			const store = new WorkerStore(agenticdoc);
			const head = "type: coding\nwrite_face: 'a,b'\n";
			const md = writeTask(agenticdoc, "k", "w-oneline", head);
			const refusal = assertRefusal(await dispatchTask(entry("w-oneline", md), store));
			const py = pythonWriteFaceVerdict(project, "k", "w-oneline", head);

			expect(refusal.code).toBe("write-face-invalid-entry");
			expect(py.reason).toBe('write-face-invalid-entry: entry "\'a"');
			expect(refusal.reason).toBe("write-face-invalid-entry: entry 'a,b'");
		},
	);
});
