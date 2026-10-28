/**
 * T-14 / AC-007 — `blocker_class` TS mirror: out-of-order scalar registration,
 * closed set, and the fail-closed fold (null/absent -> judgment).
 *
 * Covers the TS half of the five fail-closed forms (T-A..T-E) plus the
 * strict-parser registration counterfactual and the derivation-layer fold
 * direction. Pure file fixtures; no provider APIs, keys, or network.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import {
	BLOCKER_CLASSES,
	blockerClassOf,
	DEFAULT_CONFIG,
	deriveStatusModel,
	GATE_FRONTMATTER_FIELDS,
	GATE_JSON_LIST_FIELDS,
	GATE_SCALAR_EXTENSION_FIELDS,
	gatesDir,
	listGates,
	parseGateFile,
	renderStatusText,
	saveConfig,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";

const NOW_MS = Date.parse("2026-09-10T08:00:00Z");
const CREATED = "2026-09-10T07:00:00+00:00";

function mkdtemp(prefix: string): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

/** One gate file with an optional raw `blocker_class:` line appended verbatim
 * (so malformed values can be exercised). */
function writeGate(root: string, id: string, extra: string[] = []): string {
	const dir = gatesDir(root);
	fs.mkdirSync(dir, { recursive: true });
	const lines = [
		"---",
		`id: ${id}`,
		"kind: stalled",
		"stage: 2",
		"key: k3",
		`created_at: ${CREATED}`,
		"created_by: conductor",
		"question: 'Is this gate valid?'",
		"context_refs: []",
		"status: pending",
		"answered_at:",
		"answered_by:",
		"note:",
		...extra,
		"---",
		"",
		"body",
		"",
	];
	const file = path.join(dir, `${id}.md`);
	fs.writeFileSync(file, lines.join("\n"), "utf8");
	return file;
}

function parse(root: string, id: string, extra: string[]) {
	const file = writeGate(root, id, extra);
	return parseGateFile(fs.readFileSync(file, "utf8"), file);
}

