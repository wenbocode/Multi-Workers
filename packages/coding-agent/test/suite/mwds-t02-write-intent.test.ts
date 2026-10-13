/**
 * mwds-t02-write-intent.test.ts — AC-005a (VC-015…VC-019):
 *
 * Dispatch-time write-surface satisfiability. A task type whose worker
 * allowlist carries neither `write`/`edit` nor `bash` (review / reviewer /
 * verifier / rag-research) cannot reach any path outside its own task dir, so
 * a task book ordering one is unsatisfiable and is refused BEFORE the single
 * write point (`writeDispatchTaskMd`, contract C4) — zero mkdir, zero
 * task.md, zero queue row. `research` is writeless but shell-capable (it can
 * write with bash), so it is never refused: it only gets the C2 contract
 * section and the default C1 `write_scope:` header. `coding` and the other
 * write roles are untouched.
 *
 * The judgement is the rule set from the card: write verb + the token right
 * after it (gap <= 32, anchored character class — no extension enumeration),
 * five allow-guards (negation / read-marker / fenced code / quotation / PM
 * attribution), then the whitelist in ORDER: deny prefixes -> own task dir
 * (realpath + segment boundary) -> no-dir-component basename channel (worker_file
 * / framework names) -> path-shape refusal. The corpus replay below is the hard
 * acceptance: on every `.agenticdoc/<key>/workers/<taskKey>/task.md` in the
 * repo, the writeless-without-shell set must yield zero false positives — the hit
 * COUNT is a growth quantity (RQ-3: 2 -> 13 after the shape axis, AC-004) and is
 * logged, not asserted; the assertion is that the violation set is the one known
 * R22 incident card (the rule exists for it).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../src/core/extensions/types.ts";
import {
	applyWriteSurfaceContract,
	classifyWriteTargetShape,
	collectWriteIntentHits,
	isWhitelistedWriteTarget,
	judgeWriteIntent,
	judgeWriteTarget,
	registerWorkerCommands,
	registerWorkerTools,
	renderWriteSurfaceContract,
	WRITE_INTENT_GUARDS,
	WRITE_INTENT_VERBS,
	WRITE_SURFACE_MARKER,
	WRITE_SURFACE_MARKER_END,
	type WriteIntentHit,
	writeDispatchTaskMd,
	writeIntentRefusal,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { isSameOrUnder, normalizeForCompare } from "../../src/extensions/agent-team-loop/worker/read-scope.ts";
import { WORKER_FILE_NAME_RE } from "../../src/extensions/agent-team-loop/worker/worker-file-tool.ts";
import { isShellRole, isWritelessRole } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TEST_DIR, "../../../..");

const tempDirs: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mwds-t02-"));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

// ── corpus replay helpers (VC-015) ───────────────────────────────────────────

function findCorpusTaskMds(): string[] {
	const root = path.join(REPO_ROOT, ".agenticdoc");
	const out: string[] = [];
	let keys: string[];
	try {
		keys = fs.readdirSync(root);
	} catch {
		return out;
	}
	for (const key of keys) {
		const workers = path.join(root, key, "workers");
		let taskKeys: string[];
		try {
			taskKeys = fs.readdirSync(workers);
		} catch {
			continue;
		}
		for (const taskKey of taskKeys) {
			const taskMd = path.join(workers, taskKey, "task.md");
			if (fs.existsSync(taskMd)) out.push(taskMd);
		}
	}
	return out;
}

function corpusType(text: string): string {
	return /^type:\s*(\S+)\s*$/m.exec(text)?.[1] ?? "";
}

// ── fakes ───────────────────────────────────────────────────────────────────

interface NotifyRecord {
	message: string;
	level: string;
}

type CommandHandler = (args: string, ctx: ExtensionCommandContext) => Promise<void> | void;
type ToolExecute = (
	id: string,
	params: unknown,
	signal: undefined,
	onUpdate: undefined,
	ctx: ExtensionContext,
) => Promise<{ content: Array<{ type: string; text: string }>; details: unknown }>;

interface FakePi {
	pi: ExtensionAPI;
	commands: Map<string, CommandHandler>;
	tools: Map<string, { execute: ToolExecute }>;
	notifications: NotifyRecord[];
	ctx: ExtensionCommandContext;
}

function fakePi(): FakePi {
	const commands = new Map<string, CommandHandler>();
	const tools = new Map<string, { execute: ToolExecute }>();
	const notifications: NotifyRecord[] = [];
	const pi = {
		registerTool: (tool: { name: string; execute: ToolExecute }) => {
			tools.set(tool.name, tool);
		},
		registerCommand: (name: string, command: { handler: CommandHandler }) => {
			commands.set(name, command.handler);
		},
		sendMessage: () => {},
		appendEntry: () => {},
	} as unknown as ExtensionAPI;
	const ctx = {
		hasUI: true,
		ui: {
			notify: (message: string, level?: string) => {
				notifications.push({ message, level: level ?? "info" });
			},
			setWidget: () => {},
		},
		modelRegistry: undefined,
	} as unknown as ExtensionCommandContext;
	return { pi, commands, tools, notifications, ctx };
}

async function runWorkerCommand(
	root: string,
	args: string,
	cardKey?: string,
): Promise<{ notifications: NotifyRecord[]; store: WorkerStore }> {
	const { pi, commands, notifications, ctx } = fakePi();
	const store = new WorkerStore(root);
	registerWorkerCommands(pi, store, new IndexStore(root), root, { key: "_scratch" }, root);
	const handler = commands.get("worker");
	if (!handler) throw new Error("/worker not registered");
	let effectiveArgs = args;
	if (cardKey !== undefined) {
		// T-02: success fixtures opt in with a compliant card; refusal fixtures
		// stay card-free so their before/after snapshotTree stays unchanged.
		const taskDir = path.join(root, cardKey, "tasks");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(
			path.join(taskDir, "T-00-fixture.md"),
			[
				"type: review",
				"",
				"## 上下文",
				"",
				"write-intent fixture。种子锚点 .agenticdoc/goal.md；判据入口 pm/ui-bridge.ts:1402。",
				"",
				"## 要求",
				"",
				"AC-001 成立。",
				"",
				"## 交付格式",
				"",
				"report.md。",
				"",
				"## 审计目标",
				"",
				"回答「写面判据是否可被形式满足」，对照 pm/ui-bridge.ts:1402 的窗口边界。",
				"",
				"## 未覆盖面声明",
				"",
				"未覆盖 Windows 长路径前缀下的重定向语义。",
				"",
			].join("\n"),
			"utf8",
		);
		effectiveArgs = args.replace(/^(\S+)\s*/, `$1 --card ${cardKey}/tasks/T-00-fixture.md `);
	}
	await handler(effectiveArgs, ctx);
	return { notifications, store };
}

