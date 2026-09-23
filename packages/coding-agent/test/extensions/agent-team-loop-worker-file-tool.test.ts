/**
 * Tests for the narrow worker_file tool (mw-worker-progress-persist T-2,
 * AC-005/AC-006, design D-101/D-102/D-109, §4.1).
 *
 * The suite config is `silent: "passed-only"` and swallows console.log from
 * green tests, so `[VERIFY]` lines go straight to stdout via
 * process.stdout.write.
 *
 * Covers:
 * - VC-005: append to progress.md after a pre-existing sentinel, whole-file
 *   writes of report.md / report-f1.md / report.r1.md, UTF-8 byte counts,
 * - VC-006: all 12 illegal file values rejected at the execute layer AND the
 *   schema layer, with the task directory set unchanged,
 * - fail-closed ordering: rejected calls do not create/truncate anything,
 * - the 64 KiB cap measured in UTF-8 bytes (multi-byte proof) and the slug
 *   length boundary,
 * - the D-109 failure shape: `execute` throws an Error (no `isError` result),
 * - the D-102 single source: schema `pattern` === WORKER_FILE_NAME_RE.source.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { type TSchema, Type } from "typebox";
import { Compile } from "typebox/compile";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	isAllowedWorkerFile,
	registerWorkerFileTool,
	WORKER_FILE_MAX_BYTES,
	WORKER_FILE_NAME_RE,
	WORKER_FILE_TOOL,
	writeWorkerFile,
} from "../../src/extensions/agent-team-loop/worker/worker-file-tool.ts";

/* The suite swallows console.log from green tests; write the evidence line
 * straight to stdout so the required command surfaces it. */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

const LEGAL_FILES = ["progress.md", "report.md", "report-f1.md", "report.r1.md"] as const;

/** VC-006 matrix (design D-102): path variants, evidence files, empty/.md, bad slug. */
const REJECTED_FILES = [
	"../x.md",
	"a/b.md",
	"..\\x.md",
	"C:\\abs\\x.md",
	"\\\\unc\\share\\x.md",
	"trace.log",
	"task.md",
	"output.md",
	"worker.log",
	"",
	".md",
	"report-.md",
] as const;

interface WorkerFileParams {
	file: string;
	content: string;
	mode?: "append" | "write";
}

interface CapturedTool {
	name: string;
	parameters: TSchema;
	execute: (
		toolCallId: string,
		params: WorkerFileParams,
		signal?: AbortSignal,
		onUpdate?: unknown,
		ctx?: unknown,
	) => Promise<{ content: Array<{ type: string; text: string }>; details: unknown }>;
}

/** Minimal fake ExtensionAPI that captures registered ToolDefinitions. */
function capturePi(): { pi: ExtensionAPI; tools: Map<string, CapturedTool> } {
	const tools = new Map<string, CapturedTool>();
	const pi = {
		registerTool: (tool: unknown) => {
			const captured = tool as CapturedTool;
			tools.set(captured.name, captured);
		},
	} as unknown as ExtensionAPI;
	return { pi, tools };
}

function registerTool(taskDir: string): CapturedTool {
	const { pi, tools } = capturePi();
	registerWorkerFileTool(pi, taskDir);
	const tool = tools.get(WORKER_FILE_TOOL);
	if (!tool) throw new Error("worker_file not registered");
	return tool;
}

const tmpRoots: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "atl-worker-file-"));
	tmpRoots.push(dir);
	return dir;
}

/** Existing, empty task dir. */
function mkTaskDir(): string {
	const dir = path.join(mkdtemp(), "task");
	fs.mkdirSync(dir, { recursive: true });
	return dir;
}

function snapshot(dir: string): string[] {
	if (!fs.existsSync(dir)) return [];
	return fs.readdirSync(dir).sort();
}

afterEach(() => {
	for (const dir of tmpRoots.splice(0)) {
		fs.rmSync(dir, { recursive: true, force: true });
	}
});

// ── D-102 basename whitelist ──────────────────────────────────────────────────

describe("WORKER_FILE_NAME_RE / isAllowedWorkerFile (D-102)", () => {
	it("accepts the whitelist set and rejects non-whitelist neighbors", () => {
		for (const file of LEGAL_FILES) {
			expect(isAllowedWorkerFile(file)).toBe(true);
		}
		for (const file of [
			"report..md",
			"PROGRESS.MD",
			"progress.markdown",
			"report.md.bak",
			"progress.md ",
			"progress.md\n",
		]) {
			expect(isAllowedWorkerFile(file)).toBe(false);
		}
		// No `g` flag: repeated calls must not flip on `lastIndex`.
		expect(isAllowedWorkerFile("progress.md")).toBe(true);
		expect(isAllowedWorkerFile("progress.md")).toBe(true);
	});
});

// ── VC-005: append + report writes ────────────────────────────────────────────

