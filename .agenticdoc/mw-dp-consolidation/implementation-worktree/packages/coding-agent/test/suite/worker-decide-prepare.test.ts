/**
 * worker-decide-prepare.test.ts - mw-decision-substitution W8/W10: the
 * `decide_prepare` worker role (renamed from `decision` by W10, no alias).
 *
 * What is pinned here (card requirement 7, six-plus invariants):
 *
 * 1. the tool allowlist entry - read/find/grep/ls/bash, no write/edit, and the
 *    narrow `worker_file` channel is what a decide_prepare worker writes through;
 * 2. the old `decision` type value is gone (no alias): unregistered in the
 *    runtime table and not part of the dispatchable type list;
 * 3. the fixed prompt - scaffold, fill from evidence, `book check`, "do not
 *    change thresholds / do not invent the expected answer / do not edit code";
 * 4. `allow-send` parsing - only an explicit `yes` authorizes a send;
 * 5. the read-only bash policy - `book check` / `git diff` / `rg` / `cat` pass,
 *    mutations, redirections and chained writes are blocked;
 * 6. `decide run|ask --book` is blocked unless the card authorized the send;
 * 7. the `book new` scaffold is allowed but its `--out` stays in the books dir;
 * 8. the write face - `worker_file` is confined to `<key>/evidence/books/**`.
 *
 * Pure functions only: every case imports the exported policy and asserts the
 * verdict. No provider, no spawn, no network.
 */

