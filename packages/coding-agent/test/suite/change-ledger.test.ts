/**
 * change-ledger.test.ts — T-05 / AC-004 (design §3.1): the reconciliation
 * between the worker's `改动清单` declaration and the machine `[WRITE_FILE]`
 * events in `trace.log`.
 *
 * Three required cases (the card's acceptance):
 *   1. declared ⊆ recorded          ⇒ `extra` empty (green);
 *   2. a declared file with no write event ⇒ `extra` non-empty (red) and names
 *      the off-ledger file;
 *   3. a trace with no `[WRITE_FILE]` line at all ⇒ not red, and with a
 *      non-empty declaration it is `unjudgeable` (never green, T-12/F-04);
 * Plus the producer half: a successful `worker_file` write appends exactly one
 * event (path only), a rejected write appends none.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import {
	diffLedger,
	formatWriteFileEvent,
	parseWriteFileEvents,
} from "../../src/extensions/agent-team-loop/shared/change-ledger.ts";
import { writeWorkerFile } from "../../src/extensions/agent-team-loop/worker/worker-file-tool.ts";

const tempDirs: string[] = [];

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TEST_DIR, "../../../..");

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "change-ledger-"));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

/** Report shape the recovery contract produces for `coding` (output-sections.ts
 * requires the `改动清单` section; this is its body form). */
function report(declared: string[]): string {
	return [
		"## 结论",
		"",
		"done",
		"",
		"## 改动清单",
		"",
		...declared.map((file) => `- ${file} — intent`),
		"",
		"## 残留与未验证",
		"",
		"none",
	].join("\n");
}

const LEDGER_FILE = "packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts";
const FILE_TOOL = "packages/coding-agent/src/extensions/agent-team-loop/worker/worker-file-tool.ts";
const WORKER_MODE = "packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts";