describe("writeWorkerFile (VC-005)", () => {
	it("VC-005: appends progress.md after a sentinel and writes report files; bytes match UTF-8 length", () => {
		const taskDir = mkTaskDir();

		// append: a pre-existing PM/self-assessment sentinel stays first and unchanged
		const sentinel = "CKPT 20m converging=yes 只差最后一段证据\n";
		fs.writeFileSync(path.join(taskDir, "progress.md"), sentinel, "utf8");
		const appended = "CKPT 30m [machine] risk=low 中文\n";
		const a = writeWorkerFile(taskDir, "progress.md", appended, "append");
		if (!a.ok) throw new Error(a.reason);
		const appendOk =
			fs.readFileSync(path.join(taskDir, "progress.md"), "utf8") === sentinel + appended &&
			a.bytes === Buffer.byteLength(appended, "utf8");

		// write: report.md, report-f1.md, report.r1.md each created and rewritten
		let reportOk = true;
		let bytesOk = true;
		for (const file of ["report.md", "report-f1.md", "report.r1.md"]) {
			const first = `first 中文 ${file}\n`;
			const w1 = writeWorkerFile(taskDir, file, first, "write");
			if (!w1.ok) throw new Error(w1.reason);
			const second = `rewritten ${file}`;
			const w2 = writeWorkerFile(taskDir, file, second, "write");
			if (!w2.ok) throw new Error(w2.reason);
			reportOk &&= fs.readFileSync(w2.path, "utf8") === second;
			bytesOk &&= w1.bytes === Buffer.byteLength(first, "utf8") && w2.bytes === Buffer.byteLength(second, "utf8");
		}
		expect(snapshot(taskDir)).toEqual(["progress.md", "report-f1.md", "report.md", "report.r1.md"]);

		verify(`[VERIFY] VC-005: append_ok=${appendOk} report_ok=${reportOk} bytes_ok=${bytesOk}`);
		expect(appendOk).toBe(true);
		expect(reportOk).toBe(true);
		expect(bytesOk).toBe(true);
	});
});

// ── VC-006: 12 rejections, execute + schema layers ────────────────────────────

describe("worker_file rejection (VC-006)", () => {
	it("VC-006: all 12 illegal file values rejected at execute and schema layers, dir set unchanged", async () => {
		const taskDir = mkTaskDir();
		const tool = registerTool(taskDir);
		fs.writeFileSync(path.join(taskDir, "progress.md"), "sentinel\n", "utf8");
		const before = snapshot(taskDir);
		const schemaCheck = Compile(Type.String({ pattern: WORKER_FILE_NAME_RE.source }));

		let execRejections = 0;
		let schemaRejections = 0;
		for (const file of REJECTED_FILES) {
			expect(isAllowedWorkerFile(file), `regex must reject ${JSON.stringify(file)}`).toBe(false);
			const r = writeWorkerFile(taskDir, file, "x", "append");
			expect(r.ok, `writeWorkerFile must reject ${JSON.stringify(file)}`).toBe(false);
			await expect(
				tool.execute("id", { file, content: "x" }, undefined, undefined, undefined),
				`execute must reject ${JSON.stringify(file)}`,
			).rejects.toThrow(/rejected/);
			execRejections += 1;
			if (schemaCheck.Check(file) === false) schemaRejections += 1;
		}

		expect(REJECTED_FILES).toHaveLength(12);
		expect(execRejections).toBe(12);
		expect(schemaRejections).toBe(12);
		const after = snapshot(taskDir);
		expect(after).toEqual(before);
		expect(fs.readFileSync(path.join(taskDir, "progress.md"), "utf8")).toBe("sentinel\n");
		verify(
			`[VERIFY] VC-006: rejections=${execRejections} new_files=${after.length - before.length} schema_rejections=${schemaRejections}`,
		);
	});

	it("execute throws an Error instance (D-109) and writes nothing", async () => {
		const taskDir = mkTaskDir();
		const tool = registerTool(taskDir);
		fs.writeFileSync(path.join(taskDir, "report.md"), "keep\n", "utf8");
		const before = snapshot(taskDir);

		let caught: unknown;
		try {
			await tool.execute("id", { file: "../x.md", content: "x" }, undefined, undefined, undefined);
		} catch (error) {
			caught = error;
		}
		expect(caught).toBeInstanceOf(Error);
		expect((caught as Error).message).toMatch(/^worker_file rejected: /);
		expect(snapshot(taskDir)).toEqual(before);
		expect(fs.readFileSync(path.join(taskDir, "report.md"), "utf8")).toBe("keep\n");
	});

	it("rejects fail-closed: no taskDir is created for an illegal name or oversize content", () => {
		const root = mkdtemp();
		const taskDir = path.join(root, "task-dir");

		const bad = writeWorkerFile(taskDir, "../x.md", "x", "append");
		expect(bad.ok).toBe(false);
		expect(fs.existsSync(taskDir)).toBe(false);

		const big = "中".repeat(Math.ceil(WORKER_FILE_MAX_BYTES / 3));
		expect(Buffer.byteLength(big, "utf8")).toBeGreaterThan(WORKER_FILE_MAX_BYTES);
		const oversize = writeWorkerFile(taskDir, "report-big.md", big, "write");
		expect(oversize.ok).toBe(false);
		expect(fs.existsSync(taskDir)).toBe(false);
	});
});