async function runDispatchWorker(root: string, params: Record<string, unknown>, cardKey?: string): Promise<string> {
	const { pi, tools, ctx } = fakePi();
	const store = new WorkerStore(root);
	registerWorkerTools(pi, store, new AckStore(root), new IndexStore(root), root, { key: "_scratch" }, root);
	const tool = tools.get("dispatch_worker");
	if (!tool) throw new Error("dispatch_worker not registered");
	let effectiveParams = params;
	if (cardKey !== undefined) {
		const taskDir = path.join(root, cardKey, "tasks");
		fs.mkdirSync(taskDir, { recursive: true });
		const cardPath = path.join(taskDir, "T-00-fixture.md");
		fs.writeFileSync(
			cardPath,
			[
				"type: review",
				"",
				"## 上下文",
				"",
				"write-intent fixture。种子锚点 .agenticdoc/goal.md；判据入口 pm/ui-bridge.ts:1402。",
				"",
				"## 要求",
				"",
				"AC-001 成立。",
				"",
				"## 交付格式",
				"",
				"report.md。",
				"",
				"## 审计目标",
				"",
				"回答「写面判据是否可被形式满足」，对照 pm/ui-bridge.ts:1402 的窗口边界。",
				"",
				"## 未覆盖面声明",
				"",
				"未覆盖 Windows 长路径前缀下的重定向语义。",
				"",
			].join("\n"),
			"utf8",
		);
		effectiveParams = { card_path: cardPath, ...params };
	}
	const result = await tool.execute("id", effectiveParams, undefined, undefined, ctx as unknown as ExtensionContext);
	return result.content[0]?.text ?? "";
}

function snapshotTree(root: string): string[] {
	const out: string[] = [];
	const walk = (dir: string): void => {
		const entries = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name));
		for (const entry of entries) {
			const full = path.join(dir, entry.name);
			const rel = path.relative(root, full);
			if (entry.isDirectory()) {
				out.push(`${rel}/`);
				walk(full);
			} else {
				out.push(`${rel}=${fs.readFileSync(full, "utf8")}`);
			}
		}
	};
	walk(root);
	return out;
}

function workerTaskDirs(root: string, key: string): string[] {
	try {
		return fs.readdirSync(path.join(root, key, "workers"));
	} catch {
		return [];
	}
}

function soleTaskKey(root: string, key: string): string {
	const dirs = workerTaskDirs(root, key);
	expect(dirs).toHaveLength(1);
	return dirs[0] as string;
}

function readTaskMd(root: string, key: string, taskKey: string): string {
	return fs.readFileSync(path.join(root, key, "workers", taskKey, "task.md"), "utf8");
}

function markerCount(text: string, marker: string): number {
	return text.split(marker).length - 1;
}

const PROJECT = path.resolve(os.tmpdir(), "mwds-t02-project");
// A4 fix (AC-003/VC-046): the fixture mirrors the REAL layout, so
// `.agenticdoc/k/workers/t02/report.md` is the own-taskDir case it was meant to
// be. Without the `.agenticdoc` segment the old basename-blind implementation
// resolved it OUTSIDE the task dir and still returned true — the directory
// blindness this axis removes.
const TASK_DIR = path.join(PROJECT, ".agenticdoc", "k", "workers", "t02");

function verdict(description: string, type = "review", allowForeignWrite = false) {
	return judgeWriteIntent({ type, description, taskDir: TASK_DIR, projectRoot: PROJECT, allowForeignWrite });
}

// ── VC-015: corpus replay (hard acceptance) ─────────────────────────────────