import { describe, expect, it } from "vitest";
import { DISPATCHABLE_TYPES, roleForTaskType } from "../../src/extensions/agent-team-loop/shared/dispatch-models.ts";
import {
	activeToolsForType,
	DECIDE_PREPARE_TYPE,
	DECISION_TYPE_PROMPT,
	decisionAllowsSend,
	decisionBashBlockReason,
	decisionWorkerFilePathAllowed,
	isShellRole,
	isWritelessRole,
	REGISTERED_WORKER_TYPES,
	toolsForType,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

describe("W8/W10 decide_prepare worker type: tool allowlist", () => {
	it("has the read-only set plus bash, and no write/edit", () => {
		expect(DECIDE_PREPARE_TYPE).toBe("decide_prepare");
		expect(toolsForType("decide_prepare")).toEqual(["read", "find", "grep", "ls", "bash"]);
		expect(isShellRole("decide_prepare")).toBe(true);
		// No write/edit: the book goes through the narrow worker_file channel.
		expect(isWritelessRole("decide_prepare")).toBe(true);
		expect(REGISTERED_WORKER_TYPES).toContain("decide_prepare");
	});

	it("keeps the old `decision` value out (no alias)", () => {
		expect(REGISTERED_WORKER_TYPES).not.toContain("decision");
		expect([...DISPATCHABLE_TYPES]).toContain("decide_prepare");
		expect([...DISPATCHABLE_TYPES]).not.toContain("decision");
		// roleForTaskType keeps its unknown -> coding fallback; the old value
		// must NOT resolve to the decide_prepare bucket.
		expect(roleForTaskType("decide_prepare")).toBe("decide_prepare");
		expect(roleForTaskType("decision")).toBe("coding");
	});

	it("gets the narrow worker_file channel but nothing that edits code", () => {
		const active = activeToolsForType("decide_prepare");
		expect(active).toContain("worker_file");
		expect(active).not.toContain("write");
		expect(active).not.toContain("edit");
	});
});

describe("W8/W10 decide_prepare worker type: fixed prompt", () => {
	it("names the scaffold, the evidence shape, the checker and the red lines", () => {
		expect(DECISION_TYPE_PROMPT).toContain("mw decide book new <dp> --out");
		expect(DECISION_TYPE_PROMPT).toContain("evidence/books/");
		expect(DECISION_TYPE_PROMPT).toContain("path:line");
		expect(DECISION_TYPE_PROMPT).toContain("mw decide book check");
		expect(DECISION_TYPE_PROMPT).toContain("不要改阈值");
		expect(DECISION_TYPE_PROMPT).toContain("不要填预期答案");
		expect(DECISION_TYPE_PROMPT).toContain("不改代码");
		expect(DECISION_TYPE_PROMPT).toContain("allow-send: no");
		expect(DECISION_TYPE_PROMPT).toContain("[mw decide_prepare worker]");
	});
});

describe("W8/W10 decide_prepare worker type: allow-send authority", () => {
	it("defaults to no and only accepts an explicit yes", () => {
		expect(decisionAllowsSend("## 决策本参数\n\n- dp: dp3-worker-clarify")).toBe(false);
		expect(decisionAllowsSend("- allow-send: no")).toBe(false);
		expect(decisionAllowsSend("- allow-send: yes")).toBe(true);
		expect(decisionAllowsSend("allow-send: YES")).toBe(true);
		expect(decisionAllowsSend("- allow-send: 也许")).toBe(false);
	});
});

describe("W8/W10 decide_prepare worker type: read-only bash policy", () => {
	it("allows the read-only subset and the book checker", () => {
		for (const command of [
			"mw decide book check evidence/books/dp3-book.json",
			"git diff --stat",
			"rg -n required_state_fields packages/multi-workers",
			"cat .mw/decide.json",
			"ls evidence/books",
			"mw decide book check a.json && cat a.json",
		]) {
			expect(decisionBashBlockReason(command, false), command).toBeNull();
		}
	});

	it("blocks mutations, redirections and chained writes", () => {
		for (const command of [
			"rm -rf evidence",
			"sed -i 's/a/b/' evidence/books/x.json",
			"cat x > evidence/books/y.json",
			"rg foo && rm -rf evidence",
			"python -c 'print(1)'",
			"git commit -m x",
		]) {
			const reason = decisionBashBlockReason(command, false);
			expect(reason, command).not.toBeNull();
			expect(reason).toContain("decision:");
		}
	});

	it("blocks `decide run|ask --book` unless allow-send is yes", () => {
		const blocked = decisionBashBlockReason("mw decide ask dp3 --book evidence/books/x.json", false);
		expect(blocked).toContain("allow-send: no");
		expect(decisionBashBlockReason("mw decide run --dp dp3 --book evidence/books/x.json", false)).not.toBeNull();
		// Authorized send passes the role policy (the service gate still applies).
		expect(decisionBashBlockReason("mw decide ask dp3 --book evidence/books/x.json", true)).toBeNull();
	});

	it("allows the book new scaffold but confines its --out to the books dir", () => {
		expect(decisionBashBlockReason("mw decide book new dp3-worker-clarify", false)).toBeNull();
		expect(
			decisionBashBlockReason("mw decide book new dp3-worker-clarify --out evidence/books/dp3-book.json", false),
		).toBeNull();
		const escaped = decisionBashBlockReason(
			"mw decide book new dp3-worker-clarify --out packages/ai/src/leak.json",
			false,
		);
		expect(escaped).toContain("evidence/books");
	});
});

describe("W8/W10 decide_prepare worker type: write face", () => {
	it("confines worker_file to evidence/books/**", () => {
		expect(decisionWorkerFilePathAllowed("evidence/books/dp3-book.json")).toBe(true);
		expect(decisionWorkerFilePathAllowed(".agenticdoc/k1/evidence/books/dp3-book.json")).toBe(true);
		// The broader evidence tree, the report files and an escape are refused.
		expect(decisionWorkerFilePathAllowed("evidence/research/notes.md")).toBe(false);
		expect(decisionWorkerFilePathAllowed("report.md")).toBe(false);
		expect(decisionWorkerFilePathAllowed("evidence/books/../../src/x.ts")).toBe(false);
		expect(decisionWorkerFilePathAllowed("/tmp/books/x.json")).toBe(false);
	});
});
