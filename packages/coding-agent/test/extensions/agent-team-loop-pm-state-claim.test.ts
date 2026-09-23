/**
 * Tests for the pm-state.md Claim-Id single-line sync writer
 * (mw-worker-visibility-gate T-2/T-6, AC-010/AC-011, design D-107/D-111,
 * VC-010/VC-011).
 *
 * T-6 (design D-111): a pm-state.md that lacks the '- Claim-Id:' line but
 * has a '- Key:' line gets the claim line INSERTED directly after '- Key:'
 * (the same anchor update_index.py uses) instead of a refusal — every key
 * created via switch_key → advance_phase.py has exactly that shape, so the
 * old refusal made the "index row == mirror" equality unreachable. Only a
 * file with NEITHER interface line fails closed.
 *
 * Measured newline facts (2026-09-23, this repo): mw-worker-visibility-gate,
 * mw-task-scope-isolation and mw-worker-progress-persist pm-state.md are all
 * pure CRLF (LF-only count 0), while agent-team-loop/pm-state.md is pure LF —
 * so the sync must detect and preserve the dominant newline (P-010: a newline
 * flip would show up as a whole-file diff). pm/StateManager.write() must NOT
 * be reused for this: it rewrites the file as the old 3-section template and
 * would erase the 7-section framework template and its evidence areas.
 *
 * The suite config is `silent: "passed-only"` and swallows console.log from
 * green tests, so `[VERIFY]` lines go straight to stdout via process.stdout.write.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { syncPmStateClaimId } from "../../src/extensions/agent-team-loop/shared/pm-state-claim.ts";

/* The suite swallows console.log from green tests; write the evidence line
 * straight to stdout so the required command surfaces it. */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

/** Framework 7-section pm-state.md sample (the advance_phase.py template
 * shape, plus the update_index.py claim stub's '- Claim-Id:' mirror line). */
const SAMPLE_LINES: string[] = [
	"# PM State: sample-key",
	"",
	"## 1. Snapshot",
	"- Key: sample-key",
	"- Claim-Id: OLDWORD:1234",
	"- Phase: EXECUTE",
	"- Next Action: 收尾 T-2 单行替换验证",
	"- Started: 2026-09-23 17:42",
	"- Updated: 2026-09-23 17:45",
	"",
	"## 2. Task Status",
	"- T-2: running（单行原地替换，不动 7 段模板）",
	"",
	"## 3. Evidence Ledger",
	"- 2026-09-23: evidence/research/design-gate-panel-claim-interfaces-2026-09-23.md",
	"",
	"## 4. Hypothesis Queue",
	"*(empty)*",
	"",
	"## 5. Decisions",
	"- D-107: 单行原地替换 + 换行探测 + 原子写",
	"",
	"## 6. Turn End Records",
	"*(empty)*",
	"",
	"## 7. Process Log",
	"- 2026-09-23: EXECUTE start",
];

const H2_RE = /^## /gm;
const UPDATED_RE = /^- Updated:/gm;
const CLAIM_LINE_RE = /^- Claim-Id:[^\r\n]*/m;
const CLAIM_LINE_G_RE = /^- Claim-Id:[^\r\n]*/gm;

const tmpRoots: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "atl-pm-state-claim-"));
	tmpRoots.push(dir);
	return dir;
}

/** Writes `lines` joined with `nl` (plus a trailing terminator unless `trailing`
 * is false) as UTF-8 bytes and returns the pm-state.md path. */
function writePmState(root: string, key: string, lines: string[], nl: string, trailing = true): string {
	const dir = path.join(root, key);
	fs.mkdirSync(dir, { recursive: true });
	const file = path.join(dir, "pm-state.md");
	fs.writeFileSync(file, Buffer.from(lines.join(nl) + (trailing ? nl : ""), "utf8"));
	return file;
}

/** Count of `seq` byte sequences in `buf` (e.g. "\r\n" pairs). */
function countSeq(buf: Buffer, seq: string): number {
	const needle = Buffer.from(seq, "latin1");
	let count = 0;
	let at = buf.indexOf(needle);
	while (at !== -1) {
		count++;
		at = buf.indexOf(needle, at + needle.length);
	}
	return count;
}

