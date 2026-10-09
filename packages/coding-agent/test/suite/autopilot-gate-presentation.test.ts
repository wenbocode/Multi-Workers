/**
 * Gate presentation contract — three machine-checkable layers (T-09,
 * mw-autopilot-slot-capacity, AC-007/012/021/026; VC-008/014/027/028/037/038).
 *
 * Layer A (`monitor.ts`): one line per pending gate, every line <= 110
 * columns, `created_at` age visible, evidence-drift marker `DRIFT(` when an
 * evidence mtime is newer than the gate's created_at.
 * Layer B (`console.ts renderGateCards`): header + EXACTLY 13 lines per pending
 * gate, fixed order, every line <= 110 columns => total `1 + 13*N`.
 * Field mirror: `GATE_FRONTMATTER_FIELDS` equals Python
 * `autopilot.gates.FRONTMATTER_FIELDS` item-for-item and in order (40 names).
 * Anti-LLM: the render function bodies never reference dispatch/model/provider,
 * and every absent field renders the one sentinel `unknown (no field)`.
 *
 * Pure file fixtures + a real Python subprocess for the mirror. No provider
 * APIs, keys, or network.
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { renderGateCards } from "../../src/extensions/agent-team-loop/autopilot/console.ts";
import { readMonitorState, renderMonitorLines } from "../../src/extensions/agent-team-loop/autopilot/monitor.ts";
import {
	GATE_FRONTMATTER_FIELDS,
	gatesDir,
	listGates,
	MISSING_FIELD_SENTINEL,
	parseGateFile,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import { resolveRagPython } from "../../src/extensions/agent-team-loop/rag/cli-bridge.ts";

/** 2026-09-26T08:33:00Z — the design snapshot instant. */
const NOW_MS = Date.parse("2026-09-26T08:33:00Z");
const GATE_CREATED = "2026-09-26T04:37:27+00:00";
const OLD_EVIDENCE_MS = Date.parse("2026-09-11T20:25:02Z");
const NEW_EVIDENCE_MS = Date.parse("2026-09-27T01:00:00Z");
const LINE_MAX = 110;
const HEDGE = /(大概|可能|推测|也许|似乎|\bprobably\b|\bmaybe\b|\bperhaps\b|\blikely\b)/i;

function mkdtemp(prefix: string): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

interface GateSpec {
	id: string;
	kind: string;
	status?: string;
	stage?: number | null;
	key?: string | null;
	createdAt?: string;
	question?: string;
	contextRefs?: string[];
	reasonCode?: string;
	evidenceRefs?: string[];
	/** Render evidence_refs as the v2 single-line JSON substring instead of a
	 * block list. */
	evidenceRefsJson?: boolean;
	loop?: string;
	usedRounds?: number;
	roundLimit?: number;
	creditsUsed?: number;
	goalSha256?: string;
	proposalSha256?: string;
	constraintsJson?: string;
	openItemsJson?: string;
	answerSource?: string;
	expiresAt?: string;
	defaultAction?: string;
	answeredAt?: string;
	answeredBy?: string;
	note?: string;
}