describe("diffLedger — declared ⊆ recorded", () => {
	it("equal sets are green (extra empty)", () => {
		const trace = [
			"[START] 2026-10-12T00:00:00.000Z task=t05 type=coding phases=-",
			`[TOOL] 2026-10-12T00:00:01.000Z write ${LEDGER_FILE}`,
			`[WRITE_FILE] path=${LEDGER_FILE}`,
			`[WRITE_FILE] path=${FILE_TOOL}`,
			`[WRITE_FILE] path=${FILE_TOOL}`, // duplicate call ⇒ one recorded entry
		].join("\n");

		const ledger = diffLedger(report([LEDGER_FILE, FILE_TOOL]), trace);

		expect(ledger.declared).toEqual([LEDGER_FILE, FILE_TOOL]);
		expect(ledger.recorded).toEqual([LEDGER_FILE, FILE_TOOL]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("a declared file with no write event is red and names the file", () => {
		const trace = [`[WRITE_FILE] path=${LEDGER_FILE}`, `[WRITE_FILE] path=${FILE_TOOL}`].join("\n");

		const ledger = diffLedger(report([LEDGER_FILE, FILE_TOOL, WORKER_MODE]), trace, { projectRoot: REPO_ROOT });

		expect(ledger.declared).toEqual([LEDGER_FILE, FILE_TOOL, WORKER_MODE]);
		expect(ledger.extra).toEqual([WORKER_MODE]);
	});

	it("a trace with no [WRITE_FILE] line and a declaration is unjudgeable, not green (T-12/F-04)", () => {
		const legacyTrace = [
			"[START] pid=42",
			"[TOOL] 2026-09-01T00:00:00.000Z write src/legacy.ts",
			"[END] 2026-09-01T00:10:00.000Z exit=0 elapsed=600s tools=12 phases=-",
		].join("\n");

		const ledger = diffLedger(report([WORKER_MODE]), legacyTrace, { projectRoot: REPO_ROOT });

		expect(ledger.recorded).toEqual([]);
		expect(ledger.declared).toEqual([WORKER_MODE]);
		expect(ledger.extra).toEqual([]);
		// A declaration that the trace cannot confirm or refute must not read as
		// a clean pass (the bash-bypass / legacy ambiguity).
		expect(ledger.unjudgeable).toBe(true);
	});

	it("a trace with no [WRITE_FILE] line and no declaration is trivially green", () => {
		const legacyTrace = "[START] pid=42\n[END] exit=0\n";
		const ledger = diffLedger(report([]), legacyTrace);
		expect(ledger.declared).toEqual([]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("a bash write event makes a shell-only run judgeable (T-12/F-04)", () => {
		// The producer half lives in worker-mode.ts; here the trace shape is the
		// contract: a bash write target recorded as [WRITE_FILE] reconciles green.
		const trace = ["[START] pid=42", `[WRITE_FILE] path=${LEDGER_FILE}`].join("\n");
		const ledger = diffLedger(report([LEDGER_FILE]), trace);
		expect(ledger.recorded).toEqual([LEDGER_FILE]);
		expect(ledger.extra).toEqual([]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("a report without 改动清单 declares nothing", () => {
		const reportText = "## 结论\n\ndone\n\n## 证据\n\ncommands\n";
		const trace = `[WRITE_FILE] path=${LEDGER_FILE}`;

		expect(diffLedger(reportText, trace)).toEqual({
			declared: [],
			recorded: [LEDGER_FILE],
			extra: [],
			// T-17b/T-17c: the ledger verdict carries the (empty) framework-infra and
			// off-disk channels alongside the three T-05 fields. `toEqual` is exact,
			// so the new fields must be named; the assertion itself is unchanged.
			infra: [],
			unresolvable: [],
			unjudgeable: false,
		});
	});

	it("absolute trace paths match repo-relative declarations (and windows separators)", () => {
		const trace = [`[WRITE_FILE] path=H:\\git\\Multi-Workers\\${FILE_TOOL.replace(/\//g, "\\")}`].join("\n");

		const ledger = diffLedger(report([FILE_TOOL]), trace);

		expect(ledger.declared).toEqual([FILE_TOOL]);
		expect(ledger.extra).toEqual([]);
	});

	it("parses only path-shaped statements from the section body", () => {
		const reportText = [
			"## 改动清单（文件+意图）",
			"",
			"- 新增 `shared/change-ledger.ts`：实现 diffLedger",
			"- worker/worker-mode.ts 最小改动",
			"- 无其他文件",
		].join("\n");
		const trace = `[WRITE_FILE] path=shared/change-ledger.ts\n[WRITE_FILE] path=worker/worker-mode.ts`;

		const ledger = diffLedger(reportText, trace);

		expect(ledger.declared).toEqual(["shared/change-ledger.ts", "worker/worker-mode.ts"]);
		expect(ledger.extra).toEqual([]);
	});
});

describe("[WRITE_FILE] event", () => {
	it("records the path only, never content", () => {
		const line = formatWriteFileEvent("src/a.ts");
		expect(line).toBe("[WRITE_FILE] path=src/a.ts");
		expect(parseWriteFileEvents(`${line}\n`)).toEqual(["src/a.ts"]);
	});

	it("ignores non-event lines and blank path values", () => {
		const trace = [
			"[WRITE_FILE] path=src/a.ts",
			"[TOOL] write src/b.ts",
			"prefix [WRITE_FILE] path=src/c.ts",
			"[WRITE_FILE]",
		].join("\n");
		expect(parseWriteFileEvents(trace)).toEqual(["src/a.ts"]);
	});
});

function writeFileLines(taskDir: string): string[] {
	return fs
		.readFileSync(path.join(taskDir, "trace.log"), "utf8")
		.split(/\r?\n/)
		.filter((line) => line.startsWith("[WRITE_FILE]"));
}

describe("producer — worker_file", () => {
	it("appends exactly one event per successful write and none for a rejected one", () => {
		const taskDir = mkdtemp();

		const ok = writeWorkerFile(taskDir, "report.md", "hello", "write");
		expect(ok.ok).toBe(true);

		const rejected = writeWorkerFile(taskDir, "../escape.md", "hello", "write");
		expect(rejected.ok).toBe(false);

		const events = writeFileLines(taskDir);
		expect(events).toHaveLength(1);
		expect(events[0].startsWith("[WRITE_FILE] path=")).toBe(true);
		expect(events[0].endsWith("report.md")).toBe(true);
	});

	it("appends one line per call without touching the written file's bytes", () => {
		const taskDir = mkdtemp();
		const tracePath = path.join(taskDir, "trace.log");
		fs.writeFileSync(tracePath, "[START] pid=1\n", "utf8");

		writeWorkerFile(taskDir, "progress.md", "note\n", "append");
		writeWorkerFile(taskDir, "progress.md", "more\n", "append");

		expect(fs.readFileSync(path.join(taskDir, "progress.md"), "utf8")).toBe("note\nmore\n");
		const events = writeFileLines(taskDir);
		expect(events).toHaveLength(2);
		expect(events.every((line) => line.endsWith("progress.md"))).toBe(true);
	});
});
