/**
 * mw-key-write-journal regressions: PM-window write journal + mw done
 * finalizer. Drives the real `pi.on("tool_result")` handler registered by
 * registerPmWriteJournal, and the real TS → Python finalizeChangeSet path.
 */
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { fauxAssistantMessage, fauxToolCall } from "@earendil-works/pi-ai";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ToolResultEvent } from "../../src/core/extensions/types.ts";
import { finalizeChangeSet } from "../../src/extensions/agent-team-loop/shared/agentic-scripts.ts";
import { acquireLock } from "../../src/extensions/agent-team-loop/shared/file-lock.ts";
import { currentClaimId } from "../../src/extensions/agent-team-loop/shared/implementation-gate.ts";
import {
	appendJournalEvents,
	bashWriteTargets,
	isProcessState,
	journalEventsForResult,
	journalPath,
	type PmJournalEvent,
	registerPmWriteJournal,
} from "../../src/extensions/agent-team-loop/shared/write-journal.ts";
import { createHarness } from "./harness.ts";

const SUITE_DIR = path.dirname(fileURLToPath(import.meta.url));
const REAL_MW_PY = path.resolve(SUITE_DIR, "../../../../packages/multi-workers/mw.py");
const PYTHON_EXE = process.platform === "win32" ? "python" : "python3";
const pythonAvailable = spawnSync(PYTHON_EXE, ["-c", "print(1)"], { encoding: "utf8", timeout: 5000 }).status === 0;
const originalWorkerTask = process.env.PI_WORKER_TASK;
const originalMwPy = process.env.MW_PY;
const roots: string[] = [];

function fixture(): string {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-write-journal-"));
	roots.push(root);
	fs.mkdirSync(path.join(root, ".agenticdoc", "sample"), { recursive: true });
	return root;
}

function result(toolName: string, input: Record<string, unknown>, isError = false): ToolResultEvent {
	return {
		type: "tool_result",
		toolCallId: "call-1",
		toolName,
		input,
		content: [],
		isError,
	} as unknown as ToolResultEvent;
}

function fakePi(): { pi: ExtensionAPI; handlers: Array<(event: ToolResultEvent) => Promise<void> | void> } {
	const handlers: Array<(event: ToolResultEvent) => Promise<void> | void> = [];
	const pi = {
		on: (name: string, handler: unknown): void => {
			if (name === "tool_result") handlers.push(handler as (event: ToolResultEvent) => Promise<void> | void);
		},
	} as unknown as ExtensionAPI;
	return { pi, handlers };
}

function indexWith(rows: string[]): string {
	return [
		"# Index Parallel",
		"",
		"| Key | Status | Phase | ClaimId | Deps | Desc | Updated |",
		"|-----|--------|-------|---------|------|------|---------|",
		...rows,
		"",
	].join("\n");
}

beforeEach(() => {
	delete process.env.PI_WORKER_TASK;
});