/** Count of 0x0A bytes (total LF terminators, CRLF included). */
function countLf(buf: Buffer): number {
	let count = 0;
	for (const byte of buf) {
		if (byte === 0x0a) count++;
	}
	return count;
}

function countMatches(text: string, re: RegExp): number {
	return (text.match(re) ?? []).length;
}

/** Byte offsets of the first claim line inside `buf`'s latin1 view (latin1
 * chars map 1:1 to bytes, so char indices are byte offsets). */
function claimLineRange(buf: Buffer): { start: number; length: number } {
	const m = buf.toString("latin1").match(CLAIM_LINE_RE);
	if (m === null || m.index === undefined) throw new Error("no '- Claim-Id:' line in sample");
	return { start: m.index, length: m[0].length };
}

afterEach(() => {
	for (const dir of tmpRoots.splice(0)) {
		fs.rmSync(dir, { recursive: true, force: true });
	}
});

// ── VC-010: single-line in-place replacement ──────────────────────────────────

describe("syncPmStateClaimId (D-107, VC-010)", () => {
	it("replaces only the Claim-Id line of a CRLF 7-section template, byte-for-byte elsewhere", () => {
		const root = mkdtemp();
		const file = writePmState(root, "sample-key", SAMPLE_LINES, "\r\n");
		const before = fs.readFileSync(file);

		const result = syncPmStateClaimId(root, "sample-key", "NEWHOST:5678");
		expect(result).toEqual({ ok: true });

		const after = fs.readFileSync(file);
		const beforeText = before.toString("utf8");
		const afterText = after.toString("utf8");

		// (a) the snapshot claim line carries the new value verbatim
		const claimLine = afterText.match(CLAIM_LINE_RE)?.[0] ?? "";
		const claimIdsEqual = claimLine === "- Claim-Id: NEWHOST:5678";
		expect(claimIdsEqual).toBe(true);

		// (b) newline bytes: CRLF count unchanged, no LF-only line appeared
		const crlfBefore = countSeq(before, "\r\n");
		const crlfAfter = countSeq(after, "\r\n");
		const lfOnlyAfter = countLf(after) - crlfAfter;
		expect(crlfAfter).toBe(crlfBefore);
		expect(lfOnlyAfter).toBe(0);
		expect(countLf(after)).toBe(countLf(before));

		// (c) the 7 framework sections survive untouched
		const headingsBefore = countMatches(beforeText, H2_RE);
		const headingsAfter = countMatches(afterText, H2_RE);
		expect(headingsAfter).toBe(headingsBefore);
		expect(headingsAfter).toBe(7);

		// (d) machine-interface '- Updated:' line count unchanged
		const updatedBefore = countMatches(beforeText, UPDATED_RE);
		const updatedAfter = countMatches(afterText, UPDATED_RE);
		expect(updatedAfter).toBe(updatedBefore);
		expect(updatedAfter).toBe(1);

		// (e) every byte outside the replaced line is identical
		const b = claimLineRange(before);
		const a = claimLineRange(after);
		const prefixEqual = before.subarray(0, b.start).equals(after.subarray(0, a.start));
		const suffixEqual = before.subarray(b.start + b.length).equals(after.subarray(a.start + a.length));
		expect(prefixEqual).toBe(true);
		expect(suffixEqual).toBe(true);

		// the atomic write consumed its tmp file
		expect(fs.existsSync(`${file}.tmp`)).toBe(false);

		verify(
			`[VERIFY] VC-010: claim_ids_equal=${claimIdsEqual} headings=${headingsAfter} updated_lines=${updatedAfter} ` +
				`crlf=${crlfBefore}->${crlfAfter} lf_only=${lfOnlyAfter} bytes=${before.length}->${after.length} ` +
				`outside_line_identical=${prefixEqual && suffixEqual}`,
		);
	});

	it("keeps a pure-LF file pure LF (no CRLF introduced)", () => {
		const root = mkdtemp();
		const file = writePmState(root, "lf-key", SAMPLE_LINES, "\n");
		const before = fs.readFileSync(file);

		const result = syncPmStateClaimId(root, "lf-key", "NEWHOST:5678");
		expect(result).toEqual({ ok: true });

		const after = fs.readFileSync(file);
		const afterText = after.toString("utf8");
		const claimLine = afterText.match(CLAIM_LINE_RE)?.[0] ?? "";
		const claimIdsEqual = claimLine === "- Claim-Id: NEWHOST:5678";
		const crlfAfter = countSeq(after, "\r\n");
		const lfOnlyAfter = countLf(after) - crlfAfter;
		const headings = countMatches(afterText, H2_RE);
		const updatedLines = countMatches(afterText, UPDATED_RE);
		expect(claimIdsEqual).toBe(true);
		expect(crlfAfter).toBe(0);
		expect(lfOnlyAfter).toBe(countLf(before));
		expect(headings).toBe(7);
		expect(updatedLines).toBe(1);
		verify(
			`[VERIFY] VC-010: lf_variant claim_ids_equal=${claimIdsEqual} crlf=${crlfAfter} lf_only=${lfOnlyAfter} ` +
				`headings=${headings} updated_lines=${updatedLines} bytes=${before.length}->${after.length}`,
		);
	});

	it("replaces only the first '- Claim-Id:' line when several exist (count=1)", () => {
		const root = mkdtemp();
		const decoy = "- Claim-Id: 20260808-174558-3176（历史镜像行，不得改写）";
		const file = writePmState(root, "decoy-key", [...SAMPLE_LINES, "", decoy], "\r\n");

		const result = syncPmStateClaimId(root, "decoy-key", "NEWHOST:5678");
		expect(result).toEqual({ ok: true });

		const claimLines = fs.readFileSync(file, "utf8").match(CLAIM_LINE_G_RE) ?? [];
		expect(claimLines).toHaveLength(2);
		expect(claimLines[0]).toBe("- Claim-Id: NEWHOST:5678");
		expect(claimLines[1]).toBe(decoy);
	});

	it("replaces a bare value-less claim line at EOF without adding a trailing newline", () => {
		const root = mkdtemp();
		const lines = ["# PM State: eof-key", "", "## 1. Snapshot", "- Key: eof-key", "- Claim-Id:"];
		const file = writePmState(root, "eof-key", lines, "\n", false);

		const result = syncPmStateClaimId(root, "eof-key", "NEWHOST:5678");
		expect(result).toEqual({ ok: true });

		const text = fs.readFileSync(file, "utf8");
		expect(text.endsWith("- Claim-Id: NEWHOST:5678")).toBe(true);
		expect(text.endsWith("\n")).toBe(false);
	});

	it("refuses to write when claimId itself carries a line break (P-010 guard)", () => {
		const root = mkdtemp();
		const file = writePmState(root, "guard-key", SAMPLE_LINES, "\r\n");
		const before = fs.readFileSync(file);

		const result = syncPmStateClaimId(root, "guard-key", "NEWHOST:5678\nINJECTED:1");
		expect(result.ok).toBe(false);
		expect(result.reason).toContain("newline");
		expect(fs.readFileSync(file).equals(before)).toBe(true);
		expect(fs.existsSync(`${file}.tmp`)).toBe(false);
	});
});

