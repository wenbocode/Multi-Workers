/**
 * rag-required.test.ts — mw-rag-integration T-14 (AC-010/AC-015):
 *   VC-014  a required role/phase with no verifiable citation gets the shared
 *           `rag-required-missing` trace line + an output.md marker; a
 *           re-settle never duplicates either; a citation or a non-required /
 *           RAG-less project writes nothing.
 *   VC-020  the worker reads the task.md `phase:` header (write side is the
 *           dispatcher: Py `render_task_md` / TS `planDispatchFrontmatter`).
 *
 * The suite config uses `silent: "passed-only"`, which swallows console.log
 * from green tests — every `[VERIFY]` line goes through process.stdout.write.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { planDispatchFrontmatter } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { loadRagConfig } from "../../src/extensions/agent-team-loop/rag/config.ts";
import { validateResearchDoc } from "../../src/extensions/agent-team-loop/rag/research-doc.ts";
import {
	emitRagRequiredMissing,
	evidencePhase,
	parseTaskMd,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

const tempDirs: string[] = [];
let savedServersFile: string | undefined;
let serversFileSaved = false;

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	if (serversFileSaved) {
		if (savedServersFile === undefined) delete process.env.MW_RAG_SERVERS_FILE;
		else process.env.MW_RAG_SERVERS_FILE = savedServersFile;
		serversFileSaved = false;
	}
	delete process.env.PI_WORKER_TASK;
	delete process.env.PI_WORKER_IDLE_MS;
});

/** Skill-only server: valid config, no MCP block -> the activate probe makes
 * no network call (fast, hermetic). */
const SKILL_SERVER = `servers:
  A:
    transport: skill
    skill:
      dir: skills/a
      cli_entry: python a.py
`;

const TARGET_CODING_REQUIRED = `rag:
  enabled: [A]
  default_server: A
  roles:
    coding:
      server: A
      require: true
`;

