import { spawnSync } from "node:child_process";
import { appendFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { collectArtifacts, newRunId, RUN_SCHEMA, writeRunState } from "../../../coding-agent/src/extensions/agent-team-loop/shared/run-store.ts";

// Isolated worker adapter. The independent checker's real exit and output
// determine the worker state recorded by the production run writer.
const [python, checker, project, taskDir, key, taskKey] = process.argv.slice(2);
const start = new Date();
const run = {
	schema: RUN_SCHEMA,
	task_key: taskKey,
	owner_key: key,
	run_id: newRunId(taskKey, start),
	kind: "reviewer",
	status: "running",
	pid: process.pid,
	started_at: start.toISOString(),
	artifacts: [],
};
const opened = writeRunState(taskDir, run);
if (!opened.ok) throw new Error(opened.error);

const result = spawnSync(python, ["-B", checker, project], { cwd: project, encoding: "utf8", timeout: 15000 });
const exit = result.status ?? 1;
if (exit === 0) writeFileSync(join(taskDir, "output.md"), result.stdout, "utf8");
appendFileSync(join(taskDir, "trace.log"), `[END] reviewer pid=${process.pid} exit=${exit}\n${result.stderr ?? ""}`, "utf8");
const closed = writeRunState(taskDir, {
	...run,
	status: exit === 0 ? "done" : "failed",
	ended_at: new Date().toISOString(),
	exit,
	artifacts: collectArtifacts(taskDir),
});
if (!closed.ok) throw new Error(closed.error);
process.exitCode = exit;