describe("AC-005a corpus replay (VC-015)", () => {
	it("the writeless-without-shell corpus yields 0 false positives (hit set = known true positives only)", () => {
		const files = findCorpusTaskMds();
		const books: Array<{ file: string; text: string; taskDir: string }> = [];
		for (const file of files) {
			const text = fs.readFileSync(file, "utf8");
			const type = corpusType(text);
			if (isWritelessRole(type) && !isShellRole(type)) books.push({ file, text, taskDir: path.dirname(file) });
		}
		const hitFiles: Array<{ file: string; hits: WriteIntentHit[] }> = [];
		const violations: Array<{ file: string; hit: WriteIntentHit }> = [];
		for (const book of books) {
			const hits = collectWriteIntentHits(book.text);
			if (hits.length > 0) hitFiles.push({ file: book.file, hits });
			for (const hit of hits) {
				if (!isWhitelistedWriteTarget(hit.path, { taskDir: book.taskDir, projectRoot: REPO_ROOT })) {
					violations.push({ file: book.file, hit });
				}
			}
		}
		// T-12 corpus-brittleness fix (PM extension): the old `hits <= 2` was a
		// growth-sensitive count — the corpus is a growth quantity (298 task books
		// at this run), so any future legitimate book that hits would turn the
		// test red and mask the health of the judgement. Assert the judgement
		// instead: zero false positives, i.e. the hit set (violations, hits that
		// fail the path whitelist) must be a subset of the explicit whitelist of
		// known true positives. Whitelisted hits (a review book naming its own
		// framework-provided `output.md`, a `worker_file` basename, the task dir)
		// may grow with the corpus and are deliberately not counted here.
		const KNOWN_TRUE_POSITIVE_TASKS: ReadonlySet<string> = new Set(["mwg-qg-review-20261010"]);
		const violationTasks = violations.map((v) => path.basename(path.dirname(v.file)));
		const falsePositives = violationTasks.filter((task) => !KNOWN_TRUE_POSITIVE_TASKS.has(task));
		const truePositive = violationTasks.filter((task) => KNOWN_TRUE_POSITIVE_TASKS.has(task));
		const hits = hitFiles.reduce((n, f) => n + f.hits.length, 0);
		console.log(
			`[VERIFY] VC-015: corpus=${files.length} read_only_books=${books.length} hit_files=${hitFiles.length} hits=${hits} false_positives=${falsePositives.length} violations=${violations.length} unique_true_positive=${truePositive.length === 1}`,
		);
		for (const v of violations)
			console.log(`  [VERIFY] VC-015 violation: ${path.relative(REPO_ROOT, v.file)} -> ${v.hit.path}`);
		expect(books.length).toBeGreaterThanOrEqual(24);
		expect(falsePositives).toEqual([]);
		expect(truePositive).toHaveLength(1);
	});
});

// ── AC-010/C-29: the injected write-surface marker must not trip its own guard ─

describe("AC-010 self-injection is not a write order (C-29)", () => {
	const REAL_TARGET = ".agenticdoc/other/evidence/x.md";

	it("the marker bytes yield no hits in either form (inline / cross-line)", () => {
		const inline = `${WRITE_SURFACE_MARKER}\n${WRITE_SURFACE_MARKER_END}`;
		const crossLine = "<!--\nmw-write-surface: v1\n-->\n<!--\n/mw-write-surface: v1\n-->";
		expect(collectWriteIntentHits(inline)).toEqual([]);
		expect(collectWriteIntentHits(crossLine)).toEqual([]);
		console.log(
			`[VERIFY] AC-010: marker_inline_hits=${collectWriteIntentHits(inline).length} marker_crossline_hits=${collectWriteIntentHits(crossLine).length}`,
		);
	});

	it("the real contract section no longer produces the -surface: false positive", () => {
		const section = renderWriteSurfaceContract("review", undefined);
		const paths = collectWriteIntentHits(section).map((h) => h.path);
		expect(paths).not.toContain("-surface:");
		expect(verdict(section).ok).toBe(true);
		console.log(
			`[VERIFY] AC-010: contract_section_paths=[${paths.join(",")}] surface_fp=${paths.includes("-surface:")} verdict_ok=${verdict(section).ok}`,
		);
	});

	it("a real path inside the comment is not a hit (strip, not a marker-name skip)", () => {
		expect(collectWriteIntentHits("<!-- 例如 src/a.ts 会被改 -->")).toEqual([]);
		expect(collectWriteIntentHits(`<!-- 写入 ${REAL_TARGET} -->`)).toEqual([]);
		console.log("[VERIFY] AC-010: path_in_comment_hits=0 verb_in_comment_hits=0");
	});

	it("a real target outside the comment still hits (same line / adjacent / interleaved)", () => {
		const sameLine = `说明 <!-- mw-write-surface: v1 --> 写入 ${REAL_TARGET}`;
		const adjacent = `<!-- mw-write-surface: v1 -->\n写入 ${REAL_TARGET}`;
		const interleaved = `写入 <!-- 备注 --> ${REAL_TARGET}`;
		expect(collectWriteIntentHits(sameLine).map((h) => h.path)).toContain(REAL_TARGET);
		expect(collectWriteIntentHits(adjacent).map((h) => h.path)).toContain(REAL_TARGET);
		expect(collectWriteIntentHits(interleaved).map((h) => h.path)).toContain(REAL_TARGET);
		console.log(`[VERIFY] AC-010: same_line_hit=1 adjacent_hit=1 interleaved_hit=1 target=${REAL_TARGET}`);
	});
});

// ── VC-016: read usages are not write orders ────────────────────────────────