// ── 64 KiB byte cap + slug boundary ───────────────────────────────────────────

describe("size and slug limits", () => {
	it("caps content at 64 KiB UTF-8 bytes (multi-byte proof), accepts exactly the cap", () => {
		const taskDir = mkTaskDir();
		// 21846 code units (< 65536, so a maxLength schema gate would leak) but 65538 UTF-8 bytes.
		const big = "中".repeat(Math.ceil(WORKER_FILE_MAX_BYTES / 3));
		expect(big.length).toBeLessThanOrEqual(WORKER_FILE_MAX_BYTES);
		expect(Buffer.byteLength(big, "utf8")).toBeGreaterThan(WORKER_FILE_MAX_BYTES);
		const rejected = writeWorkerFile(taskDir, "report-big.md", big, "write");
		expect(rejected.ok).toBe(false);
		expect(snapshot(taskDir)).toEqual([]);

		const exact = "a".repeat(WORKER_FILE_MAX_BYTES);
		const accepted = writeWorkerFile(taskDir, "report-cap.md", exact, "write");
		if (!accepted.ok) throw new Error(accepted.reason);
		expect(accepted.bytes).toBe(WORKER_FILE_MAX_BYTES);
		expect(fs.statSync(accepted.path).size).toBe(WORKER_FILE_MAX_BYTES);
	});

	it("enforces the slug length boundary (41 allowed, 42 rejected)", () => {
		const allowed = `report-${"a".repeat(41)}.md`;
		const rejected = `report-${"a".repeat(42)}.md`;
		expect(isAllowedWorkerFile(allowed)).toBe(true);
		expect(isAllowedWorkerFile(rejected)).toBe(false);

		const taskDir = mkTaskDir();
		expect(writeWorkerFile(taskDir, rejected, "x", "write").ok).toBe(false);
		expect(snapshot(taskDir)).toEqual([]);
		expect(writeWorkerFile(taskDir, allowed, "x", "write").ok).toBe(true);
		expect(snapshot(taskDir)).toEqual([allowed]);
	});
});

// ── execute success path + schema single source (D-102/F2) ────────────────────

describe("registerWorkerFileTool (D-109 / §4.1)", () => {
	it("execute defaults mode to append and reports path/bytes", async () => {
		const taskDir = mkTaskDir();
		const tool = registerTool(taskDir);
		fs.writeFileSync(path.join(taskDir, "progress.md"), "a\n", "utf8");

		const content = "b 中文\n";
		const res = await tool.execute("id1", { file: "progress.md", content });
		expect(res.details).toEqual({});
		expect(res.content[0]?.text).toBe(
			`wrote ${Buffer.byteLength(content, "utf8")} bytes to ${path.join(taskDir, "progress.md")} (append)`,
		);
		expect(fs.readFileSync(path.join(taskDir, "progress.md"), "utf8")).toBe(`a\n${content}`);

		const res2 = await tool.execute("id2", { file: "progress.md", content: "c\n", mode: "write" });
		expect(fs.readFileSync(path.join(taskDir, "progress.md"), "utf8")).toBe("c\n");
		expect(res2.content[0]?.text).toContain("(write)");
	});

	it("schema layer accepts the legal set, rejects the 12 variants and extra fields, and reuses the regex source", () => {
		const taskDir = mkTaskDir();
		const tool = registerTool(taskDir);
		const compiled = Compile(tool.parameters);

		for (const file of LEGAL_FILES) {
			expect(compiled.Check({ file, content: "x" }), `schema must accept ${file}`).toBe(true);
		}
		for (const file of REJECTED_FILES) {
			expect(compiled.Check({ file, content: "x" }), `schema must reject ${JSON.stringify(file)}`).toBe(false);
		}
		// additionalProperties:false
		expect(compiled.Check({ file: "progress.md", content: "x", extra: 1 })).toBe(false);
		// empty content is rejected at the schema layer (minLength 1)
		expect(compiled.Check({ file: "progress.md", content: "" })).toBe(false);

		const schema = tool.parameters as { properties?: { file?: { pattern?: string } } };
		expect(schema.properties?.file?.pattern).toBe(WORKER_FILE_NAME_RE.source);

		verify("[VERIFY] D-102/D-109: schema_pattern_single_source=true additional_properties_rejected=true");
	});
});