describe("T-14 blocker_class registration (AC-007)", () => {
	it("is registered as an out-of-order scalar, closed set, frozen order untouched", () => {
		expect(GATE_SCALAR_EXTENSION_FIELDS.has("blocker_class")).toBe(true);
		expect(GATE_JSON_LIST_FIELDS.has("blocker_class")).toBe(false);
		expect(GATE_FRONTMATTER_FIELDS).not.toContain("blocker_class");
		expect(GATE_FRONTMATTER_FIELDS).toHaveLength(40);
		expect(GATE_FRONTMATTER_FIELDS.length + GATE_SCALAR_EXTENSION_FIELDS.size).toBe(41);
		expect([...BLOCKER_CLASSES].sort()).toEqual(["judgment", "paperwork"]);
	});

	it("parses valid values and keeps an absent field null (never folded in the parser)", () => {
		const root = mkdtemp("t14-ts-valid-");
		try {
			expect(parse(root, "gate-0001", ["blocker_class: paperwork"]).blockerClass).toBe("paperwork");
			expect(parse(root, "gate-0002", ["blocker_class: judgment"]).blockerClass).toBe("judgment");
			expect(parse(root, "gate-0003", []).blockerClass).toBeNull();
			expect(parse(root, "gate-0004", ["blocker_class:"]).blockerClass).toBeNull();
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("T-A: malformed value is rejected, never silently healthy", () => {
		const root = mkdtemp("t14-ts-ta-");
		try {
			for (const raw of ["'  '", "paper work", "paperwork".repeat(40), "'paper\\nwork'"]) {
				const file = writeGate(root, "gate-0001", [`blocker_class: ${raw}`]);
				expect(() => parseGateFile(fs.readFileSync(file, "utf8"), file)).toThrow(/blocker_class/);
			}
			// A bare empty value is `null` (unclassified) and folds to judgment.
			const quiet = parse(root, "gate-0002", ["blocker_class:"]);
			expect(quiet.blockerClass).toBeNull();
			expect(blockerClassOf(quiet)).toBe("judgment");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("T-B: an out-of-enum value is fail-closed and names the legal set", () => {
		const root = mkdtemp("t14-ts-tb-");
		try {
			const file = writeGate(root, "gate-0001", ["blocker_class: bogus"]);
			expect(() => parseGateFile(fs.readFileSync(file, "utf8"), file)).toThrow(
				/unknown blocker_class 'bogus'.*judgment, paperwork/,
			);
			const cased = writeGate(root, "gate-0002", ["blocker_class: 'Paperwork'"]);
			expect(() => parseGateFile(fs.readFileSync(cased, "utf8"), cased)).toThrow(/blocker_class/);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("T-C: a list-typed value fails explicitly instead of being ignored", () => {
		const root = mkdtemp("t14-ts-tc-");
		try {
			for (const raw of ["[paperwork]", "[paperwork, judgment]", "'[\"paperwork\"]'"]) {
				const file = writeGate(root, "gate-0001", [`blocker_class: ${raw}`]);
				expect(() => parseGateFile(fs.readFileSync(file, "utf8"), file)).toThrow(/blocker_class/);
			}
			const block = writeGate(root, "gate-0002", ["blocker_class:", "  - paperwork"]);
			expect(() => parseGateFile(fs.readFileSync(block, "utf8"), block)).toThrow();
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("T-D: a legacy v1 gate without the field stays readable and folds to judgment", () => {
		const root = mkdtemp("t14-ts-td-");
		try {
			const legacy = writeGate(root, "gate-0001", []);
			const record = parseGateFile(fs.readFileSync(legacy, "utf8"), legacy); // must not throw
			expect(record.blockerClass).toBeNull();
			expect(blockerClassOf(record)).toBe("judgment");
			expect(blockerClassOf({ blockerClass: null })).toBe("judgment");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("T-E: the fold is one-way — only an explicit paperwork is paperwork", () => {
		expect(blockerClassOf({ blockerClass: "paperwork" })).toBe("paperwork");
		expect(blockerClassOf({ blockerClass: "judgment" })).toBe("judgment");
		expect(blockerClassOf({ blockerClass: null })).toBe("judgment");
		expect(blockerClassOf({ blockerClass: "bogus" })).toBe("judgment");
	});

	it("derivation layer folds per gate (none -> judgment) without touching GateView", () => {
		const root = mkdtemp("t14-ts-derive-");
		try {
			saveConfig(root, { ...DEFAULT_CONFIG, enabled: true });
			writeGate(root, "gate-0001", ["blocker_class: paperwork"]);
			writeGate(root, "gate-0002", []);
			const result = deriveStatusModel(root, NOW_MS);
			expect(result.ok).toBe(true);
			if (!result.ok) return;
			expect(result.model.gateBlockerClasses).toEqual({
				"gate-0001": "paperwork",
				"gate-0002": "judgment",
			});
			// GateView shape is locked elsewhere; the fold must not leak into it.
			expect(Object.keys(result.model.status.gates[0]).sort()).toEqual(["ageMs", "id", "kind", "status"]);
			const text = renderStatusText(result.model);
			expect(text).toContain("gate-0001 stalled pending");
			expect(text).toContain("blocker=paperwork");
			expect(text).toContain("blocker=judgment");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("counterfactual: removing the registration fails the whole queue closed", () => {
		const root = mkdtemp("t14-ts-counterfactual-");
		try {
			const carrier = writeGate(root, "gate-0001", ["blocker_class: paperwork"]);
			const text = fs.readFileSync(carrier, "utf8");
			expect(parseGateFile(text, carrier).blockerClass).toBe("paperwork");
			writeGate(root, "gate-0002", []); // clean gate in the same queue
			GATE_SCALAR_EXTENSION_FIELDS.delete("blocker_class");
			try {
				expect(() => parseGateFile(text, carrier)).toThrow(/unknown frontmatter field 'blocker_class'/);
				// TS `listGates` degrades per file: the carrier is excluded and the
				// error is surfaced (the clean gate still reads).
				const scan = listGates(root);
				expect(scan.gates.map((g) => g.id)).toEqual(["gate-0002"]);
				expect(scan.errors.join("\n")).toContain("blocker_class");
			} finally {
				GATE_SCALAR_EXTENSION_FIELDS.add("blocker_class");
			}
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});