describe("AC-005a read usage (VC-016)", () => {
	it("an external path named as input/reference is allowed", () => {
		const v = verdict("读取 evidence/runs/x.md 作为输入，报告写到 .agenticdoc/other/evidence/out.md");
		console.log(`[VERIFY] VC-016: read_input_case=${v.ok ? "allow" : "refuse"}`);
		expect(v.ok).toBe(true);
		expect(v.violations).toEqual([]);
	});

	it("a pure read description with a write verb nowhere is allowed", () => {
		expect(verdict("核对 spec.md 与 design.md 的一致性，给出判定").ok).toBe(true);
	});
});

// ── VC-017: write roles are untouched ───────────────────────────────────────

describe("AC-005a write roles zero impact (VC-017)", () => {
	it("judgeWriteIntent short-circuits every role that has write/edit or bash", () => {
		const affected = ["coding", "repair", "vision", "roadmap-writer", "phase-writer", "research"].filter(
			(type) =>
				!judgeWriteIntent({
					type,
					description: "写入 .agenticdoc/other/evidence/x.md",
					taskDir: TASK_DIR,
					projectRoot: PROJECT,
				}).ok,
		);
		console.log(`[VERIFY] VC-017: coding_roles_affected=${affected.length}`);
		expect(affected).toEqual([]);
	});

	it("a coding dispatch keeps the pre-C2 bytes (no contract section, no write_scope)", async () => {
		const root = mkdtemp();
		const notes = await runWorkerCommand(
			root,
			"pi --type coding --key _scratch 把结论写到 packages/foo/bar.ts",
			"_scratch",
		);
		expect(notes.notifications.some((n) => n.message.includes("Dispatched"))).toBe(true);
		const taskKey = soleTaskKey(root, "_scratch");
		const md = readTaskMd(root, "_scratch", taskKey);
		expect(md).not.toContain(WRITE_SURFACE_MARKER);
		expect(md).not.toContain("write_scope:");
	});
});

// ── VC-018: the five allow-guards ───────────────────────────────────────────

describe("AC-005a allow-guards (VC-018)", () => {
	const cases: Array<{ guard: string; description: string }> = [
		{ guard: "negation", description: "不要写到 .agenticdoc/other/evidence/x.md" },
		{
			guard: "read-marker",
			description: "参考 .agenticdoc/other/evidence/x.md 后写入 .agenticdoc/other/evidence/y.md",
		},
		{ guard: "fenced-code", description: "```\n写入 .agenticdoc/other/evidence/x.md\n```" },
		{ guard: "quotation", description: '真事故：任务书要求"写入 .agenticdoc/other/evidence/x.md"' },
		{ guard: "pm-attribution", description: "PM 会写入 .agenticdoc/other/evidence/x.md" },
	];

	it("each guard turns its hit into an allowed mention", () => {
		const allowed = cases.filter((c) => verdict(c.description).ok);
		console.log(
			`[VERIFY] VC-018: guards=${WRITE_INTENT_GUARDS.length} cases=${cases.length} each_allows=${allowed.length === cases.length}`,
		);
		expect(WRITE_INTENT_GUARDS).toHaveLength(5);
		expect(cases.map((c) => c.guard).sort()).toEqual([...WRITE_INTENT_GUARDS].sort());
		for (const c of cases) {
			const v = verdict(c.description);
			expect(v.ok, c.guard).toBe(true);
			expect(v.hits, c.guard).toEqual([]);
		}
	});

	it("the same text without the guard is refused (the guard is load-bearing)", () => {
		expect(verdict("写到 .agenticdoc/other/evidence/x.md").ok).toBe(false);
	});

	it("the verb table is enumerable and refuses an external order for a review role", () => {
		expect(WRITE_INTENT_VERBS.length).toBeGreaterThanOrEqual(16);
		expect(WRITE_INTENT_VERBS).toContain("写到");
		expect(WRITE_INTENT_VERBS).toContain("write");
	});
});

// ── VC-019: contract injection + idempotency ────────────────────────────────

describe("AC-005a contract section (VC-019)", () => {
	it("applyWriteSurfaceContract is a byte-level fixed point with exactly one marker pair", () => {
		const once = applyWriteSurfaceContract("type: review\n\nwork\n", "review", undefined);
		const twice = applyWriteSurfaceContract(once, "review", undefined);
		const section = renderWriteSurfaceContract("review", undefined);
		const contentLines = section.split("\n");
		expect(twice).toBe(once);
		expect(markerCount(twice, WRITE_SURFACE_MARKER)).toBe(1);
		expect(markerCount(twice, WRITE_SURFACE_MARKER_END)).toBe(1);
		// Section body = exactly three fixed lines between the paired markers.
		expect(contentLines.filter((line) => line.startsWith("- "))).toHaveLength(3);
		console.log(
			`[VERIFY] VC-019: marker_count=${markerCount(twice, WRITE_SURFACE_MARKER)} idempotent=${twice === once}`,
		);
		console.log(`[VERIFY] VC-019 section=${JSON.stringify(section)}`);
	});

	it("re-dispatching the same task.md bytes stays a fixed point", () => {
		const root = mkdtemp();
		const deps = { agenticdocRoot: root, ownerKey: "_scratch" };
		const input = {
			taskKey: "t-md",
			type: "review",
			body: "work",
			frontmatter: "type: review\n",
			injectWriteSurface: true,
		};
		const first = writeDispatchTaskMd(deps, { ...input });
		const firstText = fs.readFileSync(first.path, "utf8");
		const second = writeDispatchTaskMd(deps, { ...input });
		const secondText = fs.readFileSync(second.path, "utf8");
		expect(first.injected).toBe(true);
		expect(secondText).toBe(firstText);
		expect(markerCount(secondText, WRITE_SURFACE_MARKER)).toBe(1);
	});

	it("a review role with no write mention still gets the contract section and no write_scope", async () => {
		const root = mkdtemp();
		const notes = await runWorkerCommand(
			root,
			"pi --type review --key _scratch 分析 X 的失败原因，给出判定",
			"_scratch",
		);
		expect(notes.notifications.some((n) => n.message.includes("Dispatched"))).toBe(true);
		const taskKey = soleTaskKey(root, "_scratch");
		const md = readTaskMd(root, "_scratch", taskKey);
		expect(markerCount(md, WRITE_SURFACE_MARKER)).toBe(1);
		expect(md).not.toContain("write_scope:");
	});
});