// ── VC-011: insert branch (D-111) / fail-closed branches ─────────────────────

describe("syncPmStateClaimId missing-line branches (D-111, VC-011)", () => {
	it("inserts the Claim-Id line directly after '- Key:' when it is missing (CRLF, byte-safe)", () => {
		const root = mkdtemp();
		const file = writePmState(
			root,
			"damaged-key",
			SAMPLE_LINES.filter((l) => !l.startsWith("- Claim-Id:")),
			"\r\n",
		);
		const before = fs.readFileSync(file);

		const result = syncPmStateClaimId(root, "damaged-key", "NEWHOST:5678");
		expect(result).toEqual({ ok: true });

		const after = fs.readFileSync(file);
		const beforeText = before.toString("utf8");
		const afterText = after.toString("utf8");

		// (a) the inserted claim line carries the new value verbatim (exactly one)
		const claimLine = afterText.match(CLAIM_LINE_RE)?.[0] ?? "";
		const claimIdsEqual = claimLine === "- Claim-Id: NEWHOST:5678";
		expect(claimIdsEqual).toBe(true);
		expect((afterText.match(CLAIM_LINE_G_RE) ?? []).length).toBe(1);

		// (b) the insertion point is directly after the '- Key:' line
		const afterKeyLine = afterText.includes("- Key: sample-key\r\n- Claim-Id: NEWHOST:5678\r\n");
		expect(afterKeyLine).toBe(true);
		const inserted = claimIdsEqual && afterKeyLine;

		// (c) newline bytes: exactly one CRLF line added, still no LF-only line
		const crlfBefore = countSeq(before, "\r\n");
		const crlfAfter = countSeq(after, "\r\n");
		const lfOnlyAfter = countLf(after) - crlfAfter;
		expect(crlfAfter).toBe(crlfBefore + 1);
		expect(lfOnlyAfter).toBe(0);
		expect(countLf(after)).toBe(countLf(before) + 1);

		// (e) the 7 framework sections and the machine '- Updated:' line survive
		const headingsBefore = countMatches(beforeText, H2_RE);
		const headingsAfter = countMatches(afterText, H2_RE);
		const updatedBefore = countMatches(beforeText, UPDATED_RE);
		const updatedAfter = countMatches(afterText, UPDATED_RE);
		expect(headingsAfter).toBe(headingsBefore);
		expect(headingsAfter).toBe(7);
		expect(updatedAfter).toBe(updatedBefore);
		expect(updatedAfter).toBe(1);

		// (d) every byte outside the inserted line (plus its terminator) is
		// identical: deleting the inserted line from `after` restores `before`.
		const m = after.toString("latin1").match(CLAIM_LINE_RE);
		if (m === null || m.index === undefined) throw new Error("inserted claim line not found");
		let lineEnd = m.index + m[0].length;
		if (after.slice(lineEnd, lineEnd + 2).toString("latin1") === "\r\n") lineEnd += 2;
		else if (after[lineEnd] === 0x0a) lineEnd += 1;
		const outside = Buffer.concat([after.subarray(0, m.index), after.subarray(lineEnd)]);
		const outsideIdentical = outside.equals(before);
		expect(outsideIdentical).toBe(true);

		// the atomic write consumed its tmp file
		expect(fs.existsSync(`${file}.tmp`)).toBe(false);

		verify(`[VERIFY] VC-011: inserted=${inserted} ok=${result.ok} outside_identical=${outsideIdentical}`);
		verify(
			`[MEASURE] VC-011 insert: crlf=${crlfBefore}->${crlfAfter} lf_only=${lfOnlyAfter} ` +
				`headings=${headingsBefore}->${headingsAfter} updated_lines=${updatedBefore}->${updatedAfter} ` +
				`bytes=${before.length}->${after.length}`,
		);
	});

	it("refuses to write when neither '- Claim-Id:' nor '- Key:' exists and leaves the file untouched", () => {
		const root = mkdtemp();
		const file = writePmState(
			root,
			"anchorless-key",
			["# PM State: anchorless-key", "", "## 1. Snapshot", "- Phase: EXECUTE", "- Updated: 2026-09-23 17:45"],
			"\r\n",
		);
		const before = fs.readFileSync(file);

		const result = syncPmStateClaimId(root, "anchorless-key", "NEWHOST:5678");
		expect(result).toEqual({ ok: false, reason: "pm-state.md has no '- Key:' or '- Claim-Id:' line" });

		const untouched = before.equals(fs.readFileSync(file));
		expect(untouched).toBe(true);
		expect(fs.existsSync(`${file}.tmp`)).toBe(false);
		verify(`[VERIFY] VC-011: no_key_line ok=${result.ok} untouched=${untouched}`);
	});

	it("returns ok=false and creates nothing when pm-state.md is missing", () => {
		const root = mkdtemp();
		const keyDir = path.join(root, "ghost-key");

		const result = syncPmStateClaimId(root, "ghost-key", "NEWHOST:5678");
		expect(result).toEqual({ ok: false, reason: "pm-state.md missing" });

		const fileCreated = fs.existsSync(path.join(keyDir, "pm-state.md"));
		const dirCreated = fs.existsSync(keyDir);
		expect(fileCreated).toBe(false);
		expect(dirCreated).toBe(false);
		verify(`[VERIFY] VC-011: claim_ok=false file_created=${fileCreated} dir_created=${dirCreated}`);
	});
});