/** A gate file in the Python renderer's shape (any field order is legal). */
function writeGate(root: string, spec: GateSpec): string {
	const dir = gatesDir(root);
	fs.mkdirSync(dir, { recursive: true });
	const lines: string[] = ["---"];
	lines.push(`id: ${spec.id}`);
	lines.push(`kind: ${spec.kind}`);
	lines.push(`stage: ${spec.stage === null || spec.stage === undefined ? "" : spec.stage}`);
	lines.push(`key: ${spec.key === null || spec.key === undefined ? "" : spec.key}`);
	lines.push(`created_at: ${spec.createdAt ?? GATE_CREATED}`);
	lines.push("created_by: conductor");
	lines.push(`question: '${(spec.question ?? "proceed?").replaceAll("'", "''")}'`);
	lines.push("context_refs:");
	for (const ref of spec.contextRefs ?? [".agenticdoc/_autopilot/_roadmap.md"]) lines.push(`  - ${ref}`);
	if (spec.reasonCode !== undefined) lines.push(`reason_code: ${spec.reasonCode}`);
	if (spec.evidenceRefs !== undefined) {
		if (spec.evidenceRefsJson === true) {
			lines.push(`evidence_refs: '${JSON.stringify(spec.evidenceRefs)}'`);
		} else {
			lines.push("evidence_refs:");
			for (const ref of spec.evidenceRefs) lines.push(`  - ${ref}`);
		}
	}
	if (spec.loop !== undefined) lines.push(`loop: ${spec.loop}`);
	if (spec.usedRounds !== undefined) lines.push(`used_rounds: ${spec.usedRounds}`);
	if (spec.roundLimit !== undefined) lines.push(`round_limit: ${spec.roundLimit}`);
	if (spec.creditsUsed !== undefined) lines.push(`credits_used: ${spec.creditsUsed}`);
	if (spec.goalSha256 !== undefined) lines.push(`goal_sha256: ${spec.goalSha256}`);
	if (spec.proposalSha256 !== undefined) lines.push(`proposal_sha256: ${spec.proposalSha256}`);
	if (spec.constraintsJson !== undefined) lines.push(`constraints: '${spec.constraintsJson}'`);
	if (spec.openItemsJson !== undefined) lines.push(`open_items: '${spec.openItemsJson}'`);
	if (spec.answerSource !== undefined) lines.push(`answer_source: ${spec.answerSource}`);
	if (spec.expiresAt !== undefined) lines.push(`expires_at: ${spec.expiresAt}`);
	if (spec.defaultAction !== undefined) lines.push(`default_action: ${spec.defaultAction}`);
	lines.push(`status: ${spec.status ?? "pending"}`);
	lines.push(`answered_at: ${spec.answeredAt ?? ""}`);
	lines.push(`answered_by: ${spec.answeredBy ?? ""}`);
	lines.push(`note: ${spec.note === undefined ? "" : `'${spec.note}'`}`);
	lines.push("---", "", `# Gate ${spec.id}`, "");
	const file = path.join(dir, `${spec.id}.md`);
	fs.writeFileSync(file, `${lines.join("\n")}\n`, "utf8");
	return file;
}

/** Write one evidence file under `<root>/.agenticdoc/<rel>` with a fixed mtime. */
function writeEvidence(root: string, rel: string, body: string, mtimeMs: number): string {
	const file = path.join(root, ".agenticdoc", rel);
	fs.mkdirSync(path.dirname(file), { recursive: true });
	fs.writeFileSync(file, body, "utf8");
	const stamp = new Date(mtimeMs);
	fs.utimesSync(file, stamp, stamp);
	return file;
}

function writeRoadmap(root: string): void {
	const file = path.join(root, ".agenticdoc", "_autopilot", "_roadmap.md");
	fs.mkdirSync(path.dirname(file), { recursive: true });
	fs.writeFileSync(
		file,
		[
			"# Roadmap",
			"> generated_at: 2026-09-26T00:00:00+00:00",
			"> goal_mtime: 1700000000000",
			"",
			"## Stage 1: Foundation",
			"> goal: ship the local closed loop",
			"> status: running",
			"> key-status: k1=done, k2=running",
			"### Keys",
			"| key | role | depends_on |",
			"|-----|------|-----------|",
			"| k1 | build | - |",
			"| k2 | verify | k1 |",
			"",
		].join("\n"),
		"utf8",
	);
}

function writeConfig(root: string, autoGateMode: string): void {
	const file = path.join(root, ".agenticdoc", "_autopilot", "config.json");
	fs.mkdirSync(path.dirname(file), { recursive: true });
	fs.writeFileSync(
		file,
		`${JSON.stringify({ enabled: true, paused: false, auto_gate_mode: autoGateMode }, null, 2)}\n`,
		"utf8",
	);
}

function cardLinesFor(root: string): string[] {
	return renderGateCards(listGates(root).gates, root, NOW_MS);
}