// ── reverse cases (a)-(e): refusal, whitelist, shell role, escape hatch ─────

describe("AC-005a refusal is zero-side-effect (VC-015 /reverse a)", () => {
	it("/worker refuses an unsatisfiable review task before any write", async () => {
		const root = mkdtemp();
		const before = snapshotTree(root);
		const { notifications, store } = await runWorkerCommand(
			root,
			"pi --type review --key _scratch 唯一允许写入 .agenticdoc/other/evidence/x.md",
		);
		expect(notifications).toHaveLength(1);
		expect(notifications[0]?.level).toBe("warning");
		const text = notifications[0]?.message ?? "";
		expect(text).toContain("[worker-write-surface]");
		expect(text).toContain(".agenticdoc/other/evidence/x.md");
		expect(text).toContain('worker_file file="report.md"');
		expect(workerTaskDirs(root, "_scratch")).toEqual([]);
		expect(store.readAll()).toEqual([]);
		expect(snapshotTree(root)).toEqual(before);
		console.log(`[VERIFY] VC-015 refusal_text=${JSON.stringify(text)}`);
	});

	it("dispatch_worker refuses the same way, before mkdir", async () => {
		const root = mkdtemp();
		const text = await runDispatchWorker(root, {
			task_key: "t-refuse",
			description: "写到 .agenticdoc/other/evidence/x.md",
			type: "review",
			key: "_scratch",
		});
		expect(text).toContain("[worker-write-surface]");
		expect(workerTaskDirs(root, "_scratch")).toEqual([]);
	});
});

describe("AC-005a whitelist (VC-015 /reverse b)", () => {
	it("worker_file basenames, framework names and the own task dir pass", () => {
		expect(isWhitelistedWriteTarget("report.md", { taskDir: TASK_DIR, projectRoot: PROJECT })).toBe(true);
		expect(isWhitelistedWriteTarget("report-adversarial.md", { taskDir: TASK_DIR, projectRoot: PROJECT })).toBe(true);
		expect(isWhitelistedWriteTarget("progress.md", { taskDir: TASK_DIR, projectRoot: PROJECT })).toBe(true);
		expect(isWhitelistedWriteTarget("output.md", { taskDir: TASK_DIR, projectRoot: PROJECT })).toBe(true);
		expect(isWhitelistedWriteTarget("trace.log", { taskDir: TASK_DIR, projectRoot: PROJECT })).toBe(true);
		expect(WORKER_FILE_NAME_RE.test("report-adversarial.md")).toBe(true);
		expect(
			isWhitelistedWriteTarget(path.join(TASK_DIR, "notes.md"), { taskDir: TASK_DIR, projectRoot: PROJECT }),
		).toBe(true);
		expect(
			isWhitelistedWriteTarget(".agenticdoc/k/workers/t02/report.md", { taskDir: TASK_DIR, projectRoot: PROJECT }),
		).toBe(true);
		expect(isWhitelistedWriteTarget(".agenticdoc/k/evidence/x.md", { taskDir: TASK_DIR, projectRoot: PROJECT })).toBe(
			false,
		);
		console.log("[VERIFY] VC-015: whitelist=report.md,report-<slug>.md,progress.md,output.md,task-dir");
	});
});

// ── VC-011: basename whitelist must not bypass the directory check (AC-003) ─

describe("AC-003 directory blindness (VC-011)", () => {
	it("a whitelisted basename does not whitelist a foreign directory", () => {
		const negatives = [
			"../other-key/workers/other-task/output.md",
			".agenticdoc/other-key/workers/other-task/output.md",
			"..\\o\\pm-state.md",
			path.join(path.parse(PROJECT).root, "elsewhere", "trace.log"),
		];
		const bypassed = negatives.filter((token) =>
			isWhitelistedWriteTarget(token, { taskDir: TASK_DIR, projectRoot: PROJECT }),
		);
		console.log(`[VERIFY] VC-011: dir_blind_bypass=${bypassed.length} checked=${negatives.length}`);
		expect(bypassed).toEqual([]);
	});

	it("the own-taskDir relative form stays allowed (fixture semantics, VC-046)", () => {
		expect(
			isWhitelistedWriteTarget(".agenticdoc/k/workers/t02/report.md", { taskDir: TASK_DIR, projectRoot: PROJECT }),
		).toBe(true);
	});
});

