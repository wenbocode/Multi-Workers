/**
 * mwds-t26-closeout-verify.test.ts — T-26 (key mw-dispatch-card-gate) closeout:
 * requirement 7 "真实越界仍红" recheck, read-only.
 *
 * Two real-overreach classes must still be red after the T-25 dotless
 * existence arbitration:
 *   (a) a real repo file declared in the report but absent from the trace's
 *       `[WRITE_FILE]` events is `extra` (dotted-path class) — checked against
 *       the actual repo file `packages/multi-workers/launcher.py`;
 *   (b) an extensionless `scripts/deploy` that exists on disk is a declaration:
 *       recorded ⇒ not `extra`; unrecorded ⇒ `extra` (T-25 arbitration, red
 *       kept).
 *
 * Pure assertions over pure functions — no writes, no network.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { diffLedger } from "../../src/extensions/agent-team-loop/shared/change-ledger.ts";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(TEST_DIR, "../../../..");
const LAUNCHER_REL = "packages/multi-workers/launcher.py";

const tempDirs: string[] = [];
function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}
afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

function report(body: readonly string[]): string {
	return ["## 结论", "", "done", "", "## 改动清单", "", ...body, "", "## 残留与未验证", "", "none"].join("\n");
}

function trace(recorded: readonly string[]): string {
	return recorded.map((file) => `[WRITE_FILE] path=${file}`).join("\n");
}

function tempRepoWithDeploy(): string {
	const root = mkdtemp("mwds-t26-repo-");
	fs.mkdirSync(path.join(root, "scripts"), { recursive: true });
	fs.writeFileSync(path.join(root, "scripts", "deploy"), "#!/bin/sh\necho deploy\n", "utf8");
	return root;
}

describe("T-26 requirement 7 — the real file exists (sanity)", () => {
	it("launcher.py and the fixture source really exist on disk", () => {
		expect(fs.existsSync(path.join(REPO_ROOT, LAUNCHER_REL))).toBe(true);
		expect(fs.existsSync(path.join(REPO_ROOT, "scripts", "deploy"))).toBe(false);
		console.log(`[VERIFY] T26-7 repo_root=${REPO_ROOT} launcher_exists=1 repo_scripts_deploy_exists=0`);
	});
});

describe("T-26 requirement 7a — dotted real file, declared, no event ⇒ extra", () => {
	it("launcher.py declared but absent from the trace is RED (extra names it)", () => {
		const text = report([`- ${LAUNCHER_REL} — 越界声明`]);
		const ledger = diffLedger(text, trace(["packages/coding-agent/src/other.ts"]), { projectRoot: REPO_ROOT });
		console.log(`[VERIFY] T26-7a declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}]`);
		expect(ledger.declared).toEqual([LAUNCHER_REL]);
		expect(ledger.extra).toEqual([LAUNCHER_REL]);
		expect(ledger.unjudgeable).toBe(false);
	});

	it("control: the same declaration with a matching event is not extra", () => {
		const text = report([`- ${LAUNCHER_REL} — 已记录`]);
		const ledger = diffLedger(text, trace([LAUNCHER_REL]), { projectRoot: REPO_ROOT });
		console.log(`[VERIFY] T26-7a-recorded declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}]`);
		expect(ledger.declared).toEqual([LAUNCHER_REL]);
		expect(ledger.extra).toEqual([]);
	});
});

describe("T-26 requirement 7b — extensionless scripts/deploy arbitration keeps red", () => {
	const DECLARED = "scripts/deploy";

	it("with a matching event: declared, not extra", () => {
		const root = tempRepoWithDeploy();
		const ledger = diffLedger(report([`- ${DECLARED} — 无扩展名部署脚本`]), trace([DECLARED]), {
			projectRoot: root,
		});
		console.log(`[VERIFY] T26-7b-recorded declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}]`);
		expect(ledger.declared).toEqual([DECLARED]);
		expect(ledger.extra).toEqual([]);
	});

	it("without the event: declared and RED (extra names it)", () => {
		const root = tempRepoWithDeploy();
		const ledger = diffLedger(
			report([`- ${DECLARED} — 无扩展名部署脚本`]),
			trace(["packages/coding-agent/src/other.ts"]),
			{
				projectRoot: root,
			},
		);
		console.log(`[VERIFY] T26-7b-miss declared=[${ledger.declared.join(",")}] extra=[${ledger.extra.join(",")}]`);
		expect(ledger.declared).toEqual([DECLARED]);
		expect(ledger.extra).toEqual([DECLARED]);
		expect(ledger.unjudgeable).toBe(false);
	});
});