/** Temp project + hermetic machine RAG layer (same shape as rag-tools.test.ts). */
function makeProject(target: string): string {
	const project = fs.mkdtempSync(path.join(os.tmpdir(), "rag-required-"));
	tempDirs.push(project);
	fs.mkdirSync(path.join(project, ".agenticdoc"), { recursive: true });
	fs.writeFileSync(path.join(project, ".agenticdoc", "target.yml"), target, "utf8");
	fs.mkdirSync(path.join(project, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(project, ".mw", "rag-servers.yml"), SKILL_SERVER, "utf8");
	if (!serversFileSaved) {
		savedServersFile = process.env.MW_RAG_SERVERS_FILE;
		serversFileSaved = true;
	}
	process.env.MW_RAG_SERVERS_FILE = path.join(project, "machine-does-not-exist.yml");
	return project;
}

/** Faux ExtensionAPI: captures `on` handlers so the test can drive the worker
 * lifecycle (the same pattern agent-team-loop.test.ts uses for watchdogs). */
function fakeWorkerPi(): { pi: ExtensionAPI; emit: (name: string, payload?: unknown) => void } {
	const handlers = new Map<string, Array<(event: unknown) => void>>();
	const pi = {
		on: (name: string, cb: (event: unknown) => void) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		registerTool: () => {},
		setActiveTools: () => {},
		getActiveTools: () => [],
		getAllTools: () => [],
		sendUserMessage: () => {},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		emit: (name, payload) => {
			for (const cb of handlers.get(name) ?? []) cb(payload);
		},
	};
}

async function startWorker(
	project: string,
	key: string,
	taskKey: string,
	body: string,
): Promise<{ taskDir: string; emit: (name: string, payload?: unknown) => void }> {
	const taskDir = path.join(project, ".agenticdoc", key, "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	const taskPath = path.join(taskDir, "task.md");
	fs.writeFileSync(taskPath, body, "utf8");
	const { pi, emit } = fakeWorkerPi();
	process.env.PI_WORKER_TASK = taskPath;
	process.env.PI_WORKER_IDLE_MS = "60000";
	await workerModeActivate(pi);
	return { taskDir, emit };
}

function read(taskDir: string, name: string): string {
	try {
		return fs.readFileSync(path.join(taskDir, name), "utf8");
	} catch {
		return "";
	}
}

function occurrences(text: string, needle: string): number {
	return text.split(needle).length - 1;
}

// ── VC-020: worker reads the phase header ───────────────────────────────────

describe("parseTaskMd reads the phase header (VC-020)", () => {
	it("returns the header value, and undefined when absent", () => {
		const dir = fs.mkdtempSync(path.join(os.tmpdir(), "rag-phase-"));
		tempDirs.push(dir);
		const withPhase = path.join(dir, "with-phase.md");
		fs.writeFileSync(withPhase, "type: coding\nphase: EXECUTE\n\nwork\n", "utf8");
		expect(parseTaskMd(withPhase).phase).toBe("EXECUTE");
		expect(parseTaskMd(withPhase).type).toBe("coding");

		const without = path.join(dir, "without-phase.md");
		fs.writeFileSync(without, "type: coding\n\nwork\n", "utf8");
		expect(parseTaskMd(without).phase).toBeUndefined();

		// The evidence-line fallback is the literal `unknown`, never a guess.
		expect(evidencePhase(undefined)).toBe("unknown");
		expect(evidencePhase("")).toBe("unknown");
		expect(evidencePhase("DESIGN")).toBe("DESIGN");

		verify("[VERIFY] VC-020: worker_reads_phase=true missing=unknown");
	});
});

// ── VC-020: TS dispatcher writes the phase header ───────────────────────────

describe("planDispatchFrontmatter phase header (VC-020)", () => {
	it("omits phase when unknown, appends it after type when known", () => {
		const cwd = fs.mkdtempSync(path.join(os.tmpdir(), "rag-phase-fm-"));
		tempDirs.push(cwd);
		const base = {
			cwd,
			cli: "pi",
			provider: "timi",
			taskType: "coding",
			model: "",
			modelReason: "",
			registry: undefined,
		};

		// Pre-T-14 bytes, pinned: no phase header at all.
		const omitted = planDispatchFrontmatter(base);
		if (!omitted.ok) throw new Error(omitted.message);
		expect(omitted.frontmatter).toBe("type: coding\n");

		// Explicit "" is the same as omitted (never a `phase:` line).
		const empty = planDispatchFrontmatter({ ...base, phase: "" });
		if (!empty.ok) throw new Error(empty.message);
		expect(empty.frontmatter).toBe(omitted.frontmatter);

		// Known phase: right after `type:`, before model/model-reason.
		const known = planDispatchFrontmatter({ ...base, phase: "EXECUTE" });
		if (!known.ok) throw new Error(known.message);
		expect(known.frontmatter).toBe("type: coding\nphase: EXECUTE\n");

		const modeled = planDispatchFrontmatter({
			...base,
			phase: "EXECUTE",
			model: "timi/foo",
			modelReason: "reason here",
		});
		if (!modeled.ok) throw new Error(modeled.message);
		expect(modeled.frontmatter).toBe("type: coding\nphase: EXECUTE\nmodel: timi/foo\nmodel-reason: reason here\n");

		verify("[VERIFY] VC-020: phase_written=true ts_empty_byte_identical=true");
	});
});

// ── VC-106 (T-17/D-107): VC-018 runtime evidence ────────────────────────────
// The runtime face of VC-018: a `rag-research` worker whose key dir carries
// the compliant deliverable at `.agenticdoc/<key>/rag/<server>-<slug>.md`.
// Driving `workerModeActivate` to its terminal settle must reach
// `validateResearchDoc` through the real key path (`path.dirname(agenticdocRoot)`),
// see the six sections + parseable citations, and therefore emit no
// `rag-required-missing` marker even though the agent's own reply has no
// citation. Without the doc the same path emits the marker.

const TARGET_RESEARCH_REQUIRED = `rag:
  enabled: [A]
  default_server: A
  roles:
    research:
      server: A
      require: true
`;

const RESEARCH_DOC = `# RAG 调研：symbol lookup

## 查询

原始问题：X 在哪里定义。

## 结论

- 结论 A：X 定义于 Runtime/Renderer/X.cpp。

## 引用

- \`A:code:engine::Runtime/Renderer/X.cpp:120\` exists=true local_path=Runtime/Renderer/X.cpp

## 未解决

- 无。

## 快照

- 索引快照：2026-09-22T10:00:00Z。

## 影响面

- Runtime/Renderer 与调用方。
`;

describe("VC-106 research-doc runtime evidence", () => {
	it("finds the compliant <server>-<slug>.md at the real key path and judges ok", async () => {
		const project = makeProject(TARGET_RESEARCH_REQUIRED);
		const { taskDir, emit } = await startWorker(
			project,
			"key-a",
			"w-research",
			"type: rag-research\nphase: EXECUTE\n\nwork\n",
		);
		// Simulate the worker's deliverable write: the doc lands in the key's
		// rag/ dir (the layout VC-018 names), not in the task dir.
		const ragDir = path.join(project, ".agenticdoc", "key-a", "rag");
		fs.mkdirSync(ragDir, { recursive: true });
		fs.writeFileSync(path.join(ragDir, "A-symbol-lookup.md"), RESEARCH_DOC, "utf8");

		emit("agent_settled");

		// Runtime face: the worker's reply has no citation of its own, yet the
		// required research role is satisfied by the key doc -> no marker.
		expect(read(taskDir, "trace.log")).not.toContain("rag-required-missing");
		expect(read(taskDir, "output.md")).not.toContain("RAG 未生效");

		const report = validateResearchDoc(path.join(project, ".agenticdoc", "key-a"));
		expect(report.ok).toBe(true);
		expect(report.headings).toHaveLength(6);
		verify(
			`[VERIFY] VC-106: runtime_doc_found=${report.docPath !== null} sections=${report.headings.length} ` +
				`verdict=${report.ok ? "ok" : "fail"}`,
		);
	});

	it("emits the missing marker when the key dir has no compliant doc", async () => {
		const project = makeProject(TARGET_RESEARCH_REQUIRED);
		const { taskDir, emit } = await startWorker(
			project,
			"key-a",
			"w-research",
			"type: rag-research\nphase: EXECUTE\n\nwork\n",
		);
		emit("agent_settled");
		expect(read(taskDir, "trace.log")).toContain("rag-required-missing role=research phase=EXECUTE server=A");
		verify("[VERIFY] VC-106: missing_doc_emits_marker=true");
	});
});

// ── VC-105: unregistered `type:` falls back to the coding role (T-16/D-105) ──

describe("VC-105 unregistered type fallback", () => {
	it("judges `roles.coding.require` for `type: foobar`, like the Python audit", async () => {
		const project = makeProject(TARGET_CODING_REQUIRED);
		// The literal `type:` value is deliberately the same one
		// test_rag_audit.py::test_vc105_unregistered_type_falls_back_to_coding_role uses.
		// `ts_phase=unknown` in the marker is what an absent `phase:` header renders as.
		const { taskDir, emit } = await startWorker(project, "key-a", "w-unknown", "type: foobar\n\nwork\n");

		emit("agent_settled");
		const trace = read(taskDir, "trace.log");
		expect(trace).toContain("rag-required-missing role=coding phase=unknown server=A");

		// Evidence fields are parsed back out of the runtime trace line (AC-108),
		// so a role-fallback regression changes them instead of printing labels.
		const marker = /rag-required-missing role=(\S+) phase=(\S+) server=(\S+)/.exec(trace);
		expect(marker).not.toBeNull();
		const [, tsRole, tsPhase, tsServer] = marker as RegExpExecArray;
		expect(tsRole).toBe("coding");
		verify(
			`[VERIFY] VC-105: ts_role=${tsRole} ts_phase=${tsPhase} ts_required=true type_literal=foobar server=${tsServer}`,
		);
	});
});

// ── VC-014: required-but-unused emission ────────────────────────────────────

describe("VC-014 required-but-unused worker emission", () => {
	it("emits the trace line + output marker once, and is idempotent", async () => {
		const project = makeProject(TARGET_CODING_REQUIRED);
		const { taskDir, emit } = await startWorker(
			project,
			"key-a",
			"w-required",
			"type: coding\nphase: DESIGN\n\nwork\n",
		);

		emit("agent_settled");
		const trace = read(taskDir, "trace.log");
		expect(trace).toContain("rag-required-missing role=coding phase=DESIGN server=A");
		const output = read(taskDir, "output.md");
		expect(output).toContain("RAG 未生效：required but unused");
		expect(output).toContain("## RAG");

		// Re-settle: output.md is rewritten then re-marked exactly once; the
		// trace line is deduped.
		emit("agent_settled");
		expect(occurrences(read(taskDir, "trace.log"), "rag-required-missing")).toBe(1);
		expect(occurrences(read(taskDir, "output.md"), "RAG 未生效")).toBe(1);

		verify("[VERIFY] VC-014: required_unused_emitted=true output_marked=true idempotent=true");
	});

	it("does not emit when the worker produced a verifiable citation", async () => {
		const project = makeProject(TARGET_CODING_REQUIRED);
		const { taskDir, emit } = await startWorker(project, "key-a", "w-cited", "type: coding\nphase: DESIGN\n\nwork\n");

		emit("agent_end", {
			messages: [
				{ role: "assistant", content: [{ type: "text", text: "`A:code:engine::Runtime/X.cpp:12` exists=true" }] },
			],
		});
		emit("agent_settled");

		expect(read(taskDir, "trace.log")).not.toContain("rag-required-missing");
		expect(read(taskDir, "output.md")).not.toContain("RAG 未生效");
		verify("[VERIFY] VC-014: citation_present_emitted=false");
	});

	it("writes nothing when the role/phase is not required", async () => {
		const project = makeProject("rag:\n  enabled: [A]\n  default_server: A\n");
		const { taskDir, emit } = await startWorker(
			project,
			"key-a",
			"w-optional",
			"type: coding\nphase: DESIGN\n\nwork\n",
		);

		emit("agent_settled");
		expect(read(taskDir, "trace.log")).not.toContain("rag-required-missing");
		expect(read(taskDir, "output.md")).not.toContain("RAG 未生效");
		verify("[VERIFY] VC-014: not_required_writes=0");
	});

	it("writes nothing when RAG is disabled (structural zero impact)", async () => {
		const project = makeProject("rag:\n  enabled: []\n");
		const { taskDir, emit } = await startWorker(
			project,
			"key-a",
			"w-disabled",
			"type: coding\nphase: DESIGN\n\nwork\n",
		);

		emit("agent_settled");
		expect(read(taskDir, "trace.log")).not.toContain("rag-required-missing");
		expect(read(taskDir, "output.md")).not.toContain("RAG 未生效");
		verify("[VERIFY] VC-014: rag_disabled_writes=0");
	});
});

// ── VC-014: the judgement function in isolation ─────────────────────────────

describe("emitRagRequiredMissing judgement", () => {
	function check(input: { project: string; taskDir: string; phase: string; outputText: string }): string | null {
		return emitRagRequiredMissing({
			config: loadRagConfig(input.project),
			taskType: "coding",
			phase: input.phase,
			outputText: input.outputText,
			keyDir: path.join(input.project, ".agenticdoc", "key-a"),
			taskDir: input.taskDir,
		});
	}

	it("returns null with zero writes when not required", () => {
		const project = makeProject("rag:\n  enabled: [A]\n  default_server: A\n");
		const taskDir = fs.mkdtempSync(path.join(os.tmpdir(), "rag-req-unit-"));
		tempDirs.push(taskDir);
		expect(check({ project, taskDir, phase: "DESIGN", outputText: "" })).toBeNull();
		expect(fs.existsSync(path.join(taskDir, "trace.log"))).toBe(false);
		expect(fs.existsSync(path.join(taskDir, "output.md"))).toBe(false);
	});

	it("emits once and dedupes on repeated calls", () => {
		const project = makeProject(TARGET_CODING_REQUIRED);
		const taskDir = fs.mkdtempSync(path.join(os.tmpdir(), "rag-req-unit-"));
		tempDirs.push(taskDir);
		const first = check({ project, taskDir, phase: "DESIGN", outputText: "" });
		expect(first).toBe("rag-required-missing role=coding phase=DESIGN server=A");
		const second = check({ project, taskDir, phase: "DESIGN", outputText: "" });
		expect(second).toBe(first);
		expect(occurrences(read(taskDir, "trace.log"), "rag-required-missing")).toBe(1);
	});

	it("returns null when a citation is present", () => {
		const project = makeProject(TARGET_CODING_REQUIRED);
		const taskDir = fs.mkdtempSync(path.join(os.tmpdir(), "rag-req-unit-"));
		tempDirs.push(taskDir);
		expect(check({ project, taskDir, phase: "DESIGN", outputText: "`A:code:engine::X.cpp:1`" })).toBeNull();
		expect(read(taskDir, "trace.log")).not.toContain("rag-required-missing");
	});
});