// ── VC-015/016/018: target-shape axis (AC-004) ──────────────────────────────

describe("AC-004 target-shape axis (VC-015)", () => {
	const leakSamples = ["config.toml", "Makefile", ".env", "x.html", "x.rs"];

	it("the five QG-B leak samples are refused (leak_caught=5/5)", () => {
		const missed = leakSamples.filter((token) => verdict(`写入 ${token}`).ok);
		console.log(`[VERIFY] VC-015: leak_caught=${leakSamples.length - missed.length}/${leakSamples.length}`);
		expect(missed).toEqual([]);
	});

	it("controls: the framework channel stays open, the pre-existing extension case stays refused", () => {
		expect(verdict("写入 report.md").ok).toBe(true);
		expect(verdict("写入 a.ts").ok).toBe(false);
	});
});

describe("AC-004 shape discovery (VC-016)", () => {
	it("no-extension and non-enumerated extensions are discovered", () => {
		for (const token of [".agenticdoc/_index.parallel", ".git/config", "packages/x.rs"]) {
			const hits = collectWriteIntentHits(`写入 ${token}`);
			expect(
				hits.map((h) => h.path),
				token,
			).toContain(token);
		}
	});
});

describe("AC-004 bare tokens introduce no false positives (VC-018)", () => {
	const proseTokens = ["your", "design", "mcp", "side", "surface", "message_update", "-pattern"];

	it("prose words are discovered as tokens but pass the shape filter", () => {
		const falsePositives = proseTokens.filter((token) => !verdict(`写入 ${token}`).ok);
		console.log(`[VERIFY] VC-018: bare_token_fp=${falsePositives.length} checked=${proseTokens.length}`);
		expect(falsePositives).toEqual([]);
	});
});

// ── VC-012/013/017/019: the target axis internals (AC-003/AC-004) ────────────

/** Real temp tree for the axis-internals cases; returns the write-surface ctx. */
function axisCtx(): { root: string; keyDir: string; taskDir: string; ctx: Parameters<typeof judgeWriteTarget>[1] } {
	const root = mkdtemp();
	const agenticdocRoot = path.join(root, ".agenticdoc");
	const keyDir = path.join(agenticdocRoot, "k");
	const taskDir = path.join(keyDir, "workers", "t");
	fs.mkdirSync(taskDir, { recursive: true });
	return { root, keyDir, taskDir, ctx: { taskDir, projectRoot: root, keyDir, trueRoot: agenticdocRoot } };
}

describe("AC-004 containment uses one normalizer (read-scope parity, VC-012)", () => {
	it("judgeWriteTarget matches read-scope containment on the `..` and segment-boundary matrix", () => {
		const { root, keyDir, taskDir, ctx } = axisCtx();
		const agenticdocRoot = path.join(root, ".agenticdoc");
		const matrix: Array<{ p: string; want: boolean }> = [
			{ p: path.join(taskDir, "report.md"), want: true },
			{ p: path.join(taskDir, "..", "t2", "report.md"), want: false },
			{ p: path.join(agenticdocRoot, "kk", "evidence", "x.md"), want: false },
			{ p: path.join(keyDir, "workers", "t", "..", "t", "notes.md"), want: true },
		];
		for (const c of matrix) {
			const parity = isSameOrUnder(normalizeForCompare(root, taskDir), normalizeForCompare(root, c.p));
			expect(parity, c.p).toBe(c.want);
			expect(judgeWriteTarget(c.p, ctx).allowed, c.p).toBe(c.want);
		}
		console.log(`[VERIFY] VC-012: parity_cases=${matrix.length} normalizer=read-scope`);
	});
});

describe("AC-004 own surface and framework names still pass (VC-013)", () => {
	it("own taskDir absolute + framework basenames are allowed under the deny table", () => {
		const { taskDir, ctx } = axisCtx();
		expect(judgeWriteTarget(path.join(taskDir, "notes.md"), ctx).allowed).toBe(true);
		expect(judgeWriteTarget("report.md", ctx).allowed).toBe(true);
		expect(judgeWriteTarget("report-adversarial.md", ctx).allowed).toBe(true);
		expect(judgeWriteTarget("progress.md", ctx).allowed).toBe(true);
		expect(judgeWriteTarget("output.md", ctx).allowed).toBe(true);
		expect(judgeWriteTarget("trace.log", ctx).allowed).toBe(true);
	});
});

describe("AC-004 deny prefix outranks the shape branch (VC-017)", () => {
	it("pm-state.md / workers/_workers* / _index.parallel return rule=deny", () => {
		const { root, keyDir, ctx } = axisCtx();
		const agenticdocRoot = path.join(root, ".agenticdoc");
		const cases: Array<{ token: string; detail: string }> = [
			{ token: path.join(keyDir, "pm-state.md"), detail: "denied:pm-state.md" },
			{ token: path.join(keyDir, "workers", "_workers.parallel"), detail: "denied:workers/_workers*" },
			{ token: path.join(agenticdocRoot, "_index.parallel"), detail: "denied:_index.parallel" },
			{
				token: path.join(agenticdocRoot, "other-key", "pm-state.md"),
				detail: "denied:other key dir / .agenticdoc root",
			},
		];
		for (const c of cases) {
			const judged = judgeWriteTarget(c.token, ctx);
			expect(judged.allowed, c.token).toBe(false);
			expect(judged.rule, c.token).toBe("deny");
			expect(judged.detail, c.token).toBe(c.detail);
		}
		console.log(`[VERIFY] VC-017: deny_cases=${cases.length} deny_outranks_shape=true`);
	});
});

