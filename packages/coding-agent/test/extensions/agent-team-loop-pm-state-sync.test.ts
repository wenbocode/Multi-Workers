/**
 * Claim-sync + phase-wiring tests for the dispatch entrances
 * (mw-worker-visibility-gate T-3; AC/VC-010..012, design D-107..D-110).
 *
 * Three surfaces wired by T-3:
 *  1. takeOverKey now mirrors the claim into {key}/pm-state.md's
 *     '- Claim-Id:' line via syncPmStateClaimId (D-108); the index row stays
 *     authoritative, so a failed mirror keeps the claim ok and surfaces as
 *     exactly one warning line (VC-010). A pm-state.md missing the
 *     '- Claim-Id:' line gets it inserted after '- Key:' instead (D-111,
 *     T-6) — no warning, and the mirror converges to the index row (VC-011).
 *  2. The dispatch_worker tool entrance passes the owner key's REAL phase
 *     into the docs gate (D-101): a SPEC-phase key with only the spec-side
 *     chain dispatches with type=coding (VC-012), and a DESIGN-phase key
 *     without the design side is blocked — the proof the wiring (not the
 *     spec-tier default) is what drives the tool.
 *  3. The dispatchNewTasks background scan reads the SCAN key's own
 *     pm-state phase (D-110's third call site).
 *
 * The pm-state fixture is the framework 7-section template in CRLF — the
 * byte-level facts measured in agent-team-loop-pm-state-claim.test.ts (T-2):
 * section count, single '- Updated:' line, and the CRLF style must all
 * survive a synced takeover untouched.
 *
 * [VERIFY] lines go to stdout via process.stdout.write (P-006).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionContext } from "../../src/core/extensions/types.ts";
import { dispatchNewTasks } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import {
	claimSyncWarningText,
	registerWorkerTools,
	takeOverKey,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

/* The suite swallows console.log from green tests; write the evidence line
 * straight to stdout so the required command surfaces it. */
function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

/** Framework 7-section pm-state.md sample (same shape as T-2's fixture). */
const SAMPLE_LINES: string[] = [
	"# PM State: sample-key",
	"",
	"## 1. Snapshot",
	"- Key: sample-key",
	"- Claim-Id: OLDWORD:1234",
	"- Phase: EXECUTE",
	"- Next Action: 收尾 T-3 接线验证",
	"- Started: 2026-09-23 17:42",
	"- Updated: 2026-09-23 17:45",
	"",
	"## 2. Task Status",
	"- T-3: running（接线：门禁传相位 + 面板聚合行 + claim 同步）",
	"",
	"## 3. Evidence Ledger",
	"- 2026-09-23: evidence/research/design-gate-panel-claim-interfaces-2026-09-23.md",
	"",
	"## 4. Hypothesis Queue",
	"*(empty)*",
	"",
	"## 5. Decisions",
	"- D-108: claim 成功后同步 pm-state 镜像，失败不回滚",
	"",
	"## 6. Turn End Records",
	"*(empty)*",
	"",
	"## 7. Process Log",
	"- 2026-09-23: EXECUTE start",
];

const H2_RE = /^## /gm;
const UPDATED_RE = /^- Updated:/gm;
const CLAIM_VALUE_RE = /^- Claim-Id:[ \t]*(.*)$/m;

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "atl-pm-state-sync-"));
}

/** Write `lines` joined with CRLF (plus trailing terminator) as UTF-8 bytes
 * and return the pm-state.md path. */
