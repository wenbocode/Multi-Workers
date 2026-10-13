/**
 * T-08 requirement 3b: drive the COMPILED change-ledger recovery judge over the
 * runtime trace.log produced by `run_writefile_retest.py`, proving the
 * "declaration is a subset of the [WRITE_FILE] event set" check works on real
 * runtime data (not a hand-written fixture).
 *
 * Run (repo root):
 *   node .agenticdoc/mw-dispatch-card-gate/evidence/runs/t08-cutover-20261012/scripts/ledger_check.mjs
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const run = path.resolve(here, "..");
const repo = path.resolve(here, "../../../../../..");
const mod = await import(
	pathToFileURL(
		path.join(repo, "packages/coding-agent/dist/extensions/agent-team-loop/shared/change-ledger.js"),
	).href
);

const tracePath = path.join(
	run,
	"fixture/writefile/.agenticdoc/mw-dispatch-card-gate/workers/mwd-writefile-retest/trace.log",
);
const trace = fs.readFileSync(tracePath, "utf8");
console.log(`trace: ${tracePath}`);
console.log(`recorded events: ${JSON.stringify(mod.parseWriteFileEvents(trace))}`);

const declaredOk = ["## 改动清单", "- notes.txt"].join("\n");
const declaredGap = ["## 改动清单", "- notes.txt", "- ghost.txt"].join("\n");
const ok = mod.diffLedger(declaredOk, trace);
const gap = mod.diffLedger(declaredGap, trace);
console.log(`declaration subset of events -> extra=${JSON.stringify(ok.extra)} (expect [])`);
console.log(`additional declared ghost   -> extra=${JSON.stringify(gap.extra)} (expect ["ghost.txt"])`);
if (gap.extra.length !== 1 || !gap.extra[0].endsWith("ghost.txt")) {
	console.error("LEDGER CHECK FAILED");
	process.exit(1);
}
console.log("LEDGER CHECK OK");