describe("AC-004 shape table (VC-015/VC-019)", () => {
	it("classifies the token without enumerating extensions", () => {
		const { root, ctx } = axisCtx();
		const shapes: Array<{ token: string; shape: string }> = [
			{ token: "/", shape: "punct" },
			{ token: "1.2.3", shape: "version" },
			{ token: "e.g.", shape: "abbrev" },
			{ token: "your", shape: "bare" },
			{ token: "message_update", shape: "bare" },
			{ token: "-pattern", shape: "bare" },
			{ token: ".env", shape: "dot-lead" },
			{ token: "config.toml", shape: "ext" },
			{ token: "x.rs", shape: "ext" },
			{ token: "Makefile", shape: "deny-name" },
			{ token: "package.json::$DATA", shape: "ads" },
			{ token: "C:foo.md", shape: "drive-relative" },
			{ token: "packages/x.rs", shape: "sep" },
		];
		for (const c of shapes) expect(classifyWriteTargetShape(c.token, { projectRoot: root }), c.token).toBe(c.shape);
		// Deny-name and shape-only refusal carry distinct rules (AC-008 branches).
		expect(judgeWriteTarget("Makefile", ctx).rule).toBe("scope");
		expect(judgeWriteTarget("config.toml", ctx).shape).toBe("ext");
		console.log(`[VERIFY] VC-015: shape_table=${shapes.length} extensions_enumerated=0`);
	});

	it("Windows boundary rulings (VC-019): every form lands on the refusal side", () => {
		const { taskDir, ctx } = axisCtx();
		// W1: `..`/duplicate separators collapse lexically (own surface stays allowed).
		expect(judgeWriteTarget(path.join(taskDir, ".", "..", "t", "output.md"), ctx).allowed).toBe(true);
		// W3: drive-relative `C:foo` is unjudgeable statically => refuse.
		expect(judgeWriteTarget("C:foo", ctx)).toMatchObject({ allowed: false, shape: "drive-relative" });
		// W4: UNC share => path shape outside the surface => refuse.
		expect(judgeWriteTarget("//server/share/x.md", ctx).allowed).toBe(false);
		// W5: long-path prefix => path shape outside the surface => refuse.
		expect(judgeWriteTarget("\\\\?\\H:\\x\\y.md", ctx).allowed).toBe(false);
		// W6: trailing dot/space inside the own surface is still the own surface.
		expect(judgeWriteTarget(path.join(taskDir, "report.md."), ctx).allowed).toBe(true);
		expect(judgeWriteTarget("Makefile.", ctx)).toMatchObject({ allowed: false, shape: "deny-name" });
		// W7: ADS stream form is labelled `ads` (before `ext`) and refused.
		expect(judgeWriteTarget("x.md::$DATA", ctx)).toMatchObject({ allowed: false, shape: "ads" });
		// W9: non-ASCII filenames are still outside the token character class.
		//          Documented fail-open residual R-4 (no CJK in the extraction axis).
		const cjk = collectWriteIntentHits("写入 报告.md");
		console.log(`[VERIFY] VC-019: w9_cjk_hits=${cjk.length} (documented residual, fail-open)`);
		expect(cjk).toEqual([]);
	});

	it("Windows case-insensitive containment (W2)", () => {
		if (process.platform !== "win32") {
			console.log("[VERIFY] VC-019: w2_skipped_non_win32");
			return;
		}
		const { taskDir, ctx } = axisCtx();
		const upper = path.join(taskDir.toUpperCase(), "REPORT.MD");
		expect(judgeWriteTarget(upper, ctx).allowed).toBe(true);
		console.log(`[VERIFY] VC-019: w2_case_fold path=${upper}`);
	});
});

describe("AC-005a shell role research is not refused (VC-015 /reverse c)", () => {
	it("research gets the contract section + default write_scope instead of a refusal", async () => {
		const root = mkdtemp();
		const notes = await runWorkerCommand(
			root,
			"pi --type research --key _scratch 输出到 .agenticdoc/other/evidence/x.md",
			"_scratch",
		);
		expect(notes.notifications.some((n) => n.message.includes("Dispatched"))).toBe(true);
		const taskKey = soleTaskKey(root, "_scratch");
		const md = readTaskMd(root, "_scratch", taskKey);
		expect(markerCount(md, WRITE_SURFACE_MARKER)).toBe(1);
		expect(md).toContain(`write_scope: .agenticdoc/_scratch/workers/${taskKey}, .agenticdoc/_scratch/evidence`);
		expect(isWritelessRole("research")).toBe(true);
		expect(isShellRole("research")).toBe(true);
	});
});

