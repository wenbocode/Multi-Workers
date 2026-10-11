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
 * The judgement is the rule set from the card: write verb + a path that starts
 * right after it, five allow-guards (negation / read-marker / fenced code /
 * quotation / PM attribution), then the whitelist (worker_file basenames,
 * framework-owned names, own task dir). The corpus replay below is the hard
 * acceptance: on every `.agenticdoc/<key>/workers/<taskKey>/task.md` in the
 * repo, the writeless-without-shell set must yield at most two hits and zero false
 * positives — the one true positive is the R22 incident card the rule exists
 * for.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../src/core/extensions/types.ts";
import {
	applyWriteSurfaceContract,
	collectWriteIntentHits,
	isWhitelistedWriteTarget,
	judgeWriteIntent,
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
): Promise<{ notifications: NotifyRecord[]; store: WorkerStore }> {
	const { pi, commands, notifications, ctx } = fakePi();
	const store = new WorkerStore(root);
	registerWorkerCommands(pi, store, new IndexStore(root), root, { key: "_scratch" }, root);
	const handler = commands.get("worker");
	if (!handler) throw new Error("/worker not registered");
	await handler(args, ctx);
	return { notifications, store };
}

async function runDispatchWorker(root: string, params: Record<string, unknown>): Promise<string> {
	const { pi, tools, ctx } = fakePi();
	const store = new WorkerStore(root);
	registerWorkerTools(pi, store, new AckStore(root), new IndexStore(root), root, { key: "_scratch" }, root);
	const tool = tools.get("dispatch_worker");
	if (!tool) throw new Error("dispatch_worker not registered");
	const result = await tool.execute("id", params, undefined, undefined, ctx as unknown as ExtensionContext);
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
const TASK_DIR = path.join(PROJECT, "k", "workers", "t02");

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
		const notes = await runWorkerCommand(root, "pi --type coding --key _scratch 把结论写到 packages/foo/bar.ts");
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
		const notes = await runWorkerCommand(root, "pi --type review --key _scratch 分析 X 的失败原因，给出判定");
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

describe("AC-005a shell role research is not refused (VC-015 /reverse c)", () => {
	it("research gets the contract section + default write_scope instead of a refusal", async () => {
		const root = mkdtemp();
		const notes = await runWorkerCommand(
			root,
			"pi --type research --key _scratch 输出到 .agenticdoc/other/evidence/x.md",
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