function writePmState(root: string, key: string, lines: string[]): string {
	const dir = path.join(root, key);
	fs.mkdirSync(dir, { recursive: true });
	const file = path.join(dir, "pm-state.md");
	fs.writeFileSync(file, Buffer.from(`${lines.join("\r\n")}\r\n`, "utf8"));
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

/** Minimal tool-capturing pi (the fakeCmdPi pattern from
 * agent-team-loop.test.ts, reduced to what registerWorkerTools needs). */
function fakeToolPi(): {
	pi: ExtensionAPI;
	tools: Map<
		string,
		{
			execute: (
				id: string,
				params: unknown,
				signal: undefined,
				onUpdate: undefined,
				ctx: ExtensionContext,
			) => Promise<{ content: Array<{ type: string; text: string }> }>;
		}
	>;
} {
	const tools = new Map<
		string,
		{
			execute: (
				id: string,
				params: unknown,
				signal: undefined,
				onUpdate: undefined,
				ctx: ExtensionContext,
			) => Promise<{ content: Array<{ type: string; text: string }> }>;
		}
	>();
	const pi = {
		registerTool: (tool: {
			name: string;
			execute: (
				id: string,
				params: unknown,
				signal: undefined,
				onUpdate: undefined,
				ctx: ExtensionContext,
			) => Promise<{ content: Array<{ type: string; text: string }> }>;
		}) => {
			tools.set(tool.name, tool);
		},
		sendMessage: () => {},
	} as unknown as ExtensionAPI;
	return { pi, tools };
}

/** Minimal ExtensionContext for a tool execute call. */
function fakeToolCtx(): ExtensionContext {
	return {
		hasUI: true,
		ui: { notify: () => {}, setWidget: () => {} },
	} as unknown as ExtensionContext;
}

/** Complete spec-side chain for a key (no goal.md → §0 check skipped):
 * spec.md >= 500 bytes with a numbered AC, and one spec research note. */
function writeSpecSide(root: string, key: string): void {
	const keyDir = path.join(root, key);
	fs.mkdirSync(keyDir, { recursive: true });
	fs.writeFileSync(
		path.join(keyDir, "spec.md"),
		`# Spec\n${"x".repeat(600)}\n\n| AC-001 | in x, y returns z |\n`,
		"utf8",
	);
	const research = path.join(keyDir, "evidence", "research");
	fs.mkdirSync(research, { recursive: true });
	fs.writeFileSync(path.join(research, "spec-topic-2026-01-01.md"), "# research\n", "utf8");
}

/** A key whose pm-state.md carries only the phase line. */
function writePhaseOnly(root: string, key: string, phase: string): string {
	const dir = path.join(root, key);
	fs.mkdirSync(dir, { recursive: true });
	const file = path.join(dir, "pm-state.md");
	fs.writeFileSync(file, `- Phase: ${phase}\n`, "utf8");
	return file;
}

// ── VC-010/VC-011: takeOverKey mirrors the claim into pm-state.md ────────────

describe("takeOverKey claim sync (D-107/D-108)", () => {
	it("VC-010: takeover mirrors the claim id into pm-state.md, byte-safe", async () => {
		const root = mkdtemp();
		try {
			const file = writePmState(root, "key-sync", SAMPLE_LINES);
			const before = fs.readFileSync(file);
			const indexStore = new IndexStore(root);

			const result = await takeOverKey(indexStore, "key-sync", false, root);
			expect(result.ok).toBe(true);
			expect(result.claimSync?.ok).toBe(true);

			const after = fs.readFileSync(file);
			const text = after.toString("utf8");
			// (b) the mirrored value equals the index row's Claim column.
			const fileClaim = CLAIM_VALUE_RE.exec(text)?.[1]?.trim() ?? "";
			const indexClaim = indexStore.findByKey("key-sync")?.claimId ?? "";
			const claimIdsEqual = fileClaim === indexClaim && indexClaim === result.claimId;
			expect(claimIdsEqual).toBe(true);
			// (c) the 7 framework sections survive.
			const headings = (text.match(H2_RE) ?? []).length;
			expect(headings).toBe(7);
			// (d) the single machine '- Updated:' line survives.
			const updatedLines = (text.match(UPDATED_RE) ?? []).length;
			expect(updatedLines).toBe(1);
			// (e) the CRLF style is untouched.
			const crlfBefore = countSeq(before, "\r\n");
			const crlfAfter = countSeq(after, "\r\n");
			expect(crlfAfter).toBe(crlfBefore);
			verify(
				`[VERIFY] VC-010: claim_ids_equal=${claimIdsEqual} headings=${headings} updated_lines=${updatedLines} crlf=${crlfBefore}->${crlfAfter}`,
			);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-011: missing Claim-Id line is inserted after '- Key:' — no warning, mirror equals the index row", async () => {
		const root = mkdtemp();
		try {
			const file = writePmState(
				root,
				"damaged-key",
				SAMPLE_LINES.filter((l) => !l.startsWith("- Claim-Id:")),
			);
			const indexStore = new IndexStore(root);

			const result = await takeOverKey(indexStore, "damaged-key", false, root);
			expect(result.ok).toBe(true);
			expect(result.claimSync?.ok).toBe(true);
			// D-111: the line was inserted, so there is no warning at all.
			const warning = claimSyncWarningText("damaged-key", result.claimSync);
			expect(warning).toBe("");
			// The VC-010 invariant now also holds for a key whose pm-state.md was
			// created without the mirror line: file value == index row Claim column.
			const text = fs.readFileSync(file, "utf8");
			const fileClaim = CLAIM_VALUE_RE.exec(text)?.[1]?.trim() ?? "";
			const indexClaim = indexStore.findByKey("damaged-key")?.claimId ?? "";
			const claimIdsEqual = fileClaim === indexClaim && indexClaim === result.claimId;
			expect(claimIdsEqual).toBe(true);
			// The insert landed directly after '- Key:' and kept the template
			// shape (7 sections, one machine '- Updated:' line).
			expect(text).toContain("- Key: sample-key\r\n- Claim-Id: ");
			const headings = (text.match(H2_RE) ?? []).length;
			expect(headings).toBe(7);
			const updatedLines = (text.match(UPDATED_RE) ?? []).length;
			expect(updatedLines).toBe(1);
			// Success / never-ran syncs produce no warning text at all.
			expect(claimSyncWarningText("k", { ok: true })).toBe("");
			expect(claimSyncWarningText("k", undefined)).toBe("");
			verify(
				`[VERIFY] VC-011: claim_ok=${result.ok} warnings=${warning === "" ? 0 : 1} ` +
					`claim_ids_equal=${claimIdsEqual} headings=${headings} updated_lines=${updatedLines}`,
			);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── VC-012 + wiring: the dispatch entrances pass the REAL phase ──────────────

describe("dispatch entrances read the owner key's phase (D-101/D-110)", () => {
	it("VC-012: type=coding dispatch at phase SPEC is not blocked by the phase gate", async () => {
		const root = mkdtemp();
		try {
			writePhaseOnly(root, "vc12-key", "SPEC");
			writeSpecSide(root, "vc12-key");
			const ws = new WorkerStore(root);
			const is = new IndexStore(root);
			const { pi, tools } = fakeToolPi();
			registerWorkerTools(pi, ws, new AckStore(root), is, root, { key: undefined });
			const tool = tools.get("dispatch_worker");
			if (!tool) throw new Error("dispatch_worker not registered");

			const r = await tool.execute(
				"id-vc12",
				{ task_key: "t-vc12", description: "work", type: "coding", key: "vc12-key" },
				undefined,
				undefined,
				fakeToolCtx(),
			);
			const text = r.content[0]?.text ?? "";
			expect(text).not.toContain("missing phase documentation");
			const taskMd = path.join(root, "vc12-key", "workers", "t-vc12", "task.md");
			expect(fs.existsSync(taskMd)).toBe(true);
			// The phase axis flowed into the task.md frontmatter as well.
			const taskMdText = fs.readFileSync(taskMd, "utf8");
			expect(taskMdText).toContain("type: coding");
			expect(taskMdText).toContain("phase: SPEC");
			const codingAtSpecAllowed = !text.includes("missing phase documentation") && fs.existsSync(taskMd);
			verify(`[VERIFY] VC-012: coding_at_spec_allowed=${codingAtSpecAllowed}`);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("wiring control: a DESIGN-phase key without design docs IS blocked at the tool entrance", async () => {
		const root = mkdtemp();
		try {
			// Same spec-side fixture, but the pm-state phase is DESIGN — the
			// design-side gaps must now block (proves the tool passes the real
			// phase, not the spec-tier default).
			writePhaseOnly(root, "design-key", "DESIGN");
			writeSpecSide(root, "design-key");
			const ws = new WorkerStore(root);
			const is = new IndexStore(root);
			const { pi, tools } = fakeToolPi();
			registerWorkerTools(pi, ws, new AckStore(root), is, root, { key: undefined });
			const tool = tools.get("dispatch_worker");
			if (!tool) throw new Error("dispatch_worker not registered");

			const r = await tool.execute(
				"id-design",
				{ task_key: "t-design", description: "work", type: "coding", key: "design-key" },
				undefined,
				undefined,
				fakeToolCtx(),
			);
			const text = r.content[0]?.text ?? "";
			expect(text).toContain("Worker dispatch blocked");
			expect(text).toContain("design.md missing or under 500 bytes");
			expect(fs.existsSync(path.join(root, "design-key", "workers", "t-design"))).toBe(false);
			expect(ws.readAll()).toHaveLength(0);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("wiring control: the dispatchNewTasks scan reads the SCAN key's pm-state phase (D-110)", async () => {
		const root = mkdtemp();
		try {
			writePhaseOnly(root, "scan-key", "DESIGN");
			writeSpecSide(root, "scan-key");
			const taskDir = path.join(root, "scan-key", "workers", "t-scan");
			fs.mkdirSync(taskDir, { recursive: true });
			fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
			const store = new WorkerStore(root);
			const gates: Array<{ key: string; gaps: string[] }> = [];

			// DESIGN phase + spec side only → blocked with both design-side gaps.
			await dispatchNewTasks(store, root, {
				warnedKeys: new Set<string>(),
				onDocGate: (key, gaps) => {
					gates.push({ key, gaps });
					return true;
				},
			});
			expect(store.readAll().filter((e) => e.taskKey === "t-scan")).toHaveLength(0);
			expect(gates).toHaveLength(1);
			expect(gates[0]?.gaps).toContain("design.md missing or under 500 bytes");
			expect(gates[0]?.gaps).toHaveLength(2);

			// Completing the design side unblocks the very same task.
			fs.writeFileSync(path.join(root, "scan-key", "design.md"), `# Design\n${"x".repeat(600)}`, "utf8");
			fs.writeFileSync(
				path.join(root, "scan-key", "evidence", "research", "design-topic-2026-01-01.md"),
				"# research\n",
				"utf8",
			);
			await dispatchNewTasks(store, root, {
				warnedKeys: new Set<string>(),
				onDocGate: (key, gaps) => {
					gates.push({ key, gaps });
					return true;
				},
			});
			expect(store.findByKey("t-scan")?.status).toBe("pending");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});