describe("AC-005a escape hatch allow_foreign_write (VC-019 /reverse e)", () => {
	it("judge allows, and the audit key lands in the task.md frontmatter", async () => {
		const direct = verdict("写到 .agenticdoc/other/evidence/x.md", "review", true);
		expect(direct.ok).toBe(true);

		const root = mkdtemp();
		const notes = await runWorkerCommand(
			root,
			"pi --type review --key _scratch --allow-foreign-write 写到 .agenticdoc/other/evidence/x.md",
			"_scratch",
		);
		expect(notes.notifications.some((n) => n.message.includes("Dispatched"))).toBe(true);
		const taskKey = soleTaskKey(root, "_scratch");
		const md = readTaskMd(root, "_scratch", taskKey);
		expect(md).toContain("allow_foreign_write: true");
		expect(markerCount(md, WRITE_SURFACE_MARKER)).toBe(1);
		console.log("[VERIFY] VC-019: allow_foreign_write=true recorded_in_task_md=true");
	});

	it("writeDispatchTaskMd records the audit key when invoked directly", () => {
		const root = mkdtemp();
		const written = writeDispatchTaskMd(
			{ agenticdocRoot: root, ownerKey: "_scratch" },
			{
				taskKey: "t-escape",
				type: "review",
				body: "work",
				frontmatter: "type: review\n",
				injectWriteSurface: true,
				allowForeignWrite: true,
			},
		);
		expect(fs.readFileSync(written.path, "utf8")).toContain("allow_foreign_write: true");
	});
});

describe("AC-005a refusal text (VC-015)", () => {
	it("names the code, the path and the three ways forward", () => {
		const text = writeIntentRefusal({ taskKey: "t-1", type: "review", path: ".agenticdoc/other/evidence/x.md" });
		expect(text).toContain("[worker-write-surface]");
		expect(text).toContain("t-1");
		expect(text).toContain("review");
		expect(text).toContain(".agenticdoc/other/evidence/x.md");
		expect(text).toContain("worker_file");
		expect(text).toContain("allow_foreign_write");
		expect(text).toContain("type: coding | repair | vision");
	});
});

// ── AC-008 branch coverage + T-04 residuals (T-10 / BR-14, R-1…R-4, W9) ─────

describe("AC-008/BR-14 shape-axis window bound (ui-bridge.ts:1402-1406)", () => {
	it("a >32-char verb-to-path gap leaks by design; <=32 is discovered", () => {
		// WRITE_INTENT_PATH_WINDOW = 32: gapLen > 32 is dropped (the documented
		// window leak), so the boundary is pinned on both sides.
		expect(collectWriteIntentHits(`写入${" ".repeat(32)}config.toml`).map((h) => h.path)).toEqual(["config.toml"]);
		expect(collectWriteIntentHits(`写入${" ".repeat(33)}config.toml`).map((h) => h.path)).toEqual([]);
		console.log("[VERIFY] AC-008/BR-14: gap_32_hit=1 gap_33_hit=0 window=32 documented_leak=1");
	});
});

describe("AC-008 T-04 residuals R-1…R-4 / W9 (documented limitations)", () => {
	it("R-1: path-shaped prose is refused (fail-closed, the safe direction)", () => {
		const tokens = ["foo.bar", "and/or", "12:30", "write_scope:"];
		const observed = tokens.map((token) => ({
			token,
			shape: classifyWriteTargetShape(token, { projectRoot: PROJECT }),
			ok: verdict(`写入 ${token}`).ok,
		}));
		expect(observed).toEqual([
			{ token: "foo.bar", shape: "ext", ok: false },
			{ token: "and/or", shape: "sep", ok: false },
			{ token: "12:30", shape: "colon", ok: false },
			{ token: "write_scope:", shape: "colon", ok: false },
		]);
		console.log("[VERIFY] AC-008/R-1: path_shaped_prose_refused=4 fail_closed=1");
	});

	it("R-2: a path after a prose word in the same clause is not discovered (fail-open)", () => {
		const text = "write your report to .agenticdoc/other/evidence/x.md";
		expect(collectWriteIntentHits(text).map((h) => h.path)).toEqual(["your"]);
		// `your` is a bare token: discovered, never refused. The later path is lost.
		expect(verdict(text).ok).toBe(true);
		console.log("[VERIFY] AC-008/R-2: hits=1 token=your later_path_lost=1 fail_open=1");
	});

	it("R-3: a new extension-less bare name is allowed; the 11-name deny table still refuses", () => {
		expect(classifyWriteTargetShape("Taskfile", { projectRoot: PROJECT })).toBe("bare");
		expect(verdict("写入 Taskfile").ok).toBe(true);
		// Control: a name in the finite deny table is refused.
		expect(classifyWriteTargetShape("Makefile", { projectRoot: PROJECT })).toBe("deny-name");
		expect(verdict("写入 Makefile").ok).toBe(false);
		console.log("[VERIFY] AC-008/R-3: Taskfile_allowed=1 Makefile_refused=1");
	});

	it("R-4/W9: a token that starts with a CJK character is not extracted (cjk_hits=0)", () => {
		expect(collectWriteIntentHits("写入 报告.md")).toEqual([]);
		// A CJK segment after an ASCII prefix truncates the token at the CJK char,
		// so only the ASCII prefix is judged (and refused as a separator shape).
		expect(collectWriteIntentHits("写入 .agenticdoc/keys/报告/evidence/x.md").map((h) => h.path)).toEqual([
			".agenticdoc/keys/",
		]);
		console.log("[VERIFY] AC-008/R-4: cjk_start_hits=0 cjk_truncated_prefix=1");
	});
});