afterEach(() => {
	if (originalWorkerTask === undefined) delete process.env.PI_WORKER_TASK;
	else process.env.PI_WORKER_TASK = originalWorkerTask;
	if (originalMwPy === undefined) delete process.env.MW_PY;
	else process.env.MW_PY = originalMwPy;
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

describe("bash write target extraction", () => {
	it("records literal redirects, reports dynamic ones, ignores non-writes", () => {
		expect(bashWriteTargets("echo hi > src/a.ts && echo more >> docs/log.md")).toEqual({
			resolved: ["src/a.ts", "docs/log.md"],
			unresolved: [],
		});
		expect(bashWriteTargets("echo hi > $OUT").unresolved).toEqual(["$OUT"]);
		expect(bashWriteTargets("cmd 2>&1 > /dev/null")).toEqual({ resolved: [], unresolved: [] });
		expect(bashWriteTargets("tee report.txt").unresolved).toEqual(["(write verb target unparsed)"]);
		expect(bashWriteTargets('echo "a > b"')).toEqual({ resolved: [], unresolved: [] });
		expect(bashWriteTargets("git status")).toEqual({ resolved: [], unresolved: [] });
	});
});

describe("journal path scope", () => {
	it("normalizes to repo-relative and excludes all of .agenticdoc/", () => {
		const root = fixture();
		expect(journalPath("src/a.ts", root)).toBe("src/a.ts");
		expect(journalPath(path.join(root, "docs", "b.md"), root)).toBe("docs/b.md");
		expect(isProcessState(".agenticdoc/sample/evidence/x.md")).toBe(true);
		expect(isProcessState(journalPath(path.join(root, ".agenticdoc", "sample", "x.md"), root))).toBe(true);
		expect(isProcessState("src/a.ts")).toBe(false);
	});
});

describe("journalEventsForResult", () => {
	it("records only successful PM writes outside .agenticdoc/", () => {
		const root = fixture();
		const written = journalEventsForResult(result("write", { path: "src/a.ts", content: "x" }), "sample", root);
		expect(written).toHaveLength(1);
		expect(written[0]).toMatchObject({ key: "sample", source: "pm-tool-result", tool: "write", path: "src/a.ts" });
		expect(journalEventsForResult(result("edit", { path: "src/a.ts" }, true), "sample", root)).toEqual([]);
		expect(
			journalEventsForResult(result("write", { path: ".agenticdoc/sample/evidence/x.md" }), "sample", root),
		).toEqual([]);
		expect(journalEventsForResult(result("read", { path: "src/a.ts" }), "sample", root)).toEqual([]);
		const bash = journalEventsForResult(result("bash", { command: "echo x > src/b.ts" }), "sample", root);
		expect(bash).toEqual([expect.objectContaining({ tool: "bash", path: "src/b.ts" })]);
		const dynamic = journalEventsForResult(result("bash", { command: "echo x > $OUT" }), "sample", root);
		expect(dynamic).toEqual([expect.objectContaining({ source: "unresolved", target: "$OUT" })]);
	});
});

describe("registerPmWriteJournal", () => {
	it("does not journal a successful write to another Codex key from an unbound pi window", async () => {
		const root = fixture();
		const doc = path.join(root, ".agenticdoc");
		fs.writeFileSync(
			path.join(doc, "_index.parallel"),
			indexWith(["| sample | active | EXECUTE | codex | | | now |"]),
		);
		const harness = await createHarness({
			extensionFactories: [(pi) => registerPmWriteJournal(pi, root, () => undefined)],
		});
		try {
			const target = path.join(root, "output.txt");
			harness.setResponses([
				fauxAssistantMessage(fauxToolCall("write", { path: target, content: "written" }), {
					stopReason: "toolUse",
				}),
				fauxAssistantMessage("Done"),
			]);
			await harness.session.prompt("Write the fixture file");

			expect(fs.readFileSync(target, "utf8")).toBe("written");
			expect(fs.existsSync(path.join(doc, "sample", "write-journal.jsonl"))).toBe(false);
		} finally {
			harness.cleanup();
		}
	});

	it.each([
		["transferred to another window", "EXECUTE", "foreign:1"],
		["closed while the claim row is still active", "DONE", currentClaimId()],
	])("stops journaling when the watched key is %s", async (_scenario, phase, owner) => {
		const root = fixture();
		const doc = path.join(root, ".agenticdoc");
		const index = path.join(doc, "_index.parallel");
		fs.writeFileSync(index, indexWith([`| sample | active | EXECUTE | ${currentClaimId()} | | | now |`]));
		const harness = await createHarness({
			extensionFactories: [(pi) => registerPmWriteJournal(pi, root, () => "sample")],
		});
		try {
			const positive = path.join(root, "before.txt");
			const journal = path.join(doc, "sample", "write-journal.jsonl");
			harness.setResponses([
				fauxAssistantMessage(fauxToolCall("write", { path: positive, content: "before" }), {
					stopReason: "toolUse",
				}),
				fauxAssistantMessage("Done"),
			]);
			await harness.session.prompt("Write before reassignment");
			const before = fs.readFileSync(journal, "utf8");
			expect(JSON.parse(before)).toMatchObject({ key: "sample", path: "before.txt" });

			fs.writeFileSync(
				index,
				indexWith([
					`| sample | active | ${phase} | ${owner} | | | now |`,
					`| replacement | active | EXECUTE | ${currentClaimId()} | | | now |`,
				]),
			);
			const negative = path.join(root, "after.txt");
			harness.setResponses([
				fauxAssistantMessage(fauxToolCall("write", { path: negative, content: "after" }), {
					stopReason: "toolUse",
				}),
				fauxAssistantMessage("Done"),
			]);
			await harness.session.prompt("Write after reassignment");

			expect(fs.readFileSync(negative, "utf8")).toBe("after");
			expect(fs.readFileSync(journal, "utf8")).toBe(before);
			expect(fs.existsSync(path.join(doc, "replacement", "write-journal.jsonl"))).toBe(false);
		} finally {
			harness.cleanup();
		}
	});

	it.each([
		["multiple owned keys without a watch", [`| second | active | EXECUTE | ${currentClaimId()} | | | now |`]],
		["a duplicate key owned by another window", ["| SAMPLE | active | EXECUTE | foreign:1 | | | now |"]],
		["a malformed authority row", ["| truncated | active | EXECUTE |"]],
	])("does not append when the index has %s", async (_scenario, additionalRows) => {
		const root = fixture();
		const doc = path.join(root, ".agenticdoc");
		fs.writeFileSync(
			path.join(doc, "_index.parallel"),
			indexWith([`| sample | active | EXECUTE | ${currentClaimId()} | | | now |`, ...additionalRows]),
		);
		const harness = await createHarness({
			extensionFactories: [(pi) => registerPmWriteJournal(pi, root, () => undefined)],
		});
		try {
			await harness.session.extensionRunner.emitToolResult(result("write", { path: "src/a.ts" }));
			expect(fs.readdirSync(doc, { recursive: true })).not.toEqual(
				expect.arrayContaining([expect.stringContaining("write-journal.jsonl")]),
			);
		} finally {
			harness.cleanup();
		}
	});

	it("rechecks the watched claim after waiting on a concurrent index change", async () => {
		const root = fixture();
		const doc = path.join(root, ".agenticdoc");
		const index = path.join(doc, "_index.parallel");
		fs.writeFileSync(index, indexWith([`| sample | active | EXECUTE | ${currentClaimId()} | | | now |`]));
		const harness = await createHarness({
			extensionFactories: [(pi) => registerPmWriteJournal(pi, root, () => "sample")],
		});
		try {
			const release = await acquireLock(path.join(root, ".mw", "index.lock"));
			let write: Promise<unknown>;
			try {
				write = harness.session.extensionRunner.emitToolResult(result("write", { path: "src/a.ts" }));
				fs.writeFileSync(index, indexWith(["| sample | active | EXECUTE | foreign:1 | | | now |"]));
			} finally {
				release();
			}
			await write;
			expect(fs.existsSync(path.join(doc, "sample", "write-journal.jsonl"))).toBe(false);
		} finally {
			harness.cleanup();
		}
	});

	it("appends one JSON line per successful write into the key journal", async () => {
		const root = fixture();
		fs.writeFileSync(
			path.join(root, ".agenticdoc", "_index.parallel"),
			indexWith([`| sample | active | EXECUTE | ${currentClaimId()} |  |  | now |`]),
			"utf8",
		);
		const { pi, handlers } = fakePi();
		registerPmWriteJournal(pi, root, () => undefined);
		expect(handlers).toHaveLength(1);
		await handlers[0]!(result("write", { path: "src/a.ts" }));
		await handlers[0]!(result("edit", { path: "src/b.ts" }, true));
		await handlers[0]!(result("write", { path: ".agenticdoc/sample/evidence/x.md" }));
		const lines = fs
			.readFileSync(path.join(root, ".agenticdoc", "sample", "write-journal.jsonl"), "utf8")
			.trim()
			.split("\n")
			.map((line) => JSON.parse(line) as PmJournalEvent);
		expect(lines).toHaveLength(1);
		expect(lines[0]).toMatchObject({ key: "sample", source: "pm-tool-result", path: "src/a.ts" });
	});

	it("does not register in a worker window (its trace.log is the source)", () => {
		process.env.PI_WORKER_TASK = "C:/tmp/task.md";
		const { pi, handlers } = fakePi();
		registerPmWriteJournal(pi, fixture(), () => "sample");
		expect(handlers).toHaveLength(0);
	});

	it("appendJournalEvents is best-effort and never throws on a bad path", () => {
		expect(() =>
			appendJournalEvents(path.join("Z:", "missing", "key"), [
				{ ts: "now", key: "sample", source: "pm-tool-result", tool: "write", path: "src/a.ts" },
			]),
		).not.toThrow();
	});
});

describe("finalizeChangeSet (mw done hook)", () => {
	it.skipIf(!pythonAvailable || !fs.existsSync(REAL_MW_PY))(
		"runs the real Python finalizer and writes change-set.json",
		() => {
			const root = fixture();
			process.env.MW_PY = REAL_MW_PY;
			fs.writeFileSync(path.join(root, "src.ts"), "export const x = 1;\n", "utf8");
			fs.writeFileSync(
				path.join(root, ".agenticdoc", "sample", "achieved.md"),
				"## 系统行为变化\nChanged.\n\n## 修改面\n- `src.ts`\n\n## 遗留\nNone.\n",
				"utf8",
			);
			const outcome = finalizeChangeSet(root, "sample");
			expect(outcome.ok, outcome.output).toBe(true);
			expect(outcome.output).toContain("CHANGE-SET:");
			const data = JSON.parse(
				fs.readFileSync(path.join(root, ".agenticdoc", "sample", "change-set.json"), "utf8"),
			) as {
				files: Array<{ path: string; sha256: string }>;
				coverage: { complete: boolean };
			};
			expect(data.files.map((item) => item.path)).toEqual(["src.ts"]);
			expect(data.files[0]?.sha256).toHaveLength(64);
			expect(data.coverage.complete).toBe(false);
		},
	);

	it.skipIf(!pythonAvailable)("is loud when the finalizer is missing", () => {
		const root = fixture();
		const stubDir = path.join(root, "mwpkg");
		fs.mkdirSync(stubDir, { recursive: true });
		const mwPy = path.join(stubDir, "mw.py");
		fs.writeFileSync(mwPy, "# stub\n", "utf8");
		process.env.MW_PY = mwPy;
		const outcome = finalizeChangeSet(root, "sample");
		expect(outcome.ok).toBe(false);
		expect(outcome.output).toContain("CHANGE-SET UNAVAILABLE");
	});
});
