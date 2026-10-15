// Ad-hoc reproduction probe: terminal-readback delivery scope gap.
// Doc: .agenticdoc/_scratch/readback-push-scope-gap-20261014.md
//
// Runs the REAL startWorkerPollLoop against a temp agenticdoc root and a fake
// pi.sendMessage recorder. No repo files are touched; the temp tree is deleted
// on exit.
//
// Run from repo root:
//   node .agenticdoc/_scratch/evidence/readback-push-scope-repro-20261014.mts

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { pathToFileURL } from "node:url";

const REPO = path.resolve(import.meta.dirname, "../../..");
const SRC = path.join(REPO, "packages/coding-agent/src/extensions/agent-team-loop");
const load = (rel: string) => import(pathToFileURL(path.join(SRC, rel)).href);

const { WorkerStore } = await load("shared/worker-store.ts");
const { AckStore } = await load("shared/ack-store.ts");
const { IndexStore } = await load("shared/index-store.ts");
const { startWorkerPollLoop } = await load("pm/pm-orchestrator.ts");

const TICK = 50;
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

function row(taskKey: string, status: string, key: string, taskDir: string): string {
	const now = new Date().toISOString();
	return [
		taskKey,
		status,
		"pi",
		"",
		path.join(taskDir, "task.md"),
		now,
		now,
		"",
		"manual",
	].join(" | ");
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "mw-readback-probe-"));
const root = path.join(tmp, "proj", ".agenticdoc");
fs.mkdirSync(root, { recursive: true });

const dirs: Record<string, string> = {};
for (const [key, taskKey] of [
	["keyA", "a1"],
	["keyA", "a2"],
	["keyB", "b1"],
	["keyB", "b2"],
	["keyC", "c1"],
]) {
	const d = path.join(root, key, "workers", taskKey);
	fs.mkdirSync(d, { recursive: true });
	fs.writeFileSync(path.join(d, "task.md"), `# ${taskKey}\n`);
	dirs[taskKey] = d;
}

const queue = path.join(root, "_workers.parallel");
function setQueue(lines: string[]): void {
	fs.writeFileSync(queue, `${lines.join("\n")}\n`);
}

// a1 running (this window's key), a2 ALREADY terminal under this window's key
// (isolates the open-time baseline), b1 running (another window's key),
// c1 ALREADY terminal under a key this window never watched.
const qA2Done = row("a2", "done", "keyA", dirs.a2);
const qC1Done = row("c1", "done", "keyC", dirs.c1);
setQueue([row("a1", "running", "keyA", dirs.a1), qA2Done, row("b1", "running", "keyB", dirs.b1), qC1Done]);

const deliveries: string[] = [];
const pi = new Proxy(
	{},
	{
		get: (_t, prop) => {
			if (prop === "sendMessage") {
				return (msg: { content?: string }) => {
					deliveries.push(String(msg?.content ?? "").split("\n")[0]);
				};
			}
			return () => undefined;
		},
	},
) as never;

const watch = { key: "keyA" };
const handle = startWorkerPollLoop(
	pi,
	new WorkerStore(root),
	new AckStore(root),
	new IndexStore(root),
	root,
	watch as never,
	{ ctx: undefined } as never,
	TICK,
);

const had = (taskKey: string) => deliveries.some((d) => d.includes(`[${taskKey}]`));
const count = (taskKey: string) => deliveries.filter((d) => d.includes(`[${taskKey}]`)).length;

await wait(TICK * 3);
const step1 = deliveries.length;

// b1 goes terminal while this window watches keyA -> skipped at the owner gate.
setQueue([row("a1", "running", "keyA", dirs.a1), qA2Done, row("b1", "done", "keyB", dirs.b1), qC1Done]);
await wait(TICK * 4);
const step2 = deliveries.length;

// The window now takes over keyB. b1 is unacked and terminal: expected push?
watch.key = "keyB";
await wait(TICK * 8);
const step3 = deliveries.length;

// Control: a SECOND keyB task that goes terminal while keyB IS watched.
setQueue([
	row("a1", "running", "keyA", dirs.a1),
	qA2Done,
	row("b1", "done", "keyB", dirs.b1),
	row("b2", "running", "keyB", dirs.b2),
	qC1Done,
]);
await wait(TICK * 3);
setQueue([
	row("a1", "running", "keyA", dirs.a1),
	qA2Done,
	row("b1", "done", "keyB", dirs.b1),
	row("b2", "done", "keyB", dirs.b2),
	qC1Done,
]);
await wait(TICK * 5);
const step4 = deliveries.length;

// keyC's row was terminal at open (baseline) -> must never be replayed.
watch.key = "keyC";
await wait(TICK * 6);
const step5 = deliveries.length;

clearInterval(handle);
fs.rmSync(tmp, { recursive: true, force: true });

const checks: Array<[string, boolean, string]> = [
	["P1 no push while both rows are running", step1 === 0, `deliveries=${step1}`],
	["P2 keyA window gets no keyB push (owner gate)", step2 === 0, `deliveries=${step2}`],
	[
		"P3 (C1): takeover of keyB replays the un-notified terminal row exactly once",
		count("b1") === 1,
		`count b1=${count("b1")}, deliveries=${step3}`,
	],
	[
		"P4 control: b2 goes terminal under watch -> pushed",
		step4 === step3 + 1 && had("b2"),
		`step3=${step3}, step4=${step4}, saw b2=${had("b2")}`,
	],
	[
		"P5 DEFECT: a2 terminal at open under the watched key is never replayed",
		!had("a2"),
		`saw a2=${had("a2")}`,
	],
	["P6 c1 terminal at open under an unwatched key is never replayed", step5 === step4 && !had("c1"), `saw c1=${had("c1")}`],
];

console.log("deliveries:", JSON.stringify(deliveries));
let failed = 0;
for (const [name, ok, detail] of checks) {
	if (!ok) failed += 1;
	console.log(`${ok ? "PASS" : "FAIL"}  ${name}  (${detail})`);
}
console.log(failed === 0 ? "VERDICT: defect reproduced as predicted" : `VERDICT: ${failed} check(s) failed`);