function gateLinesOf(panel: string[]): string[] {
	const first = panel.findIndex((line) => line.startsWith("gates:"));
	if (first < 0) return [];
	const out: string[] = [];
	for (let i = first; i < panel.length; i++) {
		const line = panel[i];
		if (i > first && !line.startsWith("  · ")) break;
		out.push(line);
	}
	return out;
}

/** Brace-matched body of `function <name>(` (the anti-LLM source assertion). */
function functionBody(source: string, name: string): string {
	const marker = `function ${name}(`;
	const at = source.indexOf(marker);
	expect(at, `function ${name} not found`).toBeGreaterThanOrEqual(0);
	const open = source.indexOf("{", at);
	let depth = 0;
	for (let i = open; i < source.length; i++) {
		const ch = source[i];
		if (ch === "{") depth += 1;
		else if (ch === "}") {
			depth -= 1;
			if (depth === 0) return source.slice(open, i + 1);
		}
	}
	throw new Error(`unbalanced body for ${name}`);
}

const AUTOPILOT_SRC = fileURLToPath(new URL("../../src/extensions/agent-team-loop/autopilot/", import.meta.url));

// ── Field mirror (VC-D6-06) ──────────────────────────────────────────────────

describe("gate frontmatter mirror (VC-D6-06)", () => {
	it("mirrors gates.FRONTMATTER_FIELDS item-for-item in the same order (40 names)", () => {
		const multiWorkers = fileURLToPath(new URL("../../../multi-workers/", import.meta.url));
		const script = [
			"import json, sys",
			"sys.path.insert(0, sys.argv[1])",
			"from autopilot import gates",
			"print('GATE_FIELDS_BEGIN')",
			"print(json.dumps(list(gates.FRONTMATTER_FIELDS)))",
			"print('GATE_FIELDS_END')",
		].join("\n");
		const run = spawnSync(resolveRagPython(), ["-c", script, multiWorkers], { encoding: "utf8" });
		expect(run.status, run.stderr).toBe(0);
		const stdout = run.stdout.replace(/\r\n/g, "\n");
		const match = /GATE_FIELDS_BEGIN\n(.*)\nGATE_FIELDS_END/s.exec(stdout);
		expect(match).not.toBeNull();
		const pyFields = JSON.parse(match?.[1] ?? "[]") as string[];
		expect(pyFields).toEqual([...GATE_FRONTMATTER_FIELDS]);
		expect(pyFields).toHaveLength(40);
		// 12 frozen base names first, then the additive v2 set.
		expect(pyFields.slice(0, 12)).toEqual([
			"id",
			"kind",
			"stage",
			"key",
			"created_at",
			"created_by",
			"question",
			"context_refs",
			"status",
			"answered_at",
			"answered_by",
			"note",
		]);
		expect(pyFields).toContain("gate_schema");
		expect(pyFields).toContain("consumed_at");
		expect(pyFields).toContain("consumed_seq");
	});

	it("parses a v2 gate with both evidence_refs encodings and rejects unknown fields", () => {
		const root = mkdtemp("ap-gate-present-parse-");
		try {
			const block = writeGate(root, {
				id: "gate-0001",
				kind: "stage-close",
				stage: 1,
				evidenceRefs: ["gate-dossier:_autopilot/stages/stage-1-close.md"],
				reasonCode: "stage:all-keys-terminal",
			});
			const parsedBlock = parseGateFile(fs.readFileSync(block, "utf8"), block);
			expect(parsedBlock.evidenceRefs).toEqual(["gate-dossier:_autopilot/stages/stage-1-close.md"]);
			expect(parsedBlock.reasonCode).toBe("stage:all-keys-terminal");
			expect(parsedBlock.gateSchema).toBe(1);

			const json = writeGate(root, {
				id: "gate-0002",
				kind: "stage-close",
				stage: 1,
				evidenceRefs: ["l3-verdict:k1/l3-verdict.txt", "worker-output:k1/workers/a/out.md"],
				evidenceRefsJson: true,
				openItemsJson: '[{"kind":"verdict-none","key":"k1"}]',
			});
			const parsedJson = parseGateFile(fs.readFileSync(json, "utf8"), json);
			expect(parsedJson.evidenceRefs).toEqual(["l3-verdict:k1/l3-verdict.txt", "worker-output:k1/workers/a/out.md"]);
			expect(Array.isArray(parsedJson.openItems)).toBe(true);

			const bogus = path.join(gatesDir(root), "gate-0003.md");
			fs.writeFileSync(
				bogus,
				"---\nid: gate-0003\nkind: stalled\nstage: 1\ncreated_at: 2026-09-26T04:37:27+00:00\ncreated_by: conductor\nquestion: 'q'\nstatus: pending\nbogus_field: x\n---\n",
				"utf8",
			);
			expect(() => parseGateFile(fs.readFileSync(bogus, "utf8"), bogus)).toThrow(/bogus_field/);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── Layer B: 1 + 13*N card contract ──────────────────────────────────────────

describe("layer B gate card contract (AC-026)", () => {
	it("renders exactly 1 + 13*N lines: N=1 -> 14, N=3 -> 40", () => {
		const root1 = mkdtemp("ap-gate-present-b1-");
		const root3 = mkdtemp("ap-gate-present-b3-");
		try {
			writeGate(root1, { id: "gate-0001", kind: "stage-close", stage: 1, key: null });
			const cards1 = cardLinesFor(root1);
			expect(cards1).toHaveLength(14); // header + 13
			expect(cards1[0]).toBe("1 pending gate(s):");

			for (let i = 1; i <= 3; i++) {
				writeGate(root3, { id: `gate-000${i}`, kind: "stalled", stage: 1, key: `k${i}` });
			}
			const cards3 = cardLinesFor(root3);
			expect(cards3).toHaveLength(40); // header + 13*3
			expect(cards3[0]).toBe("3 pending gate(s):");
		} finally {
			fs.rmSync(root1, { recursive: true, force: true });
			fs.rmSync(root3, { recursive: true, force: true });
		}
	});

	it("keeps every line <= 110 columns even with a 400-char question and long v2 values", () => {
		const root = mkdtemp("ap-gate-present-long-");
		try {
			writeGate(root, {
				id: "gate-0001",
				kind: "stalled",
				stage: 1,
				key: "feature-with-a-very-long-key-name-for-truncation",
				question: "Q".repeat(400),
				reasonCode: "advance:interface-drift",
				evidenceRefs: [`worker-output:${"deep/".repeat(20)}output.md`],
				constraintsJson: JSON.stringify(["c".repeat(120)]),
				openItemsJson: JSON.stringify([{ kind: "below", key: "k1", item: "i".repeat(80) }]),
				loop: "l2:k1:spec-to-design",
				usedRounds: 2,
				roundLimit: 2,
				creditsUsed: 0,
			});
			const cards = cardLinesFor(root);
			expect(cards).toHaveLength(14);
			for (const line of cards) expect(line.length, line).toBeLessThanOrEqual(LINE_MAX);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("renders the one sentinel literal for absent v2 fields and no hedge prose", () => {
		const root = mkdtemp("ap-gate-present-missing-");
		try {
			// Base 12 only: every v2 field is absent.
			writeGate(root, { id: "gate-0001", kind: "stage-close", stage: 1, key: null });
			const cards = cardLinesFor(root);
			expect(cards).toHaveLength(14);
			const text = cards.join("\n");
			expect(text).toContain(MISSING_FIELD_SENTINEL);
			// L9/L10/L12/L13 all carry the sentinel for the absent fields.
			expect(cards[9]).toContain(`default: ${MISSING_FIELD_SENTINEL}`);
			expect(cards[10]).toContain(MISSING_FIELD_SENTINEL);
			expect(cards[12]).toBe(`open-items: ${MISSING_FIELD_SENTINEL}`);
			expect(cards[13]).toContain(`expected: ${MISSING_FIELD_SENTINEL}`);
			for (const line of cards) expect(HEDGE.test(line), line).toBe(false);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("reports missing fields only for pending gates, never for answered history", () => {
		const root = mkdtemp("ap-gate-present-answered-");
		try {
			writeGate(root, {
				id: "gate-0001",
				kind: "stalled",
				stage: 1,
				key: "k1",
				status: "approved",
				answeredAt: "2026-09-26T05:00:00+00:00",
				answeredBy: "host:1",
			});
			const cards = cardLinesFor(root);
			expect(cards).toEqual(["no pending gates (1 total)"]);
			expect(cards.join("\n")).not.toContain(MISSING_FIELD_SENTINEL);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("L6/L8/L9/L12/L13 carry evidence, replay history, default/ttl/auto, open items and answer source", () => {
		const root = mkdtemp("ap-gate-present-fields-");
		try {
			writeRoadmap(root);
			writeConfig(root, "shadow");
			writeEvidence(root, "_autopilot/stages/stage-1-close.md", "## Keys\n\n- k1\n", OLD_EVIDENCE_MS);
			// Answered same-scope history (stage 1, keyless) — the replay shape.
			writeGate(root, {
				id: "gate-0001",
				kind: "stage-confirm",
				stage: 1,
				key: null,
				status: "approved",
				answeredAt: "2026-09-11T06:20:38+00:00",
				note: "stage 1 approved",
			});
			writeGate(root, {
				id: "gate-0005",
				kind: "stage-close",
				stage: 1,
				key: null,
				status: "approved",
				answeredAt: "2026-09-17T12:42:00+00:00",
				note: "closed after local loop",
			});
			writeGate(root, {
				id: "gate-0008",
				kind: "stage-close",
				stage: 1,
				key: null,
				reasonCode: "stage:all-keys-terminal",
				contextRefs: ["stage-1", "stage 1 all keys terminal"],
				evidenceRefs: ["gate-dossier:_autopilot/stages/stage-1-close.md"],
				openItemsJson: '[{"kind":"verdict-none","key":"k1"}]',
				constraintsJson: '["do not relax scope"]',
				expiresAt: "2026-09-27T04:37:27+00:00",
				defaultAction: "halt-and-report",
				answerSource: "human",
			});
			const cards = cardLinesFor(root);
			expect(cards).toHaveLength(14);
			expect(cards[6]).toContain("_autopilot/stages/stage-1-close.md");
			expect(cards[6]).toContain("sections=[Keys]");
			expect(cards[8]).toContain("gate-0001");
			expect(cards[8]).toContain("gate-0005");
			expect(cards[9]).toBe(`default: halt-and-report | ttl: 2026-09-27T04:37:27+00:00 | auto=shadow`);
			expect(cards[12]).toContain('"kind":"verdict-none"');
			expect(cards[13]).toContain("/autopilot gate gate-0008 approve|reject");
			expect(cards[13]).toContain("expected: human");
			for (const line of cards) expect(line.length, line).toBeLessThanOrEqual(LINE_MAX);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("marks DRIFT( when an evidence mtime is newer than created_at, and omits it otherwise", () => {
		const fresh = mkdtemp("ap-gate-present-drift-");
		const clean = mkdtemp("ap-gate-present-nodrift-");
		try {
			writeEvidence(fresh, "_autopilot/stages/stage-1-close.md", "## Keys\n", NEW_EVIDENCE_MS);
			writeGate(fresh, {
				id: "gate-0001",
				kind: "stage-close",
				stage: 1,
				evidenceRefs: ["gate-dossier:_autopilot/stages/stage-1-close.md"],
			});
			const freshCards = cardLinesFor(fresh);
			expect(freshCards[6]).toContain("DRIFT(");

			writeEvidence(clean, "_autopilot/stages/stage-1-close.md", "## Keys\n", OLD_EVIDENCE_MS);
			writeGate(clean, {
				id: "gate-0001",
				kind: "stage-close",
				stage: 1,
				evidenceRefs: ["gate-dossier:_autopilot/stages/stage-1-close.md"],
			});
			const cleanCards = cardLinesFor(clean);
			expect(cleanCards.join("\n")).not.toContain("DRIFT(");
		} finally {
			fs.rmSync(fresh, { recursive: true, force: true });
			fs.rmSync(clean, { recursive: true, force: true });
		}
	});

	it("shows auto=off when the kill switch is absent and auto=live when set to live", () => {
		const root = mkdtemp("ap-gate-present-auto-");
		try {
			writeGate(root, { id: "gate-0001", kind: "stalled", stage: 1, key: "k1" });
			expect(cardLinesFor(root)[9]).toContain("auto=off");
			writeConfig(root, "live");
			expect(cardLinesFor(root)[9]).toContain("auto=live");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── Layer A: monitor panel ───────────────────────────────────────────────────

describe("layer A monitor gate lines (AC-012)", () => {
	it("renders one line per pending gate with age and DRIFT, all <= 110 columns", () => {
		const root = mkdtemp("ap-gate-present-mon-");
		try {
			writeConfig(root, "shadow");
			writeEvidence(root, "_autopilot/stages/stage-1-close.md", "## Keys\n", NEW_EVIDENCE_MS);
			writeGate(root, {
				id: "gate-0008",
				kind: "stage-close",
				stage: 1,
				reasonCode: "stage:all-keys-terminal",
				evidenceRefs: ["gate-dossier:_autopilot/stages/stage-1-close.md"],
			});
			writeGate(root, { id: "gate-0009", kind: "stalled", stage: 1, key: "k1" });

			const panel = renderMonitorLines(readMonitorState(root, NOW_MS));
			const gateLines = gateLinesOf(panel);
			expect(gateLines).toHaveLength(2); // one line per gate
			expect(gateLines[0]).toContain("gates: 2 pending - gate-0008 (stage-close)");
			expect(gateLines[0]).toContain("DRIFT(");
			expect(gateLines[1].startsWith("  · ")).toBe(true);
			expect(gateLines[1]).toContain("age="); // age is visible on the clean gate
			expect(gateLines.join("\n")).toContain("-> /autopilot gate gate-0008 approve|reject");
			expect(panel.join("\n")).toContain("auto=shadow");
			for (const line of panel) expect(line.length, line).toBeLessThanOrEqual(LINE_MAX);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("omits DRIFT when the evidence is older than created_at", () => {
		const root = mkdtemp("ap-gate-present-monclean-");
		try {
			writeEvidence(root, "_autopilot/stages/stage-1-close.md", "## Keys\n", OLD_EVIDENCE_MS);
			writeGate(root, {
				id: "gate-0008",
				kind: "stage-close",
				stage: 1,
				evidenceRefs: ["gate-dossier:_autopilot/stages/stage-1-close.md"],
			});
			const panel = renderMonitorLines(readMonitorState(root, NOW_MS));
			expect(panel.join("\n")).toContain("gate-0008");
			expect(panel.join("\n")).not.toContain("DRIFT(");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── Anti-LLM source assertion (VC-D6-05) ─────────────────────────────────────

describe("render functions never reference dispatch/model/provider (VC-D6-05)", () => {
	it("keeps monitor renderMonitorLines, console cmdGates and renderGateCards free of model calls", () => {
		for (const [file, names] of [
			[path.join(AUTOPILOT_SRC, "monitor.ts"), ["renderMonitorLines"]],
			[path.join(AUTOPILOT_SRC, "console.ts"), ["cmdGates", "renderGateCards"]],
		] as Array<[string, string[]]>) {
			const source = fs.readFileSync(file, "utf8");
			for (const name of names) {
				const body = functionBody(source, name);
				for (const line of body.split("\n")) {
					expect(/\b(dispatch|model|provider)\b/.test(line), `${path.basename(file)} ${name}: ${line}`).toBe(
						false,
					);
				}
			}
		}
	});
});
